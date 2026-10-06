---
name: video-studio
description: 制作 2D / 3D / 混合视频的完整流程：需求收集 → 参考素材分析 → 2~4 个方案（带 AI 样张）→ 分镜表 → Remotion 制作（AI 出图、@remotion/three 3D 模型、Blender 二次编辑与渲染、Manim 公式动画、ps-mcp 修图）→ edge-tts 配音与字幕、音乐踩点与闪避 → 联系表 + ffprobe 检查 → 交付 mp4。只要用户想做视频、短片、宣传片、讲解视频、科普动画、产品展示、片头、MG 动画、数学/物理原理动画、带配音字幕的视频，或者给了参考视频/模型/音乐让你"做一个类似的视频"，都使用这个 skill，即使用户没提 Remotion 或具体工具。
---

# Video Studio：2D / 3D / 混合视频

脚本都在本 skill 的 `scripts/` 下（`$VS` 即本 skill 目录，通常是 `~/.clawsgo/skills/video-studio`），用 `python` 运行，Windows 下先设 `PYTHONIOENCODING=utf-8`。
每个视频一个独立项目目录，`storyboard.json`（分镜表）是唯一的内容来源，时间轴、配音、字幕都从它生成。

整体顺序：环境检查 → 收集需求 → 判断类型 → 方案 → 分镜表 → 素材 → 音频与时间轴 → 画面检查 → 渲染与技术检查 → 交付。
方案和分镜表两处要等用户确认，其余步骤自动推进。
项目目录在收集完需求后就用 `new_project.py` 建好（第 4 步的命令），这样样张、参考分析都能直接放进项目。
本 skill 的规定优先于 remotion-best-practices 等通用 skill（例如不主动启动 Studio）。

## 0. 环境检查（只在首次运行）

```bash
python $VS/scripts/env_check.py
```

`~/.clawsgo/video-studio/env_ok.json` 存在时脚本秒退，直接进入下一步。缺失项会用国内镜像自动安装（npmmirror、阿里云/清华 pip、hf-mirror），
最后输出环境状态清单。Blender、Photoshop 不自动装，清单里提示即可；GitHub 下载失败时让用户配置代理后重跑。
共享目录 `~/.clawsgo/video-studio/` 里放 ffmpeg、渲染用 Chrome、Whisper 模型，所有项目共用。

## 1. 收集需求

需要知道：内容主题、时长、画幅（16:9 / 9:16 / 1:1）、用途（平台）、语言、旁白音色偏好、有没有素材。
缺的信息**一次问清**（一条消息列出所有问题，给出默认值，用户只需改不同意的项），不要来回挤牙膏。

用户上传的素材放进 `<项目>/refs/`，按类型处理：

| 素材 | 处理 |
|---|---|
| 参考视频 | `python $VS/scripts/ref_video.py <视频> --out <项目>/refs/<名>`：Frameloop 抽关键帧（不用 Replicate 密集模式）、拼联系表、取主色、统计镜头切点。用 Read 看 `grid.jpg` 一张图，总结配色、字体风格、镜头节奏（平均镜头时长）、运镜、内容结构 |
| 图片 | 直接 Read 看；要抠图/调色/合成时用 ps-mcp（见第 8 步） |
| .glb / .gltf | `python $VS/scripts/blender_tool.py inspect <文件>` 看面数、动画、贴图，判断能否直接进 Remotion |
| .blend | 同上 inspect；需要改材质/灯光/动画时用 blender-mcp |
| 人声 | `python $VS/scripts/analyze_audio.py speech <文件>`：本地 faster-whisper 转写，得到字级时间戳 |
| 音乐 | `python $VS/scripts/analyze_audio.py music <文件>`：librosa 测 BPM、时长、节拍点（等间隔网格，已校准相位）、小节线、能量高点。踩点是这类需求的核心，看一眼输出的 BPM 和首尾拍点是否合理，不对时按 `references/audio.md` 修正。音乐情绪不做自动判断，在方案里写出你的理解，由用户确认 |

## 2. 判断类型

