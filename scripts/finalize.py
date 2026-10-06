"""渲染成片 → 响度标准化到 -14 LUFS → 技术检查（ffprobe），写出检查报告。

  python finalize.py <项目目录> [--comp Main] [--skip-render] [--crf 18]

步骤：
  1. npx remotion render <comp> out/raw.mp4（H.264 + AAC，使用共享的渲染浏览器）
  2. ffmpeg loudnorm 两遍法：-14 LUFS / 真峰值 -1.5 dBTP，视频流直接拷贝不重编码 → out/<标题>.mp4
  3. ffprobe 核对时长、分辨率、帧率、音轨，并复测响度；结果写入 out/check_report.md
有问题时退出码为 1，并在报告里列出原因，按报告修复后重跑即可。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import find_tool, load_json, loudness, npx, run, utf8_stdio  # noqa: E402

TARGET_I, TARGET_TP, TARGET_LRA = -14.0, -1.5, 11.0


def safe_name(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", s).strip("_")
    return s[:60] or "video"


def render(project: Path, comp: str, out: Path, crf: int) -> None:
    cmd = [npx(), "remotion", "render", comp, str(out), "--codec=h264", f"--crf={crf}",
           "--audio-codec=aac", "--audio-bitrate=192k", "--log=error"]
    print("渲染成片…（时长较长的片子需要几分钟）", flush=True)
    r = run(cmd, cwd=project, capture_output=False)
    if r.returncode != 0 or not out.exists():
        sys.exit("渲染失败：看上面的报错修复后重跑")


def normalize(src: Path, dst: Path) -> dict | None:
    """两遍 loudnorm：先测量，再用测量值线性标准化，音质比单遍更稳定。"""
    ffmpeg = find_tool("ffmpeg")
    m = loudness(src)
    if not m:
        return None
    if m["input_i"] < -70:  # 整片静音，没有可标准化的内容
        return m
    af = (f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:measured_I={m['input_i']}"
          f":measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
          ":linear=true:print_format=summary")
    r = run([ffmpeg, "-hide_banner", "-y", "-i", str(src), "-c:v", "copy", "-af", af,
             "-ar", "48000", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst)])
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-1500:])
    return m


def probe(path: Path) -> dict:
    r = run([find_tool("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    return json.loads(r.stdout)


def main() -> None:
    utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--comp", default="Main")
    ap.add_argument("--skip-render", action="store_true", help="已有 out/raw.mp4 时只做标准化和检查")
    ap.add_argument("--crf", type=int, default=18)
    a = ap.parse_args()

    project = Path(a.project).resolve()
    tl = load_json(project / "src" / "timeline.json")
    if not tl:
        sys.exit("缺少 src/timeline.json：先运行 timeline.py")
    out_dir = project / "out"
    out_dir.mkdir(exist_ok=True)
    raw = out_dir / "raw.mp4"
    final = out_dir / f"{safe_name(tl.get('title') or project.name)}.mp4"

    if not a.skip_render:
        render(project, a.comp, raw, a.crf)
    elif not raw.exists():
        sys.exit("没有 out/raw.mp4，去掉 --skip-render")

    before = normalize(raw, final)
    if not final.exists():  # 无音轨或静音：直接用原片
        final.write_bytes(raw.read_bytes())

    # ---- 技术检查 ----
    info = probe(final)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    au = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    fps_expect, dur_expect = tl["fps"], tl["durationInFrames"] / tl["fps"]
    has_sound = bool(tl.get("music") or any(s.get("vo") for s in tl["shots"]))
    rows, problems = [], []

    def check(name: str, expect: str, actual: str, ok: bool, fix: str = "") -> None:
        rows.append(f"| {name} | {expect} | {actual} | {'✅' if ok else '❌'} |")
        if not ok:
            problems.append(f"{name}：期望 {expect}，实际 {actual}。{fix}")

    dur = float(info["format"]["duration"])
    check("时长", f"{dur_expect:.2f}s", f"{dur:.2f}s", abs(dur - dur_expect) <= 1 / fps_expect + 0.05,
          "检查 Root.tsx 是否用 timeline.json 的 durationInFrames")
    if v:
        n, d = (int(x) for x in v["r_frame_rate"].split("/"))
        check("分辨率", f"{tl['width']}x{tl['height']}", f"{v['width']}x{v['height']}",
              (v["width"], v["height"]) == (tl["width"], tl["height"]), "渲染时不要加 --scale")
        check("帧率", f"{fps_expect}", f"{n / d:.3f}", abs(n / d - fps_expect) < 0.01)
        check("视频编码", "h264 / yuv420p", f"{v['codec_name']} / {v.get('pix_fmt')}",
              v["codec_name"] == "h264" and v.get("pix_fmt") == "yuv420p", "用 --codec=h264 渲染")
    else:
        check("视频流", "存在", "缺失", False)
    if has_sound:
        check("音轨", "存在", f"{au['codec_name']} {au.get('sample_rate')}Hz" if au else "缺失", bool(au),
              "检查 <Audio> 的 src 路径和 public/ 下文件")
        if au and v:
            gap = abs(float(au.get("duration", dur)) - float(v.get("duration", dur)))
            check("音画时长差", "≤ 0.1s", f"{gap:.2f}s", gap <= 0.1)
        after = loudness(final) if au else None
        if after:
            check("响度", f"{TARGET_I} LUFS ±1", f"{after['input_i']:.1f} LUFS", abs(after["input_i"] - TARGET_I) <= 1,
                  "音频过于安静或全是静音时 loudnorm 拉不到目标值")
            check("真峰值", f"≤ {TARGET_TP + 0.5} dBTP", f"{after['input_tp']:.1f} dBTP", after["input_tp"] <= TARGET_TP + 0.5)
    else:
        check("音轨", "无（未设置旁白和音乐）", "有" if au else "无", True)

    preview = load_json(out_dir / "check" / "preview.json", {})
    warn_frames = [f for f in preview.get("frames", []) if f["warnings"]]
    report = [
        f"# 检查报告：{tl.get('title') or project.name}",
        "",
        f"- 成片：`{final.relative_to(project)}`（{final.stat().st_size / 1e6:.1f} MB）",
        f"- 规格：{tl['width']}x{tl['height']} @ {fps_expect}fps，{dur_expect:.2f}s，{len(tl['shots'])} 个镜头",
        f"- 生成时间：{dt.datetime.now():%Y-%m-%d %H:%M}",
        "",
        "## 技术检查（ffprobe）",
        "",
        "| 项目 | 期望 | 实际 | 结果 |",
        "|---|---|---|---|",
        *rows,
        "",
        "## 画面检查（联系表）",
        "",
        f"- 联系表：`out/check/contact_sheet.jpg`" if preview else "- 未运行 preview_sheet.py",
        *[f"- {f['id']}（{f['time']}s）：{'；'.join(f['warnings'])}" for f in warn_frames],
        *(["- 仍有占位图：" + "、".join(preview["placeholders"])] if preview.get("placeholders") else []),
        "",
        "## 结论",
        "",
        "全部通过。" if not problems else "\n".join(f"- {p}" for p in problems),
    ]
    if before:
        report.insert(5, f"- 响度标准化前：{before['input_i']:.1f} LUFS，真峰值 {before['input_tp']:.1f} dBTP")
    (out_dir / "check_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(f"成片：{final}")
    print("\n".join(rows))
    print(f"报告：{out_dir / 'check_report.md'}")
    if problems:
        print("技术检查未通过：\n  " + "\n  ".join(problems))
        sys.exit(1)


if __name__ == "__main__":
    main()
