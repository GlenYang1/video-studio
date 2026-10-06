"""video-studio 各脚本共用的路径与工具查找逻辑。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# 共享目录：ffmpeg、渲染用 Chrome、Whisper 模型、环境标记文件都放这里，所有视频项目共用
VS_HOME = Path(os.environ.get("VIDEO_STUDIO_HOME", Path.home() / ".clawsgo" / "video-studio"))
BIN_DIR = VS_HOME / "bin"
MODELS_DIR = VS_HOME / "models"
MARKER = VS_HOME / "env_ok.json"
SKILL_DIR = Path(__file__).resolve().parent.parent

IS_WIN = os.name == "nt"
EXE = ".exe" if IS_WIN else ""


def utf8_stdio() -> None:
    """Windows 控制台默认 GBK，统一切到 UTF-8，避免中文输出乱码。"""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def find_tool(name: str, project: str | Path | None = None) -> str | None:
    """按 PATH → 共享 bin → 项目内 Remotion 自带二进制 的顺序查找 ffmpeg/ffprobe。"""
    hit = shutil.which(name)
    if hit:
        return hit
    cand = BIN_DIR / f"{name}{EXE}"
    if cand.exists():
        return str(cand)
    if project:
        for p in Path(project).glob(f"node_modules/@remotion/compositor-*/{name}{EXE}"):
            return str(p)
    return None


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    kw.setdefault("encoding", "utf-8")
    kw.setdefault("errors", "replace")
    return subprocess.run(cmd, **kw)


def npx() -> str:
    """Windows 下必须用 npx.cmd，否则 subprocess 找不到。"""
    return shutil.which("npx") or ("npx.cmd" if IS_WIN else "npx")


def load_json(path: str | Path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(path: str | Path, data) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


MCP_JSON = Path.home() / ".clawsgo" / "mcp.json"
# gen_image.py 生成占位图时写进 PNG 文本块的标记，preview_sheet.py 用它找出还没替换的占位图
PLACEHOLDER_TAG = "video-studio-placeholder"


def is_placeholder(path: str | Path) -> bool:
    """是不是 gen_image.py 生成的占位图（PNG 文本块 vs / JPEG 注释里带标记）。"""
    try:
        from PIL import Image

        with Image.open(path) as im:
            return im.info.get("vs") == PLACEHOLDER_TAG or PLACEHOLDER_TAG.encode() in (im.info.get("comment") or b"")
    except Exception:
        return False


def blender_exe() -> str | None:
    """Blender 路径：mcp.json 里 blender-mcp 的 BLENDER_PATH → PATH。"""
    try:
        cfg = json.loads(MCP_JSON.read_text(encoding="utf-8"))
        p = cfg.get("mcpServers", {}).get("blender", {}).get("env", {}).get("BLENDER_PATH")
        if p and Path(p).exists():
            return p
    except Exception:
        pass
    return shutil.which("blender")


def loudness(path: str | Path) -> dict | None:
    """用 ffmpeg loudnorm 测响度，返回 {input_i, input_tp, input_lra, input_thresh}；没有音轨时返回 None。"""
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("缺少 ffmpeg，请先运行 env_check.py")
    r = run([ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-vn",
             "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])
    text = r.stderr
    start, end = text.rfind("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        data = json.loads(text[start:end + 1])
        return {k: float(data[k]) for k in ("input_i", "input_tp", "input_lra", "input_thresh")}
    except (ValueError, KeyError):
        return None


def media_duration(path: str | Path) -> float:
    """用 PyAV 读媒体时长（秒）；PyAV 随 manim 安装，失败时退回 ffprobe。"""
    try:
        import av

        with av.open(str(path)) as c:
            if c.duration:
                return c.duration / 1_000_000
            s = c.streams[0]
            return float(s.duration * s.time_base)
    except Exception:
        probe = find_tool("ffprobe")
        if not probe:
            raise
        r = run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
        return float(r.stdout.strip())