- **2D**：图文、MG 动画、AI 出图、实拍素材剪辑 → Remotion
- **3D**：有模型或需要立体展示 → `@remotion/three`；要体积光、景深、复杂材质的镜头走 Blender 渲染序列帧
- **混合**：按镜头分别标注
- 涉及数学公式、几何证明、函数图像、物理过程的镜头标记为 **Manim 片段**

## 3. 方案（等用户选择）

先头脑风暴，再在对话里用**纯文字选择题**给 2~4 个方案，格式见 `references/plan_template.md`。每个方案包含：
参考图、风格、关键镜头内容、需要生成的图片、需要的 3D 模型、音频方案（含旁白音色），并标注推荐项。

每个方案配 1 张低分辨率样张，样张的作用是让用户直观比较风格：

```bash
python $VS/scripts/gen_image.py --prompt "<风格+关键画面描述>" --out <项目>/refs/plan_A.png --aspect <画幅> --quality low
```

多个方案的样张可以并行生成（每张约 20 秒）。没有 IMG_KEY 时脚本会生成占位图，方案改用文字描述风格。

用户选定后：
1. 把选中的样张复制为 `<项目>/refs/style.png`，后续**所有出图都用它做 `--ref`**，保证全片风格一致
2. 输出分镜表（Markdown 表格：镜头号、时长、类型、画面、旁白文案、素材），**等用户确认**后再开始制作。
   有时长要求又有旁白时，先把文案写进 storyboard.json 跑一遍 `tts.py` + `timeline.py` 拿到真实时长（按字数估算误差常到 25%），超出要求 15% 就先精简文案，再把分镜表给用户

## 4. 建项目、写分镜表

```bash
python $VS/scripts/new_project.py <项目目录> --title "<标题>" --aspect 16:9
```

模板自带通用镜头组件，绝大多数镜头只靠写 `storyboard.json` 就能完成，不用写代码。字段说明和组件参数见 `references/storyboard.md`。
需要定制画面时在 `src/shots/` 新建组件并在 `src/shots/index.tsx` 登记，写 Remotion 代码前先读 remotion-best-practices skill。

## 5. 素材

**2D 出图**（OpenAI 兼容接口，读取 IMG_API / IMG_KEY / IMG_MODEL，默认 gpt-image-2.5-flare）：
把分镜里所有要生成的图写进 `<项目>/images.json`，一次批量生成：

```bash
python $VS/scripts/gen_image.py --batch <项目>/images.json --ref <项目>/refs/style.png
```

没有 IMG_KEY 时自动生成同尺寸占位图 + `image_prompts.md` 提示词清单（文件名、比例、提示词、对应镜头）。告诉用户手动出图后放入同名文件，重新渲染即可；
已有真图不会被覆盖，占位图在有 key 后重跑会自动补出。

**3D**：
- `.glb/.gltf` 放 `public/models/`，镜头用 `Model3D` 组件（自动居中缩放、相机环绕/推近、帧驱动动画）
- 需要二次编辑（材质、灯光、动画、镜头）：用 blender-mcp 在打开的 Blender 里改，保存 .blend，再
  `python $VS/scripts/blender_tool.py export <文件.blend> <项目>/public/models/<名>.glb`；
  blender-mcp 没连上时，把 bpy 编辑代码写成脚本，用 `blender_tool.py script <源模型> <项目>/blender/<名>.blend --py <脚本.py>` 在后台执行
- 高质量镜头：`python $VS/scripts/blender_tool.py render <文件.blend> <项目>/public/renders/<镜头id> --start 1 --end <帧数> --size 1920x1080 --fps 30`，镜头用 `ImageSequence`
- 细节和坑见 `references/3d.md`

**Manim**：场景脚本写在 `<项目>/manim/`（先读 manim skill 的字体和 LaTeX 说明），然后

```bash
python $VS/scripts/manim_clip.py <项目> <项目>/manim/<脚本>.py <场景类> [--transparent]
```

需要叠加在其他画面上时加 `--transparent`（输出 WebM 带透明通道），镜头用 `ManimClip`。
竖屏项目脚本会自动把坐标系设成 宽 8 × 高 14.2 单位，场景按这个宽度排版（长公式用 `scale_to_fit_width(7)`）。
preview_sheet 每镜只看 1 帧，Manim 动画过程要单独抽几帧看：`ffmpeg -i public/manim/X.mp4 -vf fps=2,scale=-2:360,tile=6x1 -frames:v 1 out/check/X.jpg`。

