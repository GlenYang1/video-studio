# video-studio

一个用于 ClawsGO / Claude Code 的视频制作 skill，可以做 2D、3D 和混合视频。它把从需求到成片的流程都串起来了：

需求收集 → 参考素材分析 → 2~4 个方案（每个配 AI 样张）→ 分镜表 → Remotion 制作 → 配音、字幕、音乐踩点 → 联系表和 ffprobe 检查 → 交付 mp4

- **2D**：Remotion 镜头组件，包括标题卡、图片 Ken Burns、要点列表、视频片段。画面可以用 AI 出图
- **3D**：`@remotion/three` 加载 GLB 模型，支持相机环绕和推近，动画按帧驱动。需要高质量画面时走 Blender，可以二次编辑，也可以渲染序列帧
- **Manim**：公式、几何、函数图像片段，竖屏会自动适配坐标系，支持透明叠加
- **音频**：edge-tts 配音，字级时间戳直接生成字幕；librosa 分析节拍，切点对齐节拍；说话时音乐自动压低；两遍 loudnorm 把成片统一到 -14 LUFS
- **检查**：渲染前看联系表，渲染后用 ffprobe 核对技术参数。发现问题会自动修复，最多 2 轮

## 目录结构

```
video-studio/
├── SKILL.md              主流程（第 0~8 步）
├── references/           按需读取的细节文档
│   ├── plan_template.md  方案选择题与分镜表模板
│   ├── storyboard.md     storyboard.json 字段与镜头组件
│   ├── 3d.md             @remotion/three 与 Blender
│   ├── audio.md          配音、音乐踩点、响度
│   └── check.md          检查项与修复对照表
├── scripts/              Python 脚本（环境检查、出图、TTS、时间轴、检查、渲染）
└── assets/template/      Remotion 项目模板（每个视频复制一份）
```

## 安装

把整个 `video-studio` 目录复制到 skills 目录：

- ClawsGO：`~/.clawsgo/skills/video-studio/`
- Claude Code：`~/.claude/skills/video-studio/`

## 环境要求

| 依赖 | 说明 |
|---|---|
| Python 3.10+ | 必需 |
| Node.js 18+ | 必需，用于 Remotion |
| ffmpeg、渲染用 Chrome、Python 依赖包、Whisper 模型 | 首次运行时 `scripts/env_check.py` 会自动安装，优先走国内镜像（npmmirror、阿里云/清华 pip、hf-mirror） |
| Blender 4.x | 可选，3D 编辑和渲染用 |
| Photoshop + photoshop-mcp | 可选，抠图、调色用 |
| Frameloop MCP、blender-mcp | 可选，用于分析参考视频、编辑 Blender 场景 |

首次运行时，env_check.py 检查通过后会写入 `~/.clawsgo/video-studio/env_ok.json`，以后都跳过检查。目前自动安装只适配了 Windows。

AI 出图走 OpenAI 兼容接口，从环境变量读取配置。不要把 key 写进任何文件：

```
IMG_API=<接口地址>
IMG_KEY=<你的 key>
IMG_MODEL=gpt-image-2.5-flare   # 可选
```

没有配置 IMG_KEY 时，流程照样能走完：会生成占位图，并附上一份提示词清单。

## 使用

有三种方式触发：

- 直接描述需求，例如：`帮我做一个 30 秒的竖屏科普视频，讲勾股定理，中文旁白`
- 点名使用：`用 video-studio 帮我做……`
- 斜杠命令：`/video-studio <需求>`

流程只在两处停下来等你确认：**选方案**、**确认分镜表**。其余步骤会自动推进。

每个视频都有一个独立的项目目录，交付以下内容：

```
<项目>/out/<标题>.mp4        成片
<项目>/out/check_report.md   检查报告
<项目>/                      工程文件（storyboard.json、src/、public/、manim/、blender/）
```

想修改成片时，改 `storyboard.json`，然后按顺序重跑：`tts.py` → `timeline.py` → `finalize.py`。

## 评估结果（第 1 轮）

测了两个用例：一个竖屏 Manim 讲解视频，一个 3D 模型配合音乐踩点的展示视频。

| 配置 | 断言通过率 | 平均耗时 | 平均 token |
|---|---|---|---|
| 使用 skill | 10/10 | 约 37 分钟 | 约 19.3 万 |
| 不用 skill | 5/10 | 约 17 分钟 | 约 12.8 万 |

---

ClawsGO Science Agent
