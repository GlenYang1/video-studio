/**
 * 图片镜头（AI 出图 / 用户图片 / ps-mcp 处理后的图）。
 * props: { image: "images/s02.png", zoom?: 推拉幅度(默认 0.08), dim?: 压暗, position?: 文字位置 "bottom"|"center"|"top",
 *          align?: "left"|"center"（默认横屏 left、竖屏 center）,
 *          layer?: 叠在上面的透明 PNG（抠图后的主体），layerFrom?: 主体入场帧 }
 */
import React from "react";
import { AbsoluteFill, Img, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Cover, src } from "../components/Media";
import { TextBlock } from "../components/Text";
import { isPortrait } from "../theme";
import type { ShotProps } from "../types";

export const ImageShot: React.FC<ShotProps> = ({ shot }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = shot.props as {
    image: string;
    zoom?: number;
    dim?: number;
    position?: "bottom" | "center" | "top";
    align?: "left" | "center";
    layer?: string;
    layerFrom?: number;
  };
  const hasText = Boolean(shot.title || shot.text);
  const pop = spring({ frame: frame - (p.layerFrom ?? 6), fps, config: { damping: 14, mass: 0.8 } });
  return (
    <AbsoluteFill>
      <Cover file={p.image} zoom={p.zoom ?? 0.08} />
      {hasText ? (
        <AbsoluteFill
          style={{
            background: `linear-gradient(to top, rgba(0,0,0,${p.dim ?? 0.6}), transparent 55%)`,
          }}
        />
      ) : null}
      {p.layer ? (
        <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
          <Img
            src={src(p.layer)}
            style={{ maxWidth: "70%", maxHeight: "70%", transform: `scale(${0.8 + 0.2 * pop})`, opacity: pop }}
          />
        </AbsoluteFill>
      ) : null}
      {hasText ? <TextBlock title={shot.title} text={shot.text} position={p.position ?? "bottom"} align={p.align ?? (isPortrait ? "center" : "left")} /> : null}
    </AbsoluteFill>
  );
};
