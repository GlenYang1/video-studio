/** 字幕层：行级时间戳来自 edge-tts 字级边界（或 Whisper），由 timeline.py 断好行。 */
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { isPortrait, theme, timeline, unit } from "../theme";

export const Captions: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (!timeline.captions.enabled) return null;
  const ms = (frame / fps) * 1000;
  const line = timeline.captions.lines.find((l) => ms >= l.startMs && ms < l.endMs);
  if (!line) return null;
  const fade = Math.min(120, (line.endMs - line.startMs) / 3);
  const opacity = interpolate(ms, [line.startMs, line.startMs + fade, line.endMs - fade, line.endMs], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: (isPortrait ? 300 : 70) * unit }}
    >
      <div
        style={{
          opacity,
          maxWidth: "86%",
          padding: `${10 * unit}px ${26 * unit}px`,
          borderRadius: 12 * unit,
          background: "rgba(0,0,0,0.55)",
          color: "#fff",
          fontFamily: theme.font,
          fontSize: (isPortrait ? 58 : 46) * unit,
          fontWeight: 600,
          lineHeight: 1.35,
          textAlign: "center",
          textShadow: "0 2px 8px rgba(0,0,0,0.6)",
        }}
      >
        {line.text}
      </div>
    </AbsoluteFill>
  );
};
