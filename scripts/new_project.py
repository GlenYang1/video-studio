"""新建视频项目：复制 Remotion 模板、放入中文字体、用 npmmirror 安装依赖。

  python new_project.py <项目目录> [--title 标题] [--aspect 16:9|9:16|1:1] [--fps 30] [--no-install]

每个视频一个独立目录，结构：
  storyboard.json     分镜表（唯一的内容来源，timeline.py 由它生成 src/timeline.json）
  refs/               用户上传的参考素材和分析结果
  public/             渲染用素材：images/ audio/ models/ manim/ renders/ fonts/
  manim/ blender/     Manim 场景脚本、Blender 文件和脚本
  src/                Remotion 工程（模板自带通用镜头组件，按需在 src/shots/ 里加新组件）
  out/                成片、检查报告、联系表
依赖第一次安装约 1~3 分钟，之后走 npm 缓存会快很多。
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import IS_WIN, SKILL_DIR, run, save_json, utf8_stdio  # noqa: E402

NPM_MIRROR = "https://registry.npmmirror.com"
SIZES = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350), "4:3": (1440, 1080)}
FONT_CANDIDATES = [Path("C:/Windows/Fonts/NotoSansSC-VF.ttf"), Path.home() / "AppData/Local/Microsoft/Windows/Fonts/NotoSansSC-VF.ttf"]


def main() -> None:
    utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--title", default="")
    ap.add_argument("--aspect", default="16:9", choices=list(SIZES))
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--no-install", action="store_true")
    a = ap.parse_args()

    project = Path(a.project).resolve()
    if (project / "package.json").exists():
        print(f"{project} 已经是项目目录，只补装依赖")
    else:
        shutil.copytree(SKILL_DIR / "assets" / "template", project, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("node_modules", "out"))
        for d in ("refs", "public/images", "public/audio/vo", "public/models", "public/manim", "public/renders",
                  "manim", "blender", "out/check"):
            (project / d).mkdir(parents=True, exist_ok=True)
        w, h = SIZES[a.aspect]
        title = a.title or project.name
        save_json(project / "storyboard.json", {
            "title": title, "fps": a.fps, "width": w, "height": h,
            "style": {"bg": "#0f1115", "fg": "#f5f5f7", "accent": "#4f8cff", "font": "Noto Sans SC", "reference": ""},
            "voice": {"name": "zh-CN-YunxiNeural", "rate": "+0%"},
            "captions": True,
            "shots": [{"id": "S01", "type": "2d", "component": "TitleCard", "duration": 3, "title": title,
                       "text": "", "narration": "", "visual": "标题卡"}],
        })
        # 先放一份最小时间轴，Studio 和 tsc 立即可用；写好分镜表后运行 timeline.py 覆盖
        save_json(project / "src" / "timeline.json", {
            "fps": a.fps, "width": w, "height": h, "durationInFrames": 3 * a.fps, "title": title, "style": {},
            "shots": [{"id": "S01", "type": "2d", "component": "TitleCard", "from": 0, "durationInFrames": 3 * a.fps,
                       "transition": "cut", "transitionFrames": 12, "title": title, "visual": "", "text": "",
                       "props": {}, "vo": None}],
            "music": None, "duckRanges": [], "captions": {"enabled": False, "lines": []},
        })
        print(f"已创建项目 {project}（{w}x{h} @ {a.fps}fps）")

    font_dst = project / "public" / "fonts" / "NotoSansSC-VF.ttf"
    if not font_dst.exists():
        src = next((p for p in FONT_CANDIDATES if p.exists()), None)
        if src:
            font_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, font_dst)
        else:
            print("提示：没找到 NotoSansSC-VF.ttf，字幕会回退到微软雅黑（渲染机需装有该字体）")

    if a.no_install:
        return
    npm = shutil.which("npm") or ("npm.cmd" if IS_WIN else "npm")
    print("安装依赖（npmmirror）…", flush=True)
    r = run([npm, "install", "--registry", NPM_MIRROR, "--prefer-offline", "--no-audit", "--no-fund",
             "--loglevel=error"], cwd=project, capture_output=False)
    if r.returncode != 0:
        sys.exit("npm install 失败：检查网络后在项目目录重跑 npm install --registry " + NPM_MIRROR)
    print("依赖安装完成。下一步：写 storyboard.json → tts.py → timeline.py")


if __name__ == "__main__":
    main()
