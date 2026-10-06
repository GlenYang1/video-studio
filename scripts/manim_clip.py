"""渲染 Manim 片段并放进 Remotion 项目（public/manim/<场景名>.webm|mp4）。

  python manim_clip.py <项目目录> <场景脚本.py> <场景类名> [--transparent] [--quality h|m|l]

- 分辨率、帧率取自项目 storyboard.json，和成片一致
- 竖屏项目自动把坐标系改成 宽 8 × 高 14.2 单位（横屏默认 14.2 × 8），场景里不要再改 config.frame_*
- --transparent：透明背景，输出 WebM（VP9 带 alpha），在 Remotion 里叠在别的画面上；
  不透明时输出 mp4（背景色在场景里用 self.camera.background_color 设成主题色）
- 中文用 Text(..., font="Microsoft YaHei")，公式用 MathTex（需要 LaTeX），细节见 manim skill
输出后在分镜表里用 ManimClip 镜头：props {"video": "manim/<场景名>.webm"}；镜头时长比片段长时停在最后一帧。
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_json, media_duration, run, utf8_stdio  # noqa: E402


def main() -> None:
    utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("script")
    ap.add_argument("scene")
    ap.add_argument("--transparent", action="store_true")
    ap.add_argument("--quality", default="h", choices=["h", "m", "l"], help="l 用于快速预览")
    a = ap.parse_args()

    project = Path(a.project).resolve()
    sb = load_json(project / "storyboard.json", {})
    w, h, fps = int(sb.get("width", 1920)), int(sb.get("height", 1080)), int(sb.get("fps", 30))
    if a.quality != "h":  # 预览质量：分辨率减半
        w, h = w // (2 if a.quality == "m" else 4), h // (2 if a.quality == "m" else 4)
    script = Path(a.script).resolve()
    ext = "webm" if a.transparent else "mp4"
    media = Path(tempfile.mkdtemp(prefix="vs_manim_"))
    cmd = [sys.executable, "-m", "manim", "render", str(script), a.scene, "--media_dir", str(media),
           "-r", f"{w},{h}", "--fps", str(fps), "--format", ext, "--disable_caching", "--progress_bar", "none"]
    if a.transparent:
        cmd.append("-t")
    if h > w:
        # Manim 默认坐标是横屏的 14.2×8，-r 只改像素，竖屏会把画面缩成一小条。
        # 这里改成短边 8 个单位、长边按比例：竖屏 8×14.2，横屏场景照搬过来尺度不变。
        cfg = media / "portrait.cfg"
        cfg.write_text(f"[CLI]\nframe_width = 8.0\nframe_height = {8.0 * h / w:.4f}\n", encoding="utf-8")
        cmd += ["-c", str(cfg)]
    print(f"渲染 {a.scene}（{w}x{h} @ {fps}fps，{'透明 WebM' if a.transparent else 'MP4'}）…", flush=True)
    r = run(cmd, cwd=script.parent)
    outs = sorted(media.rglob(f"{a.scene}.{ext}"), key=lambda p: p.stat().st_mtime)
    if r.returncode != 0 or not outs:
        print((r.stderr or r.stdout)[-3000:])
        shutil.rmtree(media, ignore_errors=True)
        sys.exit("Manim 渲染失败：看上面的报错（常见：中文没指定 font、MathTex 缺 LaTeX 宏包）")
    dst = project / "public" / "manim" / f"{a.scene}.{ext}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(outs[-1]), dst)
    shutil.rmtree(media, ignore_errors=True)
    print(f"已输出 {dst}（{media_duration(dst):.2f}s）")
    print(f'分镜表镜头：{{"type": "manim", "props": {{"video": "manim/{dst.name}"}}}}')


if __name__ == "__main__":
    main()
