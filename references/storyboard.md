# storyboard.json 字段与镜头组件

`storyboard.json` 是项目唯一的内容来源。`timeline.py` 根据它，加上配音时长和音乐节拍，生成 `src/timeline.json`。timeline.json 不要手改。
改了分镜表后重跑 `tts.py`（文案有改动时）和 `timeline.py`。

## 顶层字段

```json
{
  "title": "成片标题（也是输出文件名）",
  "fps": 30, "width": 1920, "height": 1080,
  "style": {"bg": "#0f1115", "fg": "#f5f5f7", "accent": "#4f8cff", "muted": "rgba(245,245,247,.65)", "font": "Noto Sans SC"},
  "voice": {"name": "zh-CN-YunxiNeural", "rate": "+0%", "volume": "+0%", "pitch": "+0Hz"},
  "voiceover": {"file": "audio/vo.mp3"},
  "music": {"file": "audio/bgm.mp3", "volume": 0.5, "duck": 0.3, "start": 0, "fade_out": 2.0},
  "captions": true,
  "caption_max_chars": 18,
  "shots": []
}
```

| 字段 | 说明 |
|---|---|
| style | 全片配色和字体。来源可以是参考视频的 `summary.json` 主色，也可以从选定样张取色（Frameloop `get_color_palette`）。font 不写时用项目自带的 Noto Sans SC |
| voice | edge-tts 音色和语速，音色表见 audio.md |
| voiceover | 只在用户给了整段旁白音频时写，此时不跑 tts.py |
| music | volume 是音乐基础音量；duck 是说话时音乐压到的比例（0.3 表示压到 30%）；start 表示从音乐第几秒开始用（用来跳过前奏）；fade_out 是结尾淡出秒数 |
| captions | 设为 false 关闭字幕。没有旁白时自动关闭 |
| caption_max_chars | 每行字幕的最大字数。横屏默认 18，竖屏默认 12 |
| style.reference | 记录风格参考图路径（如 refs/style.png），只做备忘，出图时用 `--ref` 传入 |

## 镜头字段

```json
{"id": "S03", "type": "3d", "component": "Model3D", "duration": 4, "transition": "fade", "transition_frames": 12,
 "title": "大标题", "text": "副标题/说明文字", "visual": "画面描述（给自己看，也写进提示词清单）",
 "narration": "这个镜头的旁白文案。", "voice": "zh-CN-XiaoxiaoNeural",
 "props": {"model": "models/robot.glb", "orbit": 45}}
```

- `id`：S01、S02…，同时用作配音文件名，不要改动已经生成配音的 id
- `type`：`2d` / `3d` / `manim` / `mixed`。preview_sheet.py 的"过暗"检查只对 3d 和 mixed 生效
- `duration`：期望的最短秒数。有旁白时，镜头时长等于旁白时长 + 0.8 秒，取它和 duration 中较大的值；有音乐时再对齐到节拍
- `transition`：可选 `cut`（默认）、`fade`、`slide`、`wipe`、`zoom`。指的是本镜头怎样进入，过渡期间和上一镜头重叠
- `narration`：旁白文案。字幕从这里取标点和断句，配音所用的文本也是这一段
- `check_at`：preview_sheet 在镜头内的取帧位置（0~1，默认 0.6），标题后出现的镜头可设 0.9
- `title` 里写 `
` 可以手动换行
- `vo_start` / `vo_end`：只在用户给的整段旁白自动对齐不准时，手动指定这个镜头对应的秒数
- 素材路径一律相对于 `public/`，例如 `images/s01.png`

## 镜头组件（`component` 留空时按规则自动选）

自动选择的顺序：
1. type 为 3d：props 里有 frames 时用 ImageSequence，否则用 Model3D
2. type 为 manim：用 ManimClip
3. props 里有 video：用 VideoClip
4. props 里有 points：用 Points
5. props 里有 image：用 ImageShot
6. 都不满足：用 TitleCard

| 组件 | props | 用途 |
|---|---|---|
| TitleCard | image?, dim?（0~1）, kicker?（小标题）, align?（left/center） | 片头、章节标题、纯文字镜头；竖屏字号自动放大 |
| ImageShot | image, zoom?（默认 0.08）, dim?, position?（bottom/center/top）, align?（横屏默认 left、竖屏 center）, layer?（透明 PNG）, layerFrom?（帧） | AI 出图或用户图片，自带 Ken Burns 推拉效果；layer 叠放抠图后的主体 |
| Points | points[], image?（侧边图）, stagger?（帧） | 要点逐条入场 |
| VideoClip | video, trimBefore?（秒）, volume?（默认静音）, fit? | 实拍素材、Blender 输出的 mp4 |
| ManimClip | video, bg?（透明片段下面的底图）, fit?, rate? | Manim 片段；镜头比片段长时停在最后一帧 |
| Model3D | model, clip?（false 关闭自带动画）, orbit?, from?, distance?, height?, push?, light?, target?, lift?, bg?, ground? | GLB 模型，参数详见 3d.md |
| ImageSequence | frames（目录）, count, start?, digits?, ext?, bg? | Blender 渲染的 PNG 序列 |

文字统一取镜头的 `title` 和 `text` 字段。组件会自动避开底部字幕区（captionSafe），所以不要把正文放在画面最下方。

## 写定制组件

通用组件满足不了时（数据图表、复杂 MG 动画、产品界面演示等），在 `src/shots/` 新建组件，并在 `src/shots/index.tsx` 的 `SHOTS` 里登记，然后在镜头里写 `"component": "名字"`。

- 组件签名为 `React.FC<ShotProps>`。镜头参数从 `shot.props` 读取，帧号用 `useCurrentFrame()`，帧号相对镜头起点
- 颜色和字体用 `theme`，尺寸乘以 `unit`（以 1080 短边为基准），竖屏时用 `isPortrait` 调整布局
- 所有动画都由帧号驱动（interpolate / spring），不要用 CSS transition 和 setTimeout
- 图片用 `<Img>`，视频和音频用 `@remotion/media`。素材路径交给 `src()`（即 `staticFile`）
- 写完运行 `npx tsc --noEmit` 做类型检查。写之前先读 remotion-best-practices skill 中对应的规则文件

## images.json（批量出图清单，放在项目根目录）

```json
[
  {"file": "public/images/s02_bg.png", "prompt": "……", "aspect": "16:9", "shot": "S02"},
  {"file": "public/images/s04_product.png", "prompt": "……，透明背景", "aspect": "1:1", "shot": "S04", "transparent": true}
]
```

写提示词的要点：
- 先写主体和画面，再写风格。风格描述与选定方案一致，`--ref refs/style.png` 负责统一画风
- 需要叠加文字的画面，要在提示词里留出构图空间（例如"左侧留白"），并写明"画面中不要出现文字"，因为 AI 生成的文字常常是乱码
- 竖屏片子用 9:16 出图，不要先出横图再裁切