## 6. 音频与时间轴

1. **配音**：用户没给旁白音频时，用 edge-tts 按分镜表旁白文案生成，同时得到字级时间戳，字幕直接由它生成，不再跑 Whisper：
   ```bash
   python $VS/scripts/tts.py <项目>
   ```
   用户给了整段旁白：在 storyboard 里写 `"voiceover": {"file": "audio/vo.mp3"}`，先跑 `analyze_audio.py speech public/audio/vo.mp3`。
2. **音乐**：放 `public/audio/`，写进 storyboard 的 `music`，先跑 `analyze_audio.py music`。
3. **时间轴**：
   ```bash
   python $VS/scripts/timeline.py <项目>
   ```
   规则已内置：旁白决定镜头时长，字幕跟随旁白；有音乐时切点对齐节拍（不切断说话），结尾落在小节线，音乐在小节处截断或整小节循环并淡出；
   旁白和音乐同时有时说话区间音乐压低。改了分镜表文案后重跑 tts.py（只重新生成改动的镜头）和 timeline.py。
   成片响度 -14 LUFS 在 finalize 阶段统一处理。音色、规则细节见 `references/audio.md`。

## 7. 检查（有问题自动修复，最多 2 轮）

**画面检查（整片渲染前）**：

```bash
python $VS/scripts/preview_sheet.py <项目>
```

每个镜头渲染 1 帧（默认镜头 60% 处，镜头可写 `check_at` 改位置）拼成联系表，并自动标出 3D 过暗、画面近乎纯色（素材没加载）、残留占位图。
自己用 `npx remotion render --frames=...` 抽帧时要加 `--props=<含 {"preview": true} 的 json 文件>`，否则声音层会让不连续帧渲染报错。用 Read 看 `out/check/contact_sheet.jpg` 这一张图，
对照分镜表检查：文字裁切/溢出、和字幕重叠、素材缺失、3D 过暗或穿模、画面和分镜不符。发现问题就改，再出一次联系表；两轮后仍有问题则在报告里写明。
（Frameloop MCP 的 render_preview 是均匀取帧且每帧重新打包，这里用 preview_sheet.py 代替，按镜头取帧、只打包一次。）

修复对照表见 `references/check.md`。

**技术检查（渲染后）**：

```bash
python $VS/scripts/finalize.py <项目>
```

渲染 H.264 成片 → 两遍 loudnorm 到 -14 LUFS → ffprobe 核对时长、分辨率、帧率、音轨、音画时长差、响度，写 `out/check_report.md`。
退出码非 0 时按报告修复后重跑；raw.mp4 本身没问题、只需重新标准化响度时加 `--skip-render`。

## 8. 随时可用的工具

- **ps-mcp（Photoshop）**：抠图（`photoshop_recipe_remove_background`）、调色、合成、扩图。先 `photoshop_ping` 确认连接，
  处理完导出 PNG 到 `public/images/`。抠好的主体可以用 `ImageShot` 的 `layer` 叠在背景上
- **blender-mcp**：检查和编辑场景，先读 blender-mcp skill；导出和渲染用 blender_tool.py 走命令行（MCP 导出容易超时）
- **Frameloop MCP**：`analyze_video`、`extract_frames_at_timestamps`（查看参考视频某几秒）、`get_color_palette`、`compare_frames`（参考帧与成片对比）
- **Manim**：公式、几何、函数图像片段，透明背景叠加

不要主动启动 Remotion Studio 等常驻服务，除非用户要求预览。

## 交付

```
<项目>/out/<标题>.mp4        成片
<项目>/out/check_report.md   检查报告（技术检查表 + 画面检查结论）
<项目>/                      工程文件（storyboard.json、src/、public/ 素材、manim/、blender/）
```

用 `mcp__clawsgo__deliver_files` 交付 mp4、检查报告、联系表；最后用几句话说明：成片规格、用了哪些工具做了哪些镜头、仍是占位图的素材（如有）、怎么修改
（改 storyboard.json → tts.py → timeline.py → finalize.py）。
