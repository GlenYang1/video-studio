/** 素材辅助：public/ 下的相对路径 → staticFile；http 开头的原样返回。 */
import React from "react";
import { Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

export const src = (p: string): string => (/^https?:\/\//.test(p) ? p : staticFile(p.replace(/^\/+/, "")));

/** 铺满画面的图片，可选 Ken Burns 缓慢推拉（zoom: 1 → 1+zoom），让静态图也有运动感。 */
export const Cover: React.FC<{ file: string; zoom?: number; style?: React.CSSProperties }> = ({
  file,
  zoom = 0,
  style,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const s = 1 + interpolate(frame, [0, durationInFrames], [0, zoom], { extrapolateRight: "clamp" });
  return (
    <Img
      src={src(file)}
      style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${s})`, ...style }}
    />
  );
};
