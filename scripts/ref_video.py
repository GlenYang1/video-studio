"""参考视频分析：用 Frameloop 抽关键帧（镜头切换 + 均匀采样），拼联系表，提取配色，估算剪辑节奏。

  python ref_video.py <参考视频> [--out <项目>/refs/<视频名>] [--max-frames 12]

和 Frameloop MCP 的 analyze_video 等价（同一套抽帧代码，不用 Replicate 密集模式），
MCP 没加载时也能用。输出：
  frames/*.jpg      关键帧
  grid.jpg          联系表（用 Read 看这一张就够，省 token）
  summary.json      时长、分辨率、帧率、镜头切点、平均镜头时长、配色、是否有音轨
看完联系表后，把配色、字体风格、镜头节奏、运镜和内容总结写进 storyboard.json 的 style 字段。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import save_json, utf8_stdio  # noqa: E402


def scene_cuts(video: str) -> list[float]:
    """用 PySceneDetect 找镜头切点（秒），统计剪辑节奏。"""
    try:
        from scenedetect import ContentDetector, detect

        scenes = detect(video, ContentDetector(threshold=27.0), show_progress=False)
        return [round(s[0].get_seconds(), 2) for s in scenes[1:]]
    except Exception:
        return []


def has_audio(video: str) -> bool:
    try:
        import av

        with av.open(video) as c:
            return any(s.type == "audio" for s in c.streams)
    except Exception:
        return False


def main() -> None:
    utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out")
    ap.add_argument("--max-frames", type=int, default=12)
    a = ap.parse_args()

    try:
        from frameloop.colors import extract_palette
        from frameloop.extractor import ExtractionMethod, compose_grid, extract_frames
    except ImportError:
        sys.exit("缺少 Frameloop：运行 env_check.py --force 安装")

    video = Path(a.video).resolve()
    if not video.exists():
        sys.exit(f"文件不存在：{video}")
    out = Path(a.out).resolve() if a.out else video.parent / f"{video.stem}_analysis"
    (out / "frames").mkdir(parents=True, exist_ok=True)

    result = extract_frames(str(video), method=ExtractionMethod.COMBINED, max_frames=a.max_frames)
    frames = []
    for f in result.frames:
        p = out / "frames" / f"frame_{f.index:02d}_{f.timestamp:06.2f}s.jpg"
        f.image.convert("RGB").save(p, "JPEG", quality=88)
        frames.append({"time": round(f.timestamp, 2), "reason": f.reason, "path": str(p)})
    grid = compose_grid(result, detailed=False)
    grid.convert("RGB").save(out / "grid.jpg", "JPEG", quality=88)

    palette = []
    try:  # 用联系表取全片主色，比单帧更有代表性
        palette = [{"hex": c["hex"], "percent": c.get("percentage", c.get("percent"))}
                   for c in extract_palette(str(out / "grid.jpg"), num_colors=6)]
    except Exception as e:
        print(f"配色提取失败：{e}")

    cuts = scene_cuts(str(video))
    first = result.frames[0].image if result.frames else None
    summary = {
        "video": str(video),
        "duration": round(result.duration, 2),
        "fps": round(result.fps, 2),
        "size": list(first.size) if first else None,
        "has_audio": has_audio(str(video)),
        "cuts": cuts,
        "shot_count": len(cuts) + 1,
        "avg_shot_seconds": round(result.duration / (len(cuts) + 1), 2),
        "palette": palette,
        "frames": frames,
        "grid": str(out / "grid.jpg"),
    }
    save_json(out / "summary.json", summary)
    print(f"时长 {summary['duration']}s，{summary['fps']}fps，约 {summary['shot_count']} 个镜头，"
          f"平均每镜 {summary['avg_shot_seconds']}s，{'有' if summary['has_audio'] else '无'}音轨")
    print("主色：" + " ".join(c["hex"] for c in palette))
    print(f"联系表：{out / 'grid.jpg'}（用 Read 查看）")
    if summary["has_audio"]:
        print("参考视频带音轨：需要它的旁白/音乐信息时运行 analyze_audio.py speech|music <视频>")


if __name__ == "__main__":
    main()
