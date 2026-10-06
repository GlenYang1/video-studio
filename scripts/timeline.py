"""由分镜表 + 旁白时长 + 音乐节拍 计算时间轴，写入 src/timeline.json（Remotion 工程直接 import）。

  python timeline.py <项目目录>

规则（与 SKILL 第 6 步一致）：
  - 有旁白：旁白决定镜头时长（前留 0.3s、后留 0.5s，不短于分镜表里的 duration），字幕跟随旁白字级时间戳
  - 有音乐：切点对齐节拍（有旁白时取旁白结束后的下一拍，不会切断说话；无旁白时取最近的拍），
    结尾尽量落在小节线上；音乐比片长时在小节处截断并淡出，比片短时按整小节循环
  - 旁白和音乐同时有：说话区间音乐压低（duck）
旁白来源：
  - TTS：public/audio/vo/<镜头id>.words.json（tts.py 生成）
  - 用户上传的整段旁白：storyboard.voiceover.file，先运行 analyze_audio.py speech 得到 .words.json，
    再按各镜头 narration 文案自动对齐（镜头里写了 vo_start / vo_end 秒数时以它为准）
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from bisect import bisect_left
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_json, media_duration, save_json, utf8_stdio  # noqa: E402

LEAD, TAIL = 0.3, 0.5          # 旁白在镜头内的前后留白（秒）
CPS = 4.5                      # 还没生成配音时，按每秒 4.5 个汉字估算时长
BREAK = set("，。！？；：、,.!?;:…")
KEEP_END = set("？！?!")       # 字幕行尾保留问号和感叹号，其余标点去掉
NORM = re.compile(r"[\s\W_]+", re.UNICODE)


def norm(s: str) -> str:
    return NORM.sub("", s)


def join_token(a: str, b: str) -> str:
    """中文直接拼接，英文/数字之间补空格。"""
    if a and b and a[-1].isascii() and a[-1].isalnum() and b[0].isascii() and b[0].isalnum():
        return a + " " + b
    return a + b


def attach_punct(text: str, words: list[dict]) -> list[dict]:
    """edge-tts / Whisper 的词不带标点，按原文把标点挂回到词尾，用来断句。"""
    out, p = [], 0
    for w in words:
        token = w["word"].strip()
        i = text.find(token, p) if token else -1
        if i >= 0:
            p = i + len(token)
        trail = ""
        while p < len(text) and (text[p] in BREAK or text[p] in "“”\"'）)》」 "):
            trail += text[p]
            p += 1
        out.append({**w, "word": token, "trail": trail.strip()})
    return out


def build_lines(words: list[dict], max_chars: int) -> list[dict]:
    """把词拼成字幕行：遇到标点或超过 max_chars 就断行。words 的 start/end 已是成片绝对秒数。"""
    lines, cur, start = [], "", None
    for i, w in enumerate(words):
        if start is None:
            start = w["start"]
        cur = join_token(cur, w["word"])
        trail = w.get("trail", "")
        nxt = words[i + 1]["word"] if i + 1 < len(words) else ""
        if trail[-1:] in KEEP_END:
            cur += trail[-1]
        if any(c in BREAK for c in trail) or len(cur) + len(nxt) > max_chars or i == len(words) - 1:
            if cur.strip():
                lines.append({"text": cur.strip(), "start": start, "end": w["end"]})
            cur, start = "", None
    for a, b in zip(lines, lines[1:]):  # 行尾多停 0.2s，但不压到下一行
        a["end"] = min(a["end"] + 0.2, b["start"])
    if lines:
        lines[-1]["end"] += 0.2
    return lines


def align_user_vo(shots: list[dict], words: list[dict]) -> dict[str, tuple[float, float]]:
    """把整段旁白的转写结果按各镜头文案长度比例切开，返回 {镜头id: (开始秒, 结束秒)}。"""
    narrated = [s for s in shots if (s.get("narration") or "").strip()]
    explicit = {s["id"]: (float(s["vo_start"]), float(s["vo_end"])) for s in narrated
                if "vo_start" in s and "vo_end" in s}
    todo = [s for s in narrated if s["id"] not in explicit]
    if not todo or not words:
        return explicit
    # 每个词在转写全文中的累计字符位置
    cum, total = [], 0
    for w in words:
        cum.append(total)
        total += max(1, len(norm(w["word"])))
    lens = [max(1, len(norm(s["narration"]))) for s in todo]
    scale = total / sum(lens)
    result, pos = dict(explicit), 0.0
    for s, n in zip(todo, lens):
        lo, hi = pos, pos + n * scale
        idx = [k for k, c in enumerate(cum) if lo <= c < hi] or [min(bisect_left(cum, lo), len(words) - 1)]
        result[s["id"]] = (words[idx[0]]["start"], words[idx[-1]]["end"])
        pos = hi
    return result


def next_beat(beats: list[float], t: float, limit: float) -> float:
    i = bisect_left(beats, t - 1e-3)
    return beats[i] if i < len(beats) and beats[i] - t <= limit else t


def nearest_beat(beats: list[float], t: float, limit: float) -> float:
    i = bisect_left(beats, t)
    cands = [b for b in beats[max(0, i - 1):i + 1] if abs(b - t) <= limit]
    return min(cands, key=lambda b: abs(b - t)) if cands else t


def main() -> None:
    utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    a = ap.parse_args()
    project = Path(a.project).resolve()
    public = project / "public"
    sb = load_json(project / "storyboard.json")
    if not sb:
        sys.exit(f"找不到 {project / 'storyboard.json'}")
    fps, width, height = int(sb.get("fps", 30)), int(sb.get("width", 1920)), int(sb.get("height", 1080))
    shots = sb["shots"]
    warnings: list[str] = []

    # ---- 1. 每个镜头的旁白片段 -------------------------------------------------
    user_vo = (sb.get("voiceover") or {}).get("file")
    user_words: list[dict] = []
    if user_vo:
        wj = load_json(public / (user_vo + ".words.json"))
        if not wj:
            sys.exit(f"缺少 {user_vo}.words.json：先运行 analyze_audio.py speech public/{user_vo}")
        user_words = wj["words"]
        ranges = align_user_vo(shots, user_words)

    vo_info: dict[str, dict] = {}
    for s in shots:
        text = (s.get("narration") or "").strip()
        if not text:
            continue
        if user_vo:
            if s["id"] not in ranges:
                continue
            st, en = ranges[s["id"]]
            st, en = max(0.0, st - 0.15), en + 0.15
            words = [{**w, "start": w["start"] - st, "end": w["end"] - st} for w in user_words
                     if w["start"] >= st - 1e-3 and w["end"] <= en + 1e-3]
            vo_info[s["id"]] = {"src": user_vo, "trim": st, "dur": en - st, "words": attach_punct(text, words)}
        else:
            meta = load_json(public / "audio" / "vo" / f"{s['id']}.words.json")
            mp3 = public / "audio" / "vo" / f"{s['id']}.mp3"
            if meta and mp3.exists() and meta.get("text") == text:
                vo_info[s["id"]] = {"src": f"audio/vo/{s['id']}.mp3", "trim": 0.0, "dur": meta["duration"],
                                    "words": attach_punct(text, meta["words"])}
            else:
                warnings.append(f"{s['id']} 有旁白但没有对应配音（或文案已修改），按字数估算时长；先运行 tts.py")

    # ---- 2. 镜头时长（秒） ------------------------------------------------------
    durs = []
    for s in shots:
        base = float(s.get("duration") or 0)
        if s["id"] in vo_info:
            durs.append(max(base, LEAD + vo_info[s["id"]]["dur"] + TAIL))
        elif (s.get("narration") or "").strip():
            durs.append(max(base, LEAD + len(norm(s["narration"])) / CPS + TAIL))
        else:
            durs.append(base or 3.0)

    # ---- 3. 对齐音乐节拍 ---------------------------------------------------------
    music_cfg = sb.get("music") or {}
    music_src = music_cfg.get("file")
    ana = None
    if music_src:
        ana = load_json(public / (music_src + ".analysis.json"))
        if not ana:
            warnings.append(f"缺少 {music_src}.analysis.json，切点不对齐节拍；先运行 analyze_audio.py music")
    ends, t = [], 0.0
    for d in durs:
        t += d
        ends.append(t)
    if ana and ana.get("beats"):
        beats, beat_len = ana["beats"], 60 / ana["bpm"] if ana.get("bpm") else 0.5
        snapped, prev = [], 0.0
        for i, (s, e) in enumerate(zip(shots, ends)):
            e = e + (snapped[-1] - ends[i - 1] if i else 0.0)  # 前面镜头的平移累积到后面
            if s["id"] in vo_info or (s.get("narration") or "").strip():
                e2 = next_beat(beats, e, beat_len * 1.05)          # 不切断旁白
            else:
                e2 = nearest_beat(beats, e, beat_len * 0.55)
            if e2 - prev < 1.0:                                     # 镜头至少 1 秒
                e2 = next_beat(beats, prev + 1.0, beat_len * 1.05)
            if i == len(shots) - 1 and ana.get("downbeats"):        # 结尾尽量落在小节线
                e2 = next_beat(ana["downbeats"], e2, 2.0)
            snapped.append(e2)
            prev = e2
        ends = snapped
    frames_end = [round(e * fps) for e in ends]
    total = frames_end[-1]

    # ---- 4. 组装时间轴 -------------------------------------------------------------
    out_shots, all_words, duck = [], [], []
    start = 0
    for s, end in zip(shots, frames_end):
        item = {
            "id": s["id"], "type": s.get("type", "2d"), "from": start, "durationInFrames": end - start,
            "component": s.get("component", ""), "transition": s.get("transition", "cut"),
            "transitionFrames": int(s.get("transition_frames") or round(0.4 * fps)),
            "title": s.get("title", ""), "visual": s.get("visual", ""),
            "text": s.get("text", ""), "props": s.get("props", {}), "vo": None,
            "checkAt": float(s.get("check_at") or 0.6),
        }
        v = vo_info.get(s["id"])
        if v:
            vo_from = start + round(LEAD * fps)
            item["vo"] = {"src": v["src"], "from": vo_from, "trimBefore": round(v["trim"] * fps),
                          "durationInFrames": math.ceil(v["dur"] * fps)}
            base_t = vo_from / fps
            all_words += [{**w, "start": base_t + w["start"], "end": base_t + w["end"]} for w in v["words"]]
            duck.append([vo_from, vo_from + item["vo"]["durationInFrames"]])
        out_shots.append(item)
        start = end

    # 说话间隔小于 0.6s 的区间合并，避免音乐忽高忽低
    merged: list[list[int]] = []
    for r in duck:
        if merged and r[0] - merged[-1][1] < 0.6 * fps:
            merged[-1][1] = r[1]
        else:
            merged.append(list(r))

    music = None
    if music_src:
        mdur = (ana or {}).get("duration") or media_duration(public / music_src)
        downs = (ana or {}).get("downbeats") or []
        fade = float(music_cfg.get("fade_out", 2.0))
        trim = float(music_cfg.get("start", 0.0))          # 从音乐第几秒开始用（比如跳过前奏）
        segs = []
        if mdur - trim >= total / fps:
            segs.append({"from": 0, "durationInFrames": total, "trimBefore": round(trim * fps)})
        else:  # 音乐不够长：按整小节循环
            # 循环终点取文件结尾或之前最近的小节线（analyze_audio 会把正好结束在小节上的结尾也记为小节线）
            usable = [d for d in downs if trim + 4 < d <= mdur + 0.05]
            loop_end = min(usable[-1], mdur) if usable else mdur
            loop_frames = max(1, round((loop_end - trim) * fps))
            f = 0
            while f < total:
                segs.append({"from": f, "durationInFrames": min(loop_frames, total - f), "trimBefore": round(trim * fps)})
                f += loop_frames
            warnings.append(f"音乐 {mdur:.1f}s 短于成片 {total / fps:.1f}s，按 {loop_frames / fps:.1f}s 整小节循环 {len(segs)} 次")
        music = {"src": music_src, "volume": float(music_cfg.get("volume", 0.5)),
                 "duck": float(music_cfg.get("duck", 0.3)), "fadeInFrames": round(0.3 * fps),
                 "fadeOutFrames": round(fade * fps), "segments": segs,
                 "bpm": (ana or {}).get("bpm")}

    portrait = height > width
    max_chars = int(sb.get("caption_max_chars") or (12 if portrait else 18))
    cap_on = (sb.get("captions") if isinstance(sb.get("captions"), bool) else True) and bool(all_words)
    lines = build_lines(all_words, max_chars) if cap_on else []
    timeline = {
        "fps": fps, "width": width, "height": height, "durationInFrames": total,
        "title": sb.get("title", ""), "style": sb.get("style") or {}, "shots": out_shots, "music": music, "duckRanges": merged,
        "captions": {"enabled": cap_on,
                     "lines": [{"text": l["text"], "startMs": round(l["start"] * 1000), "endMs": round(l["end"] * 1000)}
                               for l in lines]},
    }
    save_json(project / "src" / "timeline.json", timeline)

    print(f"时间轴：{len(out_shots)} 个镜头，共 {total / fps:.2f}s（{total} 帧 @ {fps}fps，{width}x{height}）")
    for it in out_shots:
        vo = f"旁白 {it['vo']['durationInFrames'] / fps:.1f}s" if it["vo"] else "无旁白"
        print(f"  {it['id']:<5} {it['from'] / fps:6.2f}s → {(it['from'] + it['durationInFrames']) / fps:6.2f}s  "
              f"{it['durationInFrames'] / fps:5.2f}s  {it['type']:<6} {vo}")
    if music:
        print(f"音乐：{music['src']}，BPM {music['bpm']}，{len(music['segments'])} 段，压低区间 {len(merged)} 处")
    print(f"字幕：{len(lines)} 行" if cap_on else "字幕：关闭")
    for w in warnings:
        print("提示：" + w)
    print(f"已写入 {project / 'src' / 'timeline.json'}")


if __name__ == "__main__":
    main()
