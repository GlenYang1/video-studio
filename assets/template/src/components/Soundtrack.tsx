/**
 * 声音层：
 * - 旁白：每镜头一段，位置和裁切由 timeline 的 vo 字段给出
 * - 音乐：按 segments 播放（够长时截断，不够时整小节循环），全片淡入淡出
 * - 闪避：说话区间（duckRanges）音乐降到 volume × duck，前后 8 帧平滑过渡
 * 成片响度由 finalize.py 统一标准化到 -14 LUFS，这里只管相对音量。
 */
import React from "react";
import { Audio } from "@remotion/media";
import { getInputProps, interpolate, Sequence, staticFile } from "remotion";
import { timeline } from "../theme";

const RAMP = 8;

const duckGain = (f: number, duck: number): number => {
  let g = 1;
  for (const [s, e] of timeline.duckRanges) {
    g = Math.min(
      g,
      interpolate(f, [s - RAMP, s, e, e + RAMP], [1, duck, duck, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      }),
    );
  }
  return g;
};

export const Soundtrack: React.FC = () => {
  const { shots, music, durationInFrames } = timeline;
  // preview_sheet.py 抽帧渲染（不连续的帧）时不挂载声音，否则 Remotion 内联混音会写入越界
  if (getInputProps().preview) return null;
  return (
    <>
      {shots.map((s) =>
        s.vo ? (
          <Sequence
            key={`vo-${s.id}`}
            name={`旁白 ${s.id}`}
            from={s.vo.from}
            durationInFrames={s.vo.durationInFrames}
            layout="none"
          >
            <Audio src={staticFile(s.vo.src)} trimBefore={s.vo.trimBefore || undefined} />
          </Sequence>
        ) : null,
      )}
      {music
        ? music.segments.map((seg, i) => (
            <Sequence
              key={`bgm-${i}`}
              name={`音乐 ${i + 1}`}
              from={seg.from}
              durationInFrames={seg.durationInFrames}
              layout="none"
            >
              <Audio
                src={staticFile(music.src)}
                trimBefore={seg.trimBefore || undefined}
                volume={(f) => {
                  const g = seg.from + f; // 换算成全片帧号
                  const fade = interpolate(
                    g,
                    [0, music.fadeInFrames, durationInFrames - music.fadeOutFrames, durationInFrames],
                    [0, 1, 1, 0],
                    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
                  );
                  return music.volume * fade * duckGain(g, music.duck);
                }}
              />
            </Sequence>
          ))
        : null}
    </>
  );
};
