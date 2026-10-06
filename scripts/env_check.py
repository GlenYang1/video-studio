"""第 0 步：环境检查与自动安装（国内镜像）。

用法：
  python env_check.py              # 检查 + 自动安装缺失项，必需项全部通过后写入标记文件
  python env_check.py --check      # 只检查，不安装
  python env_check.py --force      # 忽略标记文件，重新检查
  python env_check.py --skip-models  # 跳过 Whisper 模型下载（约 480MB，可在用到时再装）

标记文件：~/.clawsgo/video-studio/env_ok.json。存在时 SKILL 流程直接跳过本步。
Blender、Photoshop、Node.js 这类大型软件只检查不安装。
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import importlib.metadata as md
import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BIN_DIR, EXE, IS_WIN, MARKER, MODELS_DIR, VS_HOME, find_tool, npx, run, utf8_stdio  # noqa: E402

PIP_MIRRORS = ["https://mirrors.aliyun.com/pypi/simple/", "https://pypi.tuna.tsinghua.edu.cn/simple/"]
NPM_MIRROR = "https://registry.npmmirror.com"
HF_MIRROR = "https://hf-mirror.com"

# 版本与模板 package.json 保持一致；Remotion 4.0.532 对应的渲染浏览器版本
REMOTION_VERSION = "4.0.532"
CHROME_VERSION = "149.0.7790.0"
CHROME_URL = f"{NPM_MIRROR}/-/binary/chrome-for-testing/{CHROME_VERSION}/win64/chrome-headless-shell-win64.zip"
CHROME_DIR = VS_HOME / "chrome-headless-shell"
CHROME_EXE = CHROME_DIR / "win64" / "chrome-headless-shell-win64" / "chrome-headless-shell.exe"
FFMPEG_STATIC = f"{NPM_MIRROR}/-/binary/ffmpeg-static/b6.1.1"

# Frameloop 不在 PyPI，固定到已审阅过的提交
FRAMELOOP_SHA = "8da6e39af6f37060f0538661bac2daffeebb8bef"
FRAMELOOP_URL = f"https://codeload.github.com/Alan-Lucena/Frameloop/zip/{FRAMELOOP_SHA}"

# 发行包名 -> (导入名, 固定版本)
PY_PKGS = {
    "Pillow": ("PIL", "12.1.0"),
    "requests": ("requests", "2.32.5"),
    "numpy": ("numpy", "2.2.6"),
    "edge-tts": ("edge_tts", "7.2.8"),
    "soundfile": ("soundfile", "0.14.0"),
    "librosa": ("librosa", "0.11.0"),
    "faster-whisper": ("faster_whisper", "1.2.1"),
    "manim": ("manim", "0.21.0"),
}

WHISPER_MODEL = os.environ.get("VIDEO_STUDIO_WHISPER", "small")
MCP_JSON = Path.home() / ".clawsgo" / "mcp.json"

results: list[dict] = []


def report(name: str, ok: bool, detail: str, required: bool = True, action: str = "") -> bool:
    results.append({"name": name, "ok": ok, "detail": detail, "required": required, "action": action})
    flag = "OK " if ok else ("缺失" if required else "提示")
    print(f"[{flag}] {name}: {detail}" + (f"  → {action}" if action and not ok else ""), flush=True)
    return ok


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "video-studio-env-check"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got, step = 0, 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            got += len(chunk)
            if total and got * 10 // total > step:
                step = got * 10 // total
                print(f"    下载 {dest.name}: {got * 100 // total}%", flush=True)
    tmp.replace(dest)


def pip_install(specs: list[str]) -> bool:
    for idx in PIP_MIRRORS:
        r = run([sys.executable, "-m", "pip", "install", "-i", idx, *specs], capture_output=False)
        if r.returncode == 0:
            return True
        print(f"    镜像 {idx} 安装失败，尝试下一个", flush=True)
    return False


def add_user_path(directory: Path) -> None:
    """把共享 bin 目录追加到用户 PATH（不用 setx，避免 1024 字符截断）。"""
    os.environ["PATH"] = f"{directory}{os.pathsep}{os.environ['PATH']}"
    if not IS_WIN:
        return
    ps = (
        "$d='{d}';$p=[Environment]::GetEnvironmentVariable('Path','User');"
        "if(-not (($p -split ';') -contains $d)){{[Environment]::SetEnvironmentVariable('Path',($p.TrimEnd(';')+';'+$d),'User');'added'}}"
    ).format(d=str(directory))
    r = run(["powershell", "-NoProfile", "-Command", ps])
    if "added" in r.stdout:
        print(f"    已把 {directory} 加入用户 PATH（新开的终端生效）", flush=True)


# ---------------------------------------------------------------- 各项检查

def check_basics() -> None:
    v = sys.version_info
    report("Python", v >= (3, 10), f"{v.major}.{v.minor}.{v.micro}（{sys.executable}）",
           action="需要 Python 3.10+")
    node = shutil.which("node")
    if node:
        ver = run([node, "-v"]).stdout.strip()
        major = int(ver.lstrip("v").split(".")[0] or 0)
        report("Node.js", major >= 18, ver, action="需要 Node.js 18+，从 https://npmmirror.com/mirrors/node/ 下载安装")
    else:
        report("Node.js", False, "未找到", action="从 https://npmmirror.com/mirrors/node/ 下载 LTS 安装包")
    report("npx", bool(shutil.which("npx")), npx())


def check_py_pkgs(install: bool) -> None:
    missing = []
    for dist, (mod, pin) in PY_PKGS.items():
        try:
            ver = md.version(dist)
            report(f"pip: {dist}", True, ver)
        except md.PackageNotFoundError:
            missing.append(f"{dist}=={pin}")
    if missing and install:
        print(f"    安装 Python 包：{' '.join(missing)}", flush=True)
        pip_install(missing)
    for spec in missing:
        dist = spec.split("==")[0]
        try:
            report(f"pip: {dist}", True, md.version(dist) + "（本次安装）")
        except md.PackageNotFoundError:
            report(f"pip: {dist}", False, "未安装", action=f"pip install -i {PIP_MIRRORS[0]} {spec}")


def check_ffmpeg(install: bool) -> None:
    for name in ("ffmpeg", "ffprobe"):
        hit = find_tool(name)
        if not hit and install:
            dest = BIN_DIR / f"{name}{EXE}"
            try:
                if name == "ffmpeg":
                    try:  # manim 依赖的 imageio-ffmpeg 自带完整 ffmpeg，直接复制最快
                        import imageio_ffmpeg

                        src = Path(imageio_ffmpeg.get_ffmpeg_exe())
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dest)
                    except Exception:
                        pass
                if not dest.exists():
                    gz = BIN_DIR / f"{name}.gz"
                    download(f"{FFMPEG_STATIC}/{name}-win32-x64.gz", gz)
                    with gzip.open(gz, "rb") as fi, open(dest, "wb") as fo:
                        shutil.copyfileobj(fi, fo)
                    gz.unlink()
                hit = str(dest)
            except Exception as e:
                print(f"    {name} 安装失败：{e}", flush=True)
        if hit:
            ver = run([hit, "-version"]).stdout.splitlines()[:1]
            report(name, True, f"{hit}（{ver[0][:40] if ver else ''}）")
        else:
            report(name, False, "未找到", action=f"手动下载 {FFMPEG_STATIC}/{name}-win32-x64.gz 解压到 {BIN_DIR}")
    if BIN_DIR.exists() and install:
        add_user_path(BIN_DIR)


def check_chrome(install: bool) -> None:
    if not IS_WIN:
        report("Remotion 渲染浏览器", True, "非 Windows，交给 Remotion 自动下载", required=False)
        return
    if not CHROME_EXE.exists() and install:
        # 先找本机已有 Remotion 项目里同版本的浏览器（复制比下载快得多）
        roots = [Path.home() / d for d in ("ClawsGO", "Documents", "Desktop", "Projects", "code")]
        found = None
        for root in roots:
            if not root.exists():
                continue
            for ver in list(root.glob("*/node_modules/.remotion/chrome-headless-shell/VERSION")) + \
                    list(root.glob("*/*/node_modules/.remotion/chrome-headless-shell/VERSION")):
                if ver.read_text(encoding="utf-8").strip() == CHROME_VERSION:
                    found = ver.parent
                    break
            if found:
                break
        try:
            if found:
                print(f"    从 {found} 复制渲染浏览器", flush=True)
                shutil.copytree(found, CHROME_DIR, dirs_exist_ok=True)
            else:
                z = VS_HOME / "chrome-headless-shell.zip"
                download(CHROME_URL, z)
                with zipfile.ZipFile(z) as f:
                    f.extractall(CHROME_DIR / "win64")
                (CHROME_DIR / "VERSION").write_text(CHROME_VERSION, encoding="utf-8")
                z.unlink()
        except Exception as e:
            print(f"    渲染浏览器安装失败：{e}", flush=True)
    report("Remotion 渲染浏览器", CHROME_EXE.exists(), f"{CHROME_VERSION} → {CHROME_EXE}",
           action=f"手动下载 {CHROME_URL} 解压到 {CHROME_DIR / 'win64'}")


def check_whisper_model(install: bool) -> None:
    target = MODELS_DIR / f"faster-whisper-{WHISPER_MODEL}"
    ok = (target / "model.bin").exists()
    if not ok and install:
        os.environ.setdefault("HF_ENDPOINT", HF_MIRROR)
        try:
            from huggingface_hub import snapshot_download

            print(f"    从 {HF_MIRROR} 下载 Whisper {WHISPER_MODEL} 模型（约 480MB）", flush=True)
            snapshot_download(f"Systran/faster-whisper-{WHISPER_MODEL}", local_dir=str(target),
                              endpoint=os.environ["HF_ENDPOINT"])
            ok = (target / "model.bin").exists()
        except Exception as e:
            print(f"    模型下载失败：{e}", flush=True)
    report(f"Whisper 模型 {WHISPER_MODEL}", ok, str(target), required=False,
           action="用到人声转写时再运行 env_check.py 下载，或设置 HF_ENDPOINT=https://hf-mirror.com")


PATCH_MARK = "# video-studio: windows npx fix"
PATCH_LINE = "    cmd = [__import__('shutil').which(cmd[0]) or cmd[0], *cmd[1:]]  " + PATCH_MARK + "\n"


def patch_frameloop(install: bool) -> None:
    """Frameloop 的 MCP 工具用 create_subprocess_exec("npx", ...) 调 Remotion，Windows 上找不到 npx.cmd。
    在两个子进程函数开头把 cmd[0] 解析成完整路径（幂等，重装 Frameloop 后会再次打补丁）。"""
    try:
        import frameloop
    except ImportError:
        return
    root = Path(frameloop.__file__).parent
    targets = [root / "mcp_server.py", root / "routers" / "render.py"]
    pending = [p for p in targets if p.exists() and PATCH_MARK not in p.read_text(encoding="utf-8")]
    if pending and install:
        for p in pending:
            shutil.copy2(p, p.with_name(p.name + ".orig"))  # 保留原文件，删掉补丁后改回即可
            lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
            out, in_fn = [], False
            for line in lines:
                if line.startswith(("async def _run(", "async def _run_command(")):
                    in_fn = True
                if in_fn and "proc = await asyncio.create_subprocess_exec(" in line:
                    out.append(PATCH_LINE)
                    in_fn = False
                out.append(line.replace("stdout.decode(), stderr.decode()",
                                        'stdout.decode(errors="replace"), stderr.decode(errors="replace")'))
            p.write_text("".join(out), encoding="utf-8")
        pending = [p for p in targets if p.exists() and PATCH_MARK not in p.read_text(encoding="utf-8")]
    report("Frameloop Windows 补丁", not pending, "npx → npx.cmd 已修复" if not pending else "未打补丁",
           required=False, action="运行 env_check.py --force 自动修复（否则 render_still 等 MCP 工具在 Windows 上报错）")


def check_frameloop(install: bool) -> None:
    exe = shutil.which("frameloop") or str(Path(sys.executable).parent / "Scripts" / f"frameloop{EXE}")
    ok = Path(exe).exists()
    if not ok and install:
        print("    从 GitHub 安装 Frameloop（依赖走 pip 国内镜像）", flush=True)
        if not pip_install([f"frameloop @ {FRAMELOOP_URL}"]):
            print("    GitHub 下载失败：请配置代理后重新运行，或手动下载仓库 zip 后 pip install <zip路径>", flush=True)
        ok = Path(exe).exists()
    report("Frameloop", ok, exe if ok else "未安装", required=False,
           action="参考视频抽帧需要它；GitHub 不通时配置代理后重试")
    if not ok:
        return
    if IS_WIN:
        patch_frameloop(install)
    py = frameloop_venv(install)
    if not py:
        return
    # 注册到 ClawsGO 的 MCP 配置（下个任务生效）
    want = {
        "command": py,
        "args": ["-c", "from frameloop.cli import cli; cli()", "mcp"],
        "env": {"FRAMELOOP_OUTPUT_DIR": str(VS_HOME / "frameloop_output"), "PYTHONIOENCODING": "utf-8"},
    }
    cfg = json.loads(MCP_JSON.read_text(encoding="utf-8")) if MCP_JSON.exists() else {"mcpServers": {}}
    servers = cfg.setdefault("mcpServers", {})
    cur = servers.get("frameloop", {})
    if cur.get("command") == want["command"] and cur.get("args") == want["args"]:
        report("Frameloop MCP 配置", True, f"已在 {MCP_JSON}", required=False)
    elif install:
        if MCP_JSON.exists():
            shutil.copy2(MCP_JSON, MCP_JSON.with_name(f"mcp.json.bak-{dt.date.today():%Y%m%d}"))
        servers["frameloop"] = {**cur, **want, "env": {**cur.get("env", {}), **want["env"]}}
        MCP_JSON.parent.mkdir(parents=True, exist_ok=True)
        MCP_JSON.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        report("Frameloop MCP 配置", True, f"已写入 {MCP_JSON}（下个任务生效，原文件已备份）", required=False)
    else:
        report("Frameloop MCP 配置", False, "未注册或启动命令过期", required=False,
               action="运行 env_check.py --force 自动注册")


FL_VENV = VS_HOME / "frameloop-venv"


def frameloop_venv(install: bool) -> str | None:
    """Frameloop 0.2 用的是 mcp 1.x 的 FastMCP，全局装的 mcp 2.x 已移除这个接口。
    建一个继承全局包的虚拟环境，只在里面装 mcp 1.x，不影响全局其他包。返回该环境的 python 路径。"""
    py = FL_VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")
    probe = "import mcp.server.fastmcp, frameloop.mcp_server"
    ok = py.exists() and run([str(py), "-c", probe]).returncode == 0
    if not ok and install:
        print("    为 Frameloop MCP 建独立环境（mcp 1.x）", flush=True)
        if not py.exists():
            run([sys.executable, "-m", "venv", "--system-site-packages", str(FL_VENV)])
        for idx in PIP_MIRRORS:
            if run([str(py), "-m", "pip", "install", "-q", "-i", idx, "mcp>=1.20,<2"]).returncode == 0:
                break
        ok = py.exists() and run([str(py), "-c", probe]).returncode == 0
    report("Frameloop MCP 运行环境", ok, str(py) if ok else "mcp 版本不兼容", required=False,
           action="运行 env_check.py --force 自动修复；不修也不影响 ref_video.py")
    return str(py) if ok else None


def check_apps() -> None:
    cfg = json.loads(MCP_JSON.read_text(encoding="utf-8")) if MCP_JSON.exists() else {}
    servers = cfg.get("mcpServers", {})

    blender = servers.get("blender", {})
    bpath = blender.get("env", {}).get("BLENDER_PATH") or shutil.which("blender")
    if bpath and Path(bpath).exists():
        ver = run([bpath, "--version"]).stdout.splitlines()[:1]
        report("Blender", True, f"{ver[0] if ver else ''}（{bpath}）", required=False)
    else:
        report("Blender", False, "未找到", required=False, action="需要 3D 编辑时手动安装 Blender 4.x/5.x")
    port = int(blender.get("env", {}).get("BLENDER_MCP_PORT", 9876))
    s = socket.socket()
    s.settimeout(1.5)
    try:
        s.connect(("localhost", port))
        report("blender-mcp 连接", True, f"localhost:{port} 已连通", required=False)
    except OSError:
        report("blender-mcp 连接", False, f"localhost:{port} 未连通" if blender else "mcp.json 未配置 blender",
               required=False, action="用到 3D 时打开 Blender 并在 N 面板启动 MCP 插件")
    finally:
        s.close()

    ps = servers.get("photoshop", {})
    ppath = ps.get("env", {}).get("PHOTOSHOP_PATH")
    report("Photoshop + ps-mcp", bool(ps) and bool(ppath) and Path(ppath).exists(),
           ppath or "mcp.json 未配置 photoshop", required=False,
           action="用到修图时先打开 Photoshop，再调用 photoshop_ping 确认连接")

    for var in ("IMG_API", "IMG_KEY"):
        report(f"环境变量 {var}", bool(os.environ.get(var)), "已设置" if os.environ.get(var) else "未设置",
               required=False, action="没有出图 key 时 gen_image.py 会输出提示词清单和占位图")
    report("出图模型", True, os.environ.get("IMG_MODEL", "gpt-image-2.5-flare（默认）"), required=False)

    tex = shutil.which("latex") or next(
        (str(p) for p in [Path.home() / "AppData/Local/Programs/MiKTeX/miktex/bin/x64/latex.exe"] if p.exists()), None)
    report("LaTeX（Manim 公式）", bool(tex), tex or "未找到", required=False,
           action="只用 Text 不用 MathTex 时可忽略")


def main() -> None:
    utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查不安装")
    ap.add_argument("--force", action="store_true", help="忽略标记文件")
    ap.add_argument("--skip-models", action="store_true", help="跳过 Whisper 模型下载")
    a = ap.parse_args()

    if MARKER.exists() and not a.force and not a.check:
        print(f"环境已检查通过（{MARKER}），跳过。需要重新检查时加 --force。")
        return

    install = not a.check
    VS_HOME.mkdir(parents=True, exist_ok=True)
    print(f"== video-studio 环境检查（共享目录 {VS_HOME}）==", flush=True)
    check_basics()
    check_py_pkgs(install)
    check_ffmpeg(install)
    check_chrome(install)
    if not a.skip_models:
        check_whisper_model(install)
    check_frameloop(install)
    check_apps()

    failed = [r for r in results if r["required"] and not r["ok"]]
    hints = [r for r in results if not r["required"] and not r["ok"]]
    print("\n== 环境状态清单 ==")
    print(f"必需项：{sum(r['ok'] for r in results if r['required'])}/{sum(r['required'] for r in results)} 通过")
    for r in failed:
        print(f"  ✗ {r['name']}：{r['action']}")
    for r in hints:
        print(f"  · {r['name']}（可选）：{r['action']}")
    if not failed and install:
        MARKER.write_text(json.dumps({
            "checked_at": dt.datetime.now().isoformat(timespec="seconds"),
            "remotion": REMOTION_VERSION,
            "chrome": str(CHROME_EXE),
            "items": results,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入标记文件 {MARKER}，之后自动跳过环境检查。")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
