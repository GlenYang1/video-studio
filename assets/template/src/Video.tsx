/**
 * 主合成：完全由 timeline.json 驱动。
 * - 每个镜头一个 <Sequence>，起止帧由 timeline.py 算好（旁白定时长、切点对齐节拍）
 * - 转场不缩短时间轴：前一镜头多保留 transitionFrames 帧垫在下面，后一镜头在上层做入场
 * - 旁白、音乐、字幕各自独立一层，和画面解耦
 */
import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import { Captions } from "./components/Captions";
import { Soundtrack } from "./components/Soundtrack";
import { TransitionIn } from "./components/TransitionIn";
import { renderShot } from "./shots";
import { theme, timeline } from "./theme";

export const Main: React.FC = () => {
  const { shots, fps } = timeline;
  return (
    <AbsoluteFill style={{ backgroundColor: theme.bg, fontFamily: theme.font, color: theme.fg }}>
      {shots.map((shot, i) => {
        const next = shots[i + 1];
        const tail = next && next.transition !== "cut" ? next.transitionFrames : 0;
        return (
          <Sequence
            key={shot.id}
            name={`${shot.id} ${shot.title || shot.visual}`.slice(0, 40)}
            from={shot.from}
            durationInFrames={shot.durationInFrames + tail}
            premountFor={fps}
          >
            <TransitionIn type={i === 0 ? "cut" : shot.transition} frames={shot.transitionFrames}>
              {renderShot(shot)}
            </TransitionIn>
          </Sequence>
        );
      })}
      <Captions />
      <Soundtrack />
    </AbsoluteFill>
  );
};
