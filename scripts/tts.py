"""按分镜表旁白生成配音（edge-tts），同时保存字级时间戳，字幕直接用它生成，不必再跑 Whisper。

  python tts.py <项目目录> [--voice zh-CN-YunxiNeural] [--rate +0%] [--only S01,S03] [--force]

读取 <项目>/storyboard.json，每个有 narration 的镜头输出：
  public/audio/vo/<镜头id>.mp3
  public/audio/vo/<镜头id>.words.json   {"text", "voice", "duration", "words": [{"word", "start", "end"}]}
旁白文本和音色都没变时跳过（改了文案只会重新生成对应镜头）。
音色优先级：命令行 --voice > 镜头的 voice > storyboard.voice.name > 默认云希。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_json, media_duration, save_json, utf8_stdio  # noqa: E402

DEFAULT_VOICE = "zh-CN-YunxiNeural"


async def synth(text: str, voice: str, rate: str, volume: str, pitch: str, mp3: Path) -> list[dict]:
    import edge_tts

    words = []
    comm = edge_tts.Communicate(text, voice, rate=rate, volume=volume, pitch=pitch, boundary="WordBoundary")
    tmp = mp3.with_suffix(".part")
    with open(tmp, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7  # 单位 100ns
                words.append({"word": chunk["text"], "start": round(start, 3),
                              "end": round(start + chunk["duration"] / 1e7, 3)})
    tmp.replace(mp3)
    return words


async def one(shot: dict, cfg: dict, out_dir: Path, force: bool, sem: asyncio.Semaphore) -> str:
    sid, text = shot["id"], shot["narration"].strip()
    voice = cfg["voice"] or shot.get("voice") or cfg["default_voice"]
    mp3, meta = out_dir / f"{sid}.mp3", out_dir / f"{sid}.words.json"
    old = load_json(meta, {})
    if not force and mp3.exists() and old.get("text") == text and old.get("voice") == voice \
            and old.get("rate") == cfg["rate"]:
        return f"{sid}: 未变化，跳过（{old.get('duration', 0):.2f}s）"
    async with sem:
        err = ""
        for attempt in range(5):
            try:
                words = await synth(text, voice, cfg["rate"], cfg["volume"], cfg["pitch"], mp3)
                break
            except Exception as e:  # 微软服务偶尔断连，重试即可
                err = str(e)[:200]
                await asyncio.sleep(2 * (attempt + 1))
        else:
            return f"{sid}: 失败（{err}）"
    dur = media_duration(mp3)
    save_json(meta, {"text": text, "voice": voice, "rate": cfg["rate"], "duration": round(dur, 3), "words": words})
    return f"{sid}: {dur:.2f}s，{len(words)} 个词，音色 {voice}"


async def main_async(a) -> int:
    project = Path(a.project).resolve()
    sb = load_json(project / "storyboard.json")
    if not sb:
        sys.exit(f"找不到 {project / 'storyboard.json'}")
    vcfg = sb.get("voice") or {}
    cfg = {
        "voice": a.voice,
        "default_voice": vcfg.get("name", DEFAULT_VOICE),
        "rate": a.rate or vcfg.get("rate", "+0%"),
        "volume": vcfg.get("volume", "+0%"),
        "pitch": vcfg.get("pitch", "+0Hz"),
    }
    only = set(a.only.split(",")) if a.only else None
    shots = [s for s in sb["shots"] if (s.get("narration") or "").strip() and (not only or s["id"] in only)]
    if not shots:
        print("分镜表里没有旁白文案，无需配音")
        return 0
    out_dir = project / "public" / "audio" / "vo"
    out_dir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(2)  # 并发太高时微软服务容易断连
    results = await asyncio.gather(*(one(s, cfg, out_dir, a.force, sem) for s in shots))
    # 微软服务偶发“网络名不再可用”断连，失败的镜头稍等后串行再补一轮
    retry = [i for i, r in enumerate(results) if "失败" in r]
    if retry:
        await asyncio.sleep(5)
        for i in retry:
            results[i] = await one(shots[i], cfg, out_dir, a.force, asyncio.Semaphore(1))
    for r in results:
        print("  " + r)
    failed = [r for r in results if "失败" in r]
    if failed:
        print("有镜头配音失败：检查网络后重跑本脚本（只会补生成失败的镜头）")
    return 1 if failed else 0


def main() -> None:
    utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--voice", help="覆盖所有镜头的音色，如 zh-CN-XiaoxiaoNeural")
    ap.add_argument("--rate", help="语速，如 +10%% 或 -5%%")
    ap.add_argument("--only", help="只生成这些镜头，逗号分隔")
    ap.add_argument("--force", action="store_true")
    sys.exit(asyncio.run(main_async(ap.parse_args())))


if __name__ == "__main__":
    main()
