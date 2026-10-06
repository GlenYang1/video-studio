import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import type { Transition } from "../types";

/** 镜头入场转场：fade 淡入 / slide 从右推入 / wipe 左到右擦除 / zoom 放大淡入 / cut 硬切。 */
export const TransitionIn: React.FC<{ type: Transition; frames: number; children: React.ReactNode }> = ({
  type,
  frames,
  children,
}) => {
  const frame = useCurrentFrame();
  if (type === "cut" || frames <= 0) return <AbsoluteFill>{children}</AbsoluteFill>;
  const p = interpolate(frame, [0, frames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const style: React.CSSProperties =
    type === "fade"
      ? { opacity: p }
      : type === "slide"
        ? { transform: `translateX(${(1 - p) * 100}%)` }
        : type === "wipe"
          ? { clipPath: `inset(0 ${(1 - p) * 100}% 0 0)` }
          : { opacity: p, transform: `scale(${1.08 - 0.08 * p})` };
  return <AbsoluteFill style={style}>{children}</AbsoluteFill>;
};
