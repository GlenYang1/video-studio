/**
 * 要点列表：逐条入场。
 * props: { points: string[], image?: 侧边图, stagger?: 每条间隔帧数（默认按镜头时长均分到前 60%） }
 */
import React from "react";
import { AbsoluteFill, Img, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { src } from "../components/Media";
import { captionSafe, isPortrait, theme, unit } from "../theme";
import type { ShotProps } from "../types";

export const Points: React.FC<ShotProps> = ({ shot }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = shot.props as { points: string[]; image?: string; stagger?: number };
  const n = Math.max(1, p.points.length);
  const stagger = p.stagger ?? Math.max(6, Math.floor((shot.durationInFrames * 0.6) / n));
  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.bg,
        flexDirection: isPortrait ? "column" : "row",
        padding: `${(isPortrait ? 140 : 90) * unit}px ${(isPortrait ? 70 : 120) * unit}px`,
        paddingBottom: captionSafe + 60 * unit,
        gap: 60 * unit,
        alignItems: "center",
      }}
    >
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 34 * unit }}>
        {shot.title ? (
          <div style={{ fontSize: (isPortrait ? 80 : 68) * unit, fontWeight: 800, marginBottom: 16 * unit }}>
            {shot.title}
          </div>
        ) : null}
        {p.points.map((t, i) => {
          const s = spring({ frame: frame - 6 - i * stagger, fps, config: { damping: 200 } });
          return (
            <div
              key={i}
              style={{
                display: "flex",
                gap: 22 * unit,
                alignItems: "baseline",
                opacity: s,
                transform: `translateX(${interpolate(s, [0, 1], [-40 * unit, 0])}px)`,
                fontSize: (isPortrait ? 50 : 44) * unit,
                lineHeight: 1.4,
              }}
            >
              <span style={{ color: theme.accent, fontWeight: 800 }}>{String(i + 1).padStart(2, "0")}</span>
              <span>{t}</span>
            </div>
          );
        })}
      </div>
      {p.image ? (
        <Img
          src={src(p.image)}
          style={{
            width: isPortrait ? "100%" : "42%",
            maxHeight: isPortrait ? "40%" : "90%",
            objectFit: "cover",
            borderRadius: 24 * unit,
          }}
        />
      ) : null}
    </AbsoluteFill>
  );
};
