"""画面检查（整片渲染前）：每个镜头渲染 1 帧，拼成联系表，并做几项不费 token 的自动检测。

  python preview_sheet.py <项目目录> [--comp Main] [--scale 0.5]

作用等同 Frameloop 的 render_preview，区别是按 src/timeline.json 的镜头取帧（每镜 1 帧，默认取镜头 60% 处，
入场动画已结束；镜头可用 check_at 指定 0~1 的位置），并且只打包一次（render --frames 多帧一次出完）。
输出：out/check/contact_sheet.jpg（用 Read 看这一张，对照分镜表检查文字裁切、素材缺失、3D 过暗/穿模）
      out/check/preview.json（每帧的自动检测结果）
自动检测：画面过暗、近乎纯色（素材没加载）、仍在使用占位图。
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import is_placeholder, load_json, npx, run, save_json, utf8_stdio  # noqa: E402


def main() -> None:
    utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--comp", default="Main")
    ap.add_argument("--scale", type=float, default=0.5, help="渲染缩放，0.5 足够看清排版")
    a = ap.parse_args()

    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    project = Path(a.project).resolve()
    tl = load_json(project / "src" / "timeline.json")
    if not tl:
        sys.exit("缺少 src/timeline.json：先运行 timeline.py")
    fps, shots = tl["fps"], tl["shots"]

    picks = []
    for s in shots:
        at = s.get("checkAt", 0.6)
        f = s["from"] + min(s["durationInFrames"] - 1, max(0, round(s["durationInFrames"] * at)))
        picks.append(f)
    frames_arg = ",".join(str(f) for f in sorted(set(picks)))

    tmp = Path(tempfile.mkdtemp(prefix="vs_preview_"))
    props = tmp / "props.json"  # 用文件传 props，避免 npx.cmd 经过 cmd.exe 时 JSON 引号被吃掉
    props.write_text('{"preview": true}', encoding="utf-8")
    out_seq = tmp / "frames"
    cmd = [npx(), "remotion", "render", a.comp, str(out_seq), f"--frames={frames_arg}", "--sequence",
           "--image-format=jpeg", f"--scale={a.scale}", "--muted", f"--props={props}", "--log=error"]
    print(f"渲染 {len(picks)} 帧（每镜头 1 帧）…", flush=True)
    r = run(cmd, cwd=project)
    if r.returncode != 0:
        print((r.stderr or r.stdout)[-3000:])
        shutil.rmtree(tmp, ignore_errors=True)
        sys.exit("预览帧渲染失败：先修复上面的报错（常见：组件报错、素材路径错误、缺少依赖）")
    files = {}
    for p in (out_seq.iterdir() if out_seq.exists() else []):
        m = re.search(r"(\d+)\.(jpe?g|png)$", p.name)
        if m:
            files[int(m.group(1))] = p

    portrait = tl["height"] > tl["width"]
    cols = max(1, min(6 if portrait else 4, len(shots)))
    cell_w = 300 if portrait else 480
    cell_h = round(cell_w * tl["height"] / tl["width"])
    label_h = 56
    rows = (len(shots) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w + (cols + 1) * 8, rows * (cell_h + label_h) + (rows + 1) * 8), (24, 24, 28))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("msyh.ttc", 18)
        small = ImageFont.truetype("msyh.ttc", 15)
    except OSError:
        font = small = ImageFont.load_default()

    results = []
    for i, (s, f) in enumerate(zip(shots, picks)):
        x = 8 + (i % cols) * (cell_w + 8)
        y = 8 + (i // cols) * (cell_h + label_h + 8)
        warn = []
        src = files.get(f)
        if src:
            im = Image.open(src).convert("RGB")
            arr = np.asarray(im.convert("L"), dtype=np.float32)
            # 只对 3D 镜头查过暗（灯光不足/曝光低）；2D 深色主题是设计选择，不报
            # 只对 3D 镜头查过暗，看最亮 5% 像素（主体）而不是平均值，深色背景不会误报
            hi = float(np.percentile(arr, 95))
            if s.get("type") in ("3d", "mixed") and hi < 70:
                warn.append(f"3D 主体过暗(高光亮度 {hi:.0f})，调高 light 或补光")
            if arr.std() < 6:
                warn.append("近乎纯色，素材可能没加载")
            sheet.paste(im.resize((cell_w, cell_h)), (x, y))
        else:
            warn.append("这一帧没渲染出来")
            draw.rectangle([x, y, x + cell_w, y + cell_h], fill=(80, 20, 20))
        t0, t1 = s["from"] / fps, (s["from"] + s["durationInFrames"]) / fps
        head = f"{s['id']}  {t0:.1f}-{t1:.1f}s  {s.get('type', '')}  帧{f}"
        draw.text((x + 4, y + cell_h + 4), head, font=font, fill=(255, 210, 90) if warn else (230, 230, 235))
        sub = "⚠ " + "；".join(warn) if warn else (s.get("title") or s.get("visual") or "")[:40]
        draw.text((x + 4, y + cell_h + 30), sub, font=small, fill=(255, 120, 110) if warn else (160, 160, 170))
        results.append({"id": s["id"], "frame": f, "time": round(f / fps, 2), "warnings": warn})

    placeholders = [str(p.relative_to(project)) for p in (project / "public").rglob("*")
                    if p.suffix.lower() in (".png", ".jpg", ".jpeg") and is_placeholder(p)]
    out_dir = project / "out" / "check"
    out_dir.mkdir(parents=True, exist_ok=True)
    sheet.save(out_dir / "contact_sheet.jpg", "JPEG", quality=85)
    save_json(out_dir / "preview.json", {"frames": results, "placeholders": placeholders})
    shutil.rmtree(tmp, ignore_errors=True)

    print(f"联系表：{out_dir / 'contact_sheet.jpg'}（用 Read 查看，对照分镜表逐镜检查）")
    bad = [r for r in results if r["warnings"]]
    for r in bad:
        print(f"  ⚠ {r['id']}（{r['time']}s）：{'；'.join(r['warnings'])}")
    if placeholders:
        print(f"  · 仍在使用占位图 {len(placeholders)} 张（无 IMG_KEY 或出图失败）：" + "、".join(placeholders[:6]))
    if not bad:
        print("  自动检测未发现问题")


if __name__ == "__main__":
    main()
