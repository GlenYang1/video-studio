"""Blender 无界面辅助：检查模型、导出 GLB、渲染序列帧。导出和渲染走命令行，不经过 blender-mcp（MCP 导出容易超时）。

  python blender_tool.py inspect <模型.blend|.glb|.gltf|.fbx|.obj>
  python blender_tool.py export  <文件.blend> <输出.glb> [--no-anim]
  python blender_tool.py render  <文件.blend> <输出目录> [--start 1 --end 120] [--size 1920x1080] [--samples 64] [--engine eevee|cycles]
  python blender_tool.py script  <源模型.blend|.glb|…> <输出.blend> --py <编辑脚本.py>

inspect：输出对象/网格面数/材质/贴图/动画/尺寸，写 <文件>.inspect.json。用来判断能否直接进 @remotion/three：
  过亮/过暗看灯光，面数 > 50 万或贴图 > 4K 建议先在 Blender 里减面/压贴图，程序化材质导出 GLB 会丢失要先烘焙。
export：export_apply=False（不烘焙修改器）、导出动画、+Y 朝上，进 Remotion 后用 Model3D 镜头加载。
render：需要高质量画面（体积光、景深、复杂材质）的镜头在 Blender 里渲染成 PNG 序列（0001.png…），
  进 Remotion 用 ImageSequence 镜头，帧率与项目一致。
二次编辑（改材质、灯光、动画、镜头）用 blender-mcp 在打开的 Blender 里做，保存 .blend 后再用本脚本导出/渲染。
script：blender-mcp 没连上时的替代。后台打开/导入源模型，执行编辑脚本（可直接用 bpy），另存为输出 .blend，不覆盖源文件。
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import blender_exe, run, utf8_stdio  # noqa: E402

# 在 Blender 内部执行的代码（通过 --python 传入），参数从 sys.argv 的 "--" 之后读
INNER = r'''
import bpy, json, sys, os
argv = sys.argv[sys.argv.index("--") + 1:]
mode, src, out = argv[0], argv[1], argv[2]
opts = json.loads(argv[3]) if len(argv) > 3 else {}

def load(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".blend":
        return  # 已由命令行打开
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise SystemExit("不支持的格式：" + ext)

load(src)
scene = bpy.context.scene

if mode == "inspect":
    from mathutils import Vector
    meshes = [o for o in scene.objects if o.type == "MESH"]
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    for o in meshes:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
    dg = bpy.context.evaluated_depsgraph_get()
    faces = sum(len(o.evaluated_get(dg).data.polygons) for o in meshes)
    mats = []
    for m in bpy.data.materials:
        if not m.users:
            continue
        nodes = [n.bl_idname for n in m.node_tree.nodes] if m.use_nodes and m.node_tree else []
        procedural = [n for n in nodes if n.startswith("ShaderNodeTex") and n != "ShaderNodeTexImage"]
        mats.append({"name": m.name, "procedural_textures": sorted(set(procedural))})
    imgs = [{"name": i.name, "size": list(i.size)} for i in bpy.data.images if i.users and i.size[0]]
    acts = [{"name": a.name, "frames": [round(a.frame_range[0]), round(a.frame_range[1])]} for a in bpy.data.actions]
    info = {
        "file": src,
        "objects": [{"name": o.name, "type": o.type} for o in scene.objects][:80],
        "object_count": len(scene.objects),
        "mesh_count": len(meshes),
        "faces": faces,
        "size": [round(v, 3) for v in (hi - lo)] if meshes else None,
        "materials": mats,
        "images": imgs,
        "max_texture": max([max(i["size"]) for i in imgs], default=0),
        "actions": acts,
        "has_armature": any(o.type == "ARMATURE" for o in scene.objects),
        "cameras": [o.name for o in scene.objects if o.type == "CAMERA"],
        "lights": [{"name": o.name, "type": o.data.type, "energy": round(o.data.energy, 1)} for o in scene.objects if o.type == "LIGHT"],
        "frame_range": [scene.frame_start, scene.frame_end],
        "fps": scene.render.fps,
        "render_engine": scene.render.engine,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

elif mode == "export":
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_apply=False,
                              export_animations=opts.get("anim", True), export_yup=True)

elif mode == "script":
    exec(compile(open(opts["py"], encoding="utf-8").read(), opts["py"], "exec"), {"__name__": "__main__", "bpy": bpy})
    bpy.ops.wm.save_as_mainfile(filepath=out)

elif mode == "render":
    r = scene.render
    if opts.get("engine") == "cycles":
        r.engine = "CYCLES"
        scene.cycles.samples = opts.get("samples", 64)
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.compute_device_type = "OPTIX"
            prefs.get_devices()
            for d in prefs.devices:
                d.use = True
            scene.cycles.device = "GPU"
        except Exception:
            pass
    elif opts.get("engine") == "eevee":
        r.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
    if opts.get("size"):
        r.resolution_x, r.resolution_y = opts["size"]
        r.resolution_percentage = 100
    if opts.get("fps"):
        r.fps = opts["fps"]
    if opts.get("start"):
        scene.frame_start = opts["start"]
    if opts.get("end"):
        scene.frame_end = opts["end"]
    if scene.camera is None:
        raise SystemExit("场景里没有相机：先用 blender-mcp 添加并设为活动相机")
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGBA" if r.film_transparent else "RGB"
    r.filepath = os.path.join(out, "")
    bpy.ops.render.render(animation=True)
'''


def call(mode: str, src: Path, out: str, opts: dict | None = None, timeout: int | None = None) -> None:
    exe = blender_exe()
    if not exe:
        sys.exit("找不到 Blender：在 ~/.clawsgo/mcp.json 的 blender.env.BLENDER_PATH 里配置路径")
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(INNER)
        script = f.name
    cmd = [exe, "--background", "--factory-startup"]
    if src.suffix.lower() == ".blend":
        cmd.append(str(src))
    cmd += ["--python", script, "--", mode, str(src), out, json.dumps(opts or {})]
    r = run(cmd, timeout=timeout, capture_output=mode != "render")
    Path(script).unlink(missing_ok=True)
    if r.returncode != 0:
        print((r.stderr or r.stdout or "")[-2500:])
        sys.exit(f"Blender {mode} 失败")


def main() -> None:
    utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["inspect", "export", "render", "script"])
    ap.add_argument("src")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--no-anim", action="store_true")
    ap.add_argument("--start", type=int)
    ap.add_argument("--end", type=int)
    ap.add_argument("--fps", type=int)
    ap.add_argument("--size", help="1920x1080")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--engine", choices=["eevee", "cycles"])
    ap.add_argument("--py", help="script 模式要执行的编辑脚本")
    a = ap.parse_args()
    src = Path(a.src).resolve()
    if not src.exists():
        sys.exit(f"文件不存在：{src}")

    if a.mode == "inspect":
        out = Path(a.out or str(src) + ".inspect.json").resolve()
        call("inspect", src, str(out), timeout=300)
        info = json.loads(out.read_text(encoding="utf-8"))
        print(f"{src.name}：{info['object_count']} 个对象，{info['mesh_count']} 个网格，{info['faces']:,} 面，"
              f"尺寸 {info['size']}，最大贴图 {info['max_texture']}px")
        print(f"  动画：{[x['name'] for x in info['actions']] or '无'}  骨骼：{'有' if info['has_armature'] else '无'}  "
              f"相机：{info['cameras'] or '无'}  灯光：{len(info['lights'])} 个")
        proc = [m["name"] for m in info["materials"] if m["procedural_textures"]]
        tips = []
        if info["faces"] > 500_000:
            tips.append("面数超过 50 万，网页渲染会慢：用 blender-mcp 加 Decimate 后再导出")
        if info["max_texture"] > 4096:
            tips.append("有超过 4K 的贴图，建议缩到 2K")
        if 0 < info["faces"] < 5_000:
            tips.append(f"只有 {info['faces']} 面，近景/特写会看到明显棱面：用 script 模式细分 + 平滑着色（见 references/3d.md）")
        if info["actions"]:
            tips.append("模型自带动画，Model3D 默认播放第 0 段；不需要时在 props 里写 clip: false")
        if proc:
            tips.append(f"材质 {proc} 用了程序化纹理，导出 GLB 会丢失：先烘焙成图片贴图，或改走 Blender 渲染序列帧")
        for t in tips:
            print("  建议：" + t)
        print(f"详情：{out}")
    elif a.mode == "export":
        if src.suffix.lower() != ".blend":
            sys.exit("export 只接受 .blend；.glb/.gltf 可以直接放进 public/models 使用")
        out = Path(a.out or src.with_suffix(".glb")).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        call("export", src, str(out), {"anim": not a.no_anim}, timeout=900)
        print(f"已导出 {out}（{out.stat().st_size / 1e6:.1f} MB）")
    elif a.mode == "script":
        if not (a.out and a.py):
            sys.exit("用法：blender_tool.py script <源模型> <输出.blend> --py <编辑脚本.py>")
        out = Path(a.out).resolve()
        if out == src:
            sys.exit("输出不能覆盖源文件，换一个 .blend 路径")
        out.parent.mkdir(parents=True, exist_ok=True)
        call("script", src, str(out), {"py": str(Path(a.py).resolve())}, timeout=900)
        print(f"已执行 {a.py} 并另存为 {out}；接着用 export 导出 GLB 或 render 渲染")
    else:
        if not a.out:
            sys.exit("render 需要输出目录，如 public/renders/S03")
        out = Path(a.out).resolve()
        out.mkdir(parents=True, exist_ok=True)
        opts = {"start": a.start, "end": a.end, "fps": a.fps, "samples": a.samples, "engine": a.engine}
        if a.size:
            opts["size"] = [int(v) for v in a.size.lower().split("x")]
        call("render", src, str(out), opts)
        n = len(list(out.glob("*.png")))
        print(f"已渲染 {n} 帧到 {out}；Remotion 里用 ImageSequence 镜头：props {{\"frames\": \"renders/{out.name}\", \"count\": {n}}}")


if __name__ == "__main__":
    main()
