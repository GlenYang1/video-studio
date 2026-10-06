# 检查与修复（最多 2 轮）

只做两项检查：渲染前看联系表，渲染后用 ffprobe 核对技术参数。目的是在不花大量 token 的前提下，抓住最常见的问题。

## 画面检查：preview_sheet.py

脚本为每个镜头渲染 1 帧（取镜头 60% 处，这时入场动画已结束），拼成 `out/check/contact_sheet.jpg`，并给出自动提示：
- **3D 主体过暗**：3d/mixed 镜头中，亮部（95 分位亮度）不足 70
- **画面近乎纯色**：素材很可能没有加载出来，比如路径写错或文件缺失
- **抽帧失败**：该帧没有渲染出来
- **仍有占位图**：public/ 下还有未替换的占位图

用 Read 看联系表，逐个镜头对照分镜表，重点检查：

| 问题 | 怎么修 |
|---|---|
| 文字被裁切、溢出画面、换行难看 | 缩短 title/text；或者在定制组件中调小字号；竖屏注意每行字数 |
| 文字和字幕重叠 | ImageShot 的 position 改为 center/top；定制组件要留出 captionSafe |
| 素材缺失或纯色 | 检查 props 路径（相对 public/）和文件是否存在；出图失败时重跑 gen_image.py |
| 3D 过暗 | 调 light 到 1.5~2，或者给模型加灯光后重新导出，见 3d.md |
| 3D 穿模或出框 | 调整 distance、height、from |
| 画面和分镜不符 | 改 props，或者为该镜头写定制组件 |
| 风格前后不一致 | 用 `--ref refs/style.png --overwrite` 重新生成偏离风格的图 |

修完重跑 preview_sheet.py，复查一次。第 2 轮之后仍然没有解决的问题，不再继续修，在交付说明中如实写出。

## 技术检查：finalize.py

渲染成片后用 ffprobe 核对以下项目：
- 时长：与 timeline 相比误差不超过 1 帧 + 0.05 秒
- 分辨率、帧率
- 编码：h264 / yuv420p
- 音轨：是否存在
- 音画时长差：≤ 0.1 秒
- 响度：-14 ±1 LUFS，真峰值 ≤ -1.5 dBTP

结果写入 `out/check_report.md`。任意一项不通过时，退出码为 1，报告的结论部分会给出修复方向：
- **时长不符**：通常是 Root.tsx 没有使用 timeline.json，或者改完分镜后没有重跑 timeline.py
- **缺少音轨**：检查 `public/audio` 下的文件，以及 storyboard 中的路径
- **响度不达标**：通常是音频过于安静，或者大部分时间是静音（loudnorm 拉不上去）。检查音乐 volume、旁白是否生成成功；素材峰值高时先压缩限幅（见 audio.md「响度」）
- **只调整了音频参数**：音频在 Remotion 中混合，所以改了 storyboard 的 music/voice 后，需要重跑 timeline.py 和完整的 finalize.py；`--skip-render` 只适用于 raw.mp4 本身没问题、只需重新标准化响度的情况

## 修复时的原则

- 改 storyboard.json，或改组件 props，不要手改 timeline.json
- 修改文案后按顺序重跑：tts.py → timeline.py → preview_sheet.py
- 每轮修复都要把这一轮的所有问题一起改完，再重新检查，不要改一个查一次
