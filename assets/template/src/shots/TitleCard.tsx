/**
 * 标题卡 / 纯文字镜头。
 * props: { image?: 背景图, dim?: 背景压暗 0~1, kicker?: 小标题, align?: "left"|"center" }
 */
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { Cover } from "../components/Media";
import { FadeUp, TextBlock } from "../components/Text";
import { isPortrait, theme, unit } from "../theme";
import type { ShotProps } from "../types";

export const TitleCard: React.FC<ShotProps> = ({ shot }) => {
  const frame = useCurrentFrame();
  const p = shot.props as { image?: string; dim?: number; kicker?: string; align?: "left" | "center" };
  const bar = interpolate(frame, [4, 22], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ backgroundColor: theme.bg }}>
      {p.image ? (
        <>
          <Cover file={p.image} zoom={0.06} />
          <AbsoluteFill style={{ backgroundColor: `rgba(0,0,0,${p.dim ?? 0.45})` }} />
        </>
      ) : (
        <AbsoluteFill
          style={{ background: `radial-gradient(circle at 30% 20%, ${theme.accent}33, transparent 60%)` }}
        />
      )}
      {p.kicker ? (
        <FadeUp style={{ position: "absolute", top: (isPortrait ? 220 : 90) * unit, width: "100%", textAlign: "center" }}>
          <span style={{ color: theme.accent, fontSize: (isPortrait ? 40 : 30) * unit, fontWeight: 700, letterSpacing: 6 * unit }}>
            {p.kicker}
          </span>
        </FadeUp>
      ) : null}
      <TextBlock title={shot.title} text={shot.text} align={p.align} bar={bar} />
    </AbsoluteFill>
  );
};
