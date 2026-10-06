"""音频分析：音乐测 BPM/节拍/小节/能量，人声用本地 faster-whisper 转写。

  python analyze_audio.py music <音频或视频文件> [--out x.analysis.json]
  python analyze_audio.py speech <音频或视频文件> [--lang zh] [--model small] [--out x.words.json]

music 输出 <文件>.analysis.json：duration、bpm、beats、downbeats、bar、energy（每秒 0~1）、peaks（能量高点）。
speech 输出 <文件>.words.json（字/词级时间戳）、<文件>.srt、<文件>.txt。
结果默认写在源文件旁边，timeline.py 会按这个命名自动读取。
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import MODELS_DIR, find_tool, run, save_json, utf8_stdio  # noqa: E402


def decode_wav(src: Path, sr: int) -> Path:
    """统一用 ffmpeg 解码成单声道 wav：mp4/mov/m4a 都能处理，也绕开 librosa 的格式限制。"""
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        sys.exit("缺少 ffmpeg，请先运行 env_check.py")
    out = Path(tempfile.gettempdir()) / f"vs_{src.stem}_{sr}.wav"
    r = run([ffmpeg, "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", str(sr), str(out)])
    if r.returncode != 0:
        sys.exit(f"ffmpeg 解码失败：{r.stderr[:300]}")
    return out


def analyze_music(src: Path, out: Path) -> dict:
    import librosa
    import numpy as np

    wav = decode_wav(src, 22050)
    y, sr = librosa.load(str(wav), sr=22050, mono=True)
    duration = len(y) / sr
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset, sr=sr, units="frames")
    raw = librosa.frames_to_time(beat_frames, sr=sr)
    bpm = float(np.atleast_1d(tempo)[0])

    # beat_track 的拍点会整体偏晚，首尾也常常漏拍。这里改用等间隔网格：
    # 1. 对检测到的拍点做线性拟合，得到周期，比 tempo 的估计更准
    # 2. 用起音点（backtrack）校正网格的相位
    # 3. 把网格铺满整首。适用于速度恒定的配乐，绝大多数商用/AI 配乐都是这种
    beats = raw
    if len(raw) >= 4:
        period = float(np.median(np.diff(raw)))
        k = np.round((raw - raw[0]) / period)
        period, phase = (float(v) for v in np.polyfit(k, raw, 1))
        onsets = librosa.onset.onset_detect(onset_envelope=onset, sr=sr, backtrack=True, units="time")
        grid = phase + period * np.arange(-int(phase / period) - 1, int((duration - phase) / period) + 2)
        if len(onsets):
            near = [onsets[np.argmin(abs(onsets - g))] - g for g in grid if abs(onsets - g).min() < period * 0.25]
            grid = grid + (float(np.median(near)) if near else 0.0)
        beats = np.clip(grid[(grid > -period * 0.25) & (grid < duration + period * 0.25)], 0, duration)
        bpm = 60 / period

    # 估计强拍：按 4/4 拍，把节拍分成 4 组，起音强度总和最大的那组当小节起点
    downbeats = beats
    if len(beats) >= 8:
        idx = np.minimum(librosa.time_to_frames(beats, sr=sr), len(onset) - 1)
        strength = onset[idx]
        phase = int(np.argmax([strength[k::4].sum() for k in range(4)]))
        downbeats = beats[phase::4]
    # 最后一个强拍之后正好一小节就结束的音乐（循环素材常见），把文件结尾也记为小节线，timeline.py 用它来整首循环
    bar = 4 * 60 / bpm if bpm else 0
    if bar and len(downbeats) and abs(duration - (downbeats[-1] + bar)) < bar / 16:
        downbeats = np.append(downbeats, duration)

    rms = librosa.feature.rms(y=y, hop_length=sr // 10)[0]  # 每 0.1 秒一个点
    per_sec = [float(rms[i:i + 10].mean()) for i in range(0, len(rms), 10)]
    peak = max(per_sec) or 1.0
    energy = [round(v / peak, 3) for v in per_sec]
    # 能量高点：用来安排高潮镜头
    order = sorted(range(len(energy)), key=lambda i: -energy[i])
    peaks: list[int] = []
    for i in order:
        if all(abs(i - p) >= 8 for p in peaks):
            peaks.append(i)
        if len(peaks) == 3:
            break

    data = {
        "file": str(src),
        "duration": round(duration, 3),
        "bpm": round(bpm, 1),
        "bar": round(4 * 60 / bpm, 3) if bpm else None,
        "beats": [round(float(b), 3) for b in beats],
        "downbeats": [round(float(b), 3) for b in downbeats],
        "energy": energy,
        "peaks": sorted(peaks),
    }
    save_json(out, data)
    wav.unlink(missing_ok=True)
    print(f"时长 {data['duration']}s，BPM {data['bpm']}，小节 {data['bar']}s，"
          f"节拍 {len(data['beats'])} 个，能量高点在 {data['peaks']} 秒附近")
    print(f"已写入 {out}")
    return data


def transcribe(src: Path, out: Path, lang: str, model_name: str) -> None:
    from faster_whisper import WhisperModel

    local = MODELS_DIR / f"faster-whisper-{model_name}"
    if not (local / "model.bin").exists():
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    model_ref = str(local) if (local / "model.bin").exists() else model_name

    model = None
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            model = WhisperModel(model_ref, device="cuda", compute_type="float16")
    except Exception:
        model = None  # 没装 CUDA 运行库时回退 CPU
    if model is None:
        model = WhisperModel(model_ref, device="cpu", compute_type="int8")

    wav = decode_wav(src, 16000)
    prompt = "以下是普通话的句子，使用简体中文和标点。" if lang.startswith("zh") else None
    segments, info = model.transcribe(str(wav), language=lang, word_timestamps=True, vad_filter=True,
                                      initial_prompt=prompt)
    words, lines = [], []
    for seg in segments:
        lines.append((seg.start, seg.end, seg.text.strip()))
        for w in seg.words or []:
            words.append({"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)})
    wav.unlink(missing_ok=True)

    save_json(out, {"file": str(src), "language": info.language, "duration": round(info.duration, 3),
                    "words": words, "segments": [{"start": round(s, 3), "end": round(e, 3), "text": t}
                                                  for s, e, t in lines]})

    def ts(t: float) -> str:
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    stem = str(out).removesuffix(".words.json")
    Path(stem + ".srt").write_text("\n".join(f"{i}\n{ts(s)} --> {ts(e)}\n{t}\n" for i, (s, e, t) in enumerate(lines, 1)),
                                   encoding="utf-8")
    Path(stem + ".txt").write_text("\n".join(f"[{s:6.2f}-{e:6.2f}] {t}" for s, e, t in lines), encoding="utf-8")
    print(f"语言 {info.language}，时长 {info.duration:.1f}s，{len(lines)} 句，{len(words)} 个词")
    print(f"已写入 {out}、{stem}.srt、{stem}.txt")


def main() -> None:
    utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["music", "speech"])
    ap.add_argument("file")
    ap.add_argument("--out")
    ap.add_argument("--lang", default="zh")
    ap.add_argument("--model", default=os.environ.get("VIDEO_STUDIO_WHISPER", "small"))
    a = ap.parse_args()
    src = Path(a.file).resolve()
    if not src.exists():
        sys.exit(f"文件不存在：{src}")
    if a.mode == "music":
        analyze_music(src, Path(a.out) if a.out else Path(str(src) + ".analysis.json"))
    else:
        transcribe(src, Path(a.out) if a.out else Path(str(src) + ".words.json"), a.lang, a.model)


if __name__ == "__main__":
    main()
