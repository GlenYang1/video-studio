/** 通用文字块：标题 + 正文，带上浮淡入。文字自动避开底部字幕安全区。 */
import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { captionSafe, isPortrait, theme, unit } from "../theme";

export const FadeUp: React.FC<{ delay?: number; children: React.ReactNode; style?: React.CSSProperties }> = ({
  delay = 0,
  children,
  style,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: frame - delay, fps, config: { damping: 200 } });
  return (
    <div style={{ opacity: p, transform: `translateY(${interpolate(p, [0, 1], [30 * unit, 0])}px)`, ...style }}>
      {children}
    </div>
  );
};

export const TextBlock: React.FC<{
  title?: string;
  text?: string;
  align?: "left" | "center";
  position?: "center" | "bottom" | "top";
  /** 标题上方的强调色短横条，0~1 为展开进度（TitleCard 用） */
  bar?: number;
}> = ({ title, text, align = "center", position = "center", bar }) => (
  <div
    style={{
      position: "absolute",
      left: 0,
      right: 0,
      top: 0,
      bottom: captionSafe,
      display: "flex",
      flexDirection: "column",
      justifyContent: position === "center" ? "center" : position === "top" ? "flex-start" : "flex-end",
      alignItems: align === "center" ? "center" : "flex-start",
      padding: `${(isPortrait ? 140 : 90) * unit}px ${(isPortrait ? 70 : 120) * unit}px`,
      textAlign: align,
      gap: 24 * unit,
    }}
  >
    {bar !== undefined && title ? (
      <div
        style={{ width: 160 * unit * bar, height: 6 * unit, backgroundColor: theme.accent, borderRadius: 3 * unit }}
      />
    ) : null}
    {title ? (
      <FadeUp>
        {/* 标题里写 
 可以手动换行；竖屏字号更大，保证手机上可读 */}
        <div
          style={{
            fontSize: (isPortrait ? 112 : 84) * unit,
            fontWeight: 800,
            lineHeight: 1.15,
            letterSpacing: 1,
            whiteSpace: "pre-line",
          }}
        >
          {title}
        </div>
      </FadeUp>
    ) : null}
    {text ? (
      <FadeUp delay={8}>
        <div
          style={{ fontSize: (isPortrait ? 52 : 40) * unit, color: theme.muted, lineHeight: 1.5, whiteSpace: "pre-line" }}
        >
          {text}
        </div>
      </FadeUp>
    ) : null}
  </div>
);
