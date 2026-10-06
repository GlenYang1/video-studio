"""出图：OpenAI 兼容接口 {IMG_API}/v1/images/generations（有参考图时走 /v1/images/edits）。

单张：
  python gen_image.py --prompt "..." --out public/images/s01.png --aspect 16:9 [--quality low] [--ref style.png]
批量（读取清单，并发 3）：
  python gen_image.py --batch images.json [--quality medium] [--ref style.png]

images.json 格式：
  [{"file": "public/images/s01_bg.png", "prompt": "...", "aspect": "16:9", "shot": "S01"}]
  file 相对于清单所在目录；可选字段 quality、ref（单条覆盖全局设置）、transparent（true 时请求透明背景）。

没有 IMG_KEY 时不报错：生成同尺寸占位图，方便用户手动出图后放入同名文件。
批量模式总会写 image_prompts.md（提示词清单，有 key 时也写，留作记录和返工用）。
已存在的文件默认跳过（加 --overwrite 重新生成），这样用户手动替换的图不会被覆盖；占位图例外，有 key 后重跑会自动补出真图。
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import io
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PLACEHOLDER_TAG, is_placeholder, load_json, utf8_stdio  # noqa: E402

DEFAULT_MODEL = "gpt-image-2.5-flare"
# gpt-image 系列只稳定支持这三种尺寸，其他比例先按最接近的出图，进 Remotion 后用 objectFit: cover 裁切
SIZES = {"16:9": "1536x1024", "3:2": "1536x1024", "9:16": "1024x1536", "2:3": "1024x1536", "1:1": "1024x1024",
         "4:3": "1536x1024", "3:4": "1024x1536"}


def cfg():
    return (os.environ.get("IMG_API", "").rstrip("/"), os.environ.get("IMG_KEY", ""),
            os.environ.get("IMG_MODEL", DEFAULT_MODEL))


def size_of(aspect: str) -> str:
    return aspect if "x" in aspect else SIZES.get(aspect, "1536x1024")


def placeholder(path: Path, size: str, label: str) -> None:
    from PIL import Image, ImageDraw, ImageFont

    w, h = (int(v) for v in size.split("x"))
    im = Image.new("RGB", (w, h), (58, 62, 74))
    d = ImageDraw.Draw(im)
    for x in range(-h, w, 48):  # 斜线底纹，一眼能认出是占位图
        d.line([(x, 0), (x + h, h)], fill=(68, 72, 86), width=10)
    try:
        font = ImageFont.truetype("msyh.ttc", max(28, w // 28))
    except OSError:
        font = ImageFont.load_default()
    text = f"占位图（待替换）\n{label}"
    box = d.multiline_textbbox((0, 0), text, font=font, align="center")
    d.multiline_text(((w - box[2]) / 2, (h - box[3]) / 2), text, font=font, fill=(220, 224, 235), align="center")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".png":  # 打上标记：preview_sheet.py 据此报告未替换的占位图，有 key 后重跑会自动重新出图
        from PIL.PngImagePlugin import PngInfo

        info = PngInfo()
        info.add_text("vs", PLACEHOLDER_TAG)
        im.save(path, pnginfo=info)
    else:
        im.convert("RGB").save(path, comment=PLACEHOLDER_TAG.encode())


def generate(item: dict, base: Path, quality: str, ref: str | None, overwrite: bool) -> tuple[str, str]:
    import requests

    out = (base / item["file"]).resolve()
    if out.exists() and not overwrite and not is_placeholder(out):
        return item["file"], "已存在，跳过"
    api, key, model = cfg()
    size = size_of(item.get("aspect", "16:9"))
    if not key:
        placeholder(out, size, Path(item["file"]).name)
        return item["file"], "无 IMG_KEY，已生成占位图"

    quality = item.get("quality", quality)
    ref = item.get("ref", ref)
    data = {"model": model, "prompt": item["prompt"], "size": size, "quality": quality, "n": 1}
    if item.get("transparent"):
        data["background"] = "transparent"
    headers = {"Authorization": f"Bearer {key}"}
    t0 = time.time()
    for attempt in range(3):
        try:
            if ref:
                refs = [ref] if isinstance(ref, str) else ref
                files = [("image[]", (Path(r).name, open((base / r) if not Path(r).is_absolute() else r, "rb"),
                                      "image/png")) for r in refs]
                r = requests.post(f"{api}/v1/images/edits", headers=headers, files=files,
                                  data={k: str(v) for k, v in data.items()}, timeout=240)
            else:
                r = requests.post(f"{api}/v1/images/generations", headers=headers, json=data, timeout=240)
            if r.status_code == 200:
                d = r.json()["data"][0]
                raw = base64.b64decode(d["b64_json"]) if d.get("b64_json") else requests.get(d["url"], timeout=120).content
                out.parent.mkdir(parents=True, exist_ok=True)
                from PIL import Image

                Image.open(io.BytesIO(raw)).save(out)  # 统一转成目标扩展名对应的格式
                return item["file"], f"完成 {size} {quality} {time.time() - t0:.0f}s"
            err = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code in (400, 401, 403):
                break  # 参数或鉴权错误，重试没有意义
        except Exception as e:  # 网络抖动时重试
            err = str(e)[:200]
        time.sleep(3 * (attempt + 1))
    placeholder(out, size, Path(item["file"]).name)
    return item["file"], f"失败，已放占位图（{err}）"


def write_prompt_list(items: list[dict], base: Path) -> Path:
    md = base / "image_prompts.md"
    lines = ["# 图片提示词清单", "", "手动出图后，按“文件名”放到对应路径（覆盖占位图），再重新渲染即可。", "",
             "| 镜头 | 文件名 | 比例/尺寸 | 提示词 |", "|---|---|---|---|"]
    for it in items:
        p = it["prompt"].replace("|", "｜").replace("\n", " ")
        lines.append(f"| {it.get('shot', '')} | `{it['file']}` | {it.get('aspect', '16:9')}（{size_of(it.get('aspect', '16:9'))}） | {p} |")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md


def main() -> None:
    utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt")
    ap.add_argument("--out")
    ap.add_argument("--aspect", default="16:9", help="16:9 / 9:16 / 1:1 或 1536x1024 这样的尺寸")
    ap.add_argument("--batch", help="images.json 清单")
    ap.add_argument("--quality", default="medium", choices=["low", "medium", "high", "auto"])
    ap.add_argument("--ref", help="风格参考图（选定方案的样张）")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()

    if a.batch:
        base = Path(a.batch).resolve().parent
        items = load_json(a.batch)
    elif a.prompt and a.out:
        base = Path.cwd()
        items = [{"file": a.out, "prompt": a.prompt, "aspect": a.aspect}]
    else:
        ap.error("需要 --batch，或同时给 --prompt 和 --out")

    api, key, model = cfg()
    print(f"出图模型 {model if key else '（无 IMG_KEY，只生成占位图和提示词清单）'}，共 {len(items)} 张", flush=True)
    if not key or a.batch:
        print(f"提示词清单：{write_prompt_list(items, base)}", flush=True)
    with cf.ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        futs = [ex.submit(generate, it, base, a.quality, a.ref, a.overwrite) for it in items]
        for f in cf.as_completed(futs):
            name, status = f.result()
            print(f"  {name}: {status}", flush=True)


if __name__ == "__main__":
    main()
