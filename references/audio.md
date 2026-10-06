# 音频规则

## 时间轴的主导关系

| 有什么 | 由谁决定时间轴 |
|---|---|
| 只有旁白 | 旁白决定镜头时长（前留 0.3 秒，后留 0.5 秒），字幕跟随旁白 |
| 只有音乐 | 镜头切点对齐节拍（取最近的拍），结尾落在小节线 |
| 旁白 + 音乐 | 旁白决定时长，切点推到旁白结束后的下一拍，保证不切断说话；说话区间音乐压低（duck），前后各 8 帧平滑过渡 |
| 都没有 | 用分镜表的 duration，片子无音轨 |

音乐和成片长度不一致时的处理：
- 音乐比成片长：在小节处截断，按 `fade_out` 淡出
- 音乐比成片短：按整小节循环，timeline.py 会打印提示

上面这些规则都已在 timeline.py 和 Soundtrack.tsx 里实现，正常情况只需要配置 storyboard 的 `music`，不用改代码。

## edge-tts 音色

| 音色 | 特点 | 适合 |
|---|---|---|
| zh-CN-YunxiNeural | 男，年轻、阳光 | 科普、产品介绍（默认） |
| zh-CN-YunyangNeural | 男，新闻播音腔 | 正式、企业宣传 |
| zh-CN-YunjianNeural | 男，激昂 | 运动、热血、预告片 |
| zh-CN-XiaoxiaoNeural | 女，温暖、自然 | 生活、情感、教程 |
| zh-CN-XiaoyiNeural | 女，活泼 | 轻松、少儿、短视频 |
| zh-CN-YunxiaNeural | 男童 | 少儿内容 |
| zh-TW-HsiaoChenNeural / zh-HK-HiuMaanNeural | 台湾 / 粤语女声 | 对应地区 |
| en-US-AndrewNeural / en-US-EmmaNeural | 英文男 / 女，自然 | 英文旁白 |

- 查看全部音色：`edge-tts --list-voices`
- 语速：短视频常用 `+5%~+15%`，讲解类用 `+0%`
- 个别镜头需要换人说话时，在该镜头写 `voice`
- edge-tts 是在线服务，偶尔会断连。tts.py 已内置重试；如果仍然失败，直接重跑，它只会补生成失败的镜头

## 旁白文案

- 每个镜头的旁白一般 1~3 句，横屏每秒约 4.5 个汉字
- 数字、英文缩写、公式要写成读法，例如"三点一四"、"A I"、"a 的平方加 b 的平方"，否则 TTS 会读错。字幕同样取自 narration，读法和显示有冲突时以读法为准
- 句末带标点，字幕依靠标点断行

## 用户给的音频

- **整段旁白**：先运行 `analyze_audio.py speech public/audio/vo.mp3`，再在 storyboard 写 `voiceover.file`，并在各镜头 narration 中填入对应文字（可以从 `.txt` 转写结果里复制）。timeline.py 会按文字比例切分；切得不准时，给镜头加 `vo_start` / `vo_end`
- **音乐**：运行 `analyze_audio.py music`，从 `.analysis.json` 读出 BPM 和能量高点（peaks），可以把关键镜头（比如产品亮相）安排在能量高点上。音乐情绪（激昂、温暖、悬疑等）在方案中写出你的判断，由用户确认
  - 核对节拍：BPM 应是常见整数附近（如 120、128、90），`beats` 首拍应在 0~1 拍内，末拍接近时长。脚本按恒定速度铺网格，变速音乐（现场录音、古典）不适用
  - 不对时（例如 BPM 测成一半或两倍、网格偏移）：手动重写 `.analysis.json`，`beats` 为等间隔网格，`downbeats` 每 4 拍取一个，正好在小节线结束的循环素材把时长也加进 `downbeats`；原文件先备份
  - 音乐比片子短时按整小节循环，循环终点是文件结尾或之前最近的小节线
- **参考视频里的声音**：两种模式都可以直接分析视频文件

## 响度

finalize.py 用两遍 loudnorm 把成片统一到 -14 LUFS，真峰值 ≤ -1.5 dBTP，所以模板中的音量只需管相对关系：
- 音乐 `volume` 默认 0.5，`duck` 默认 0.3；纯音乐无旁白时设为 1.0
- 旁白听不清时，把 duck 调低到 0.2；音乐太弱时，把 volume 调高到 0.7
- 素材本身很轻、峰值又高时（loudnorm 受真峰值限制拉不上去，报告里响度低于 -15），先做一版压缩限幅的母带再用：
  `ffmpeg -i bgm.mp3 -af "acompressor=threshold=-20dB:ratio=3:attack=5:release=100,alimiter=limit=0.8" bgm_master.wav`，把 `.analysis.json` 复制一份改成同名
