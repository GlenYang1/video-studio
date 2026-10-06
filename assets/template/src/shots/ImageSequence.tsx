/**
 * Blender 渲染的序列帧（blender_tool.py render 输出到 public/renders/<镜头>/0001.png …）。
 * props: { frames: "renders/S03", count: 帧数, start?: 起始编号(默认 1), digits?: 位数(默认 4), ext?: "png"|"jpg", bg?: 底图 }
 * 按镜头内帧号逐帧取图，镜头比序列长时停在最后一帧。
 */
import React from "react";
import { AbsoluteFill, Img, useCurrentFrame } from "remotion";
import { Cover, src } from "../components/Media";
import { theme } from "../theme";
import type { ShotProps } from "../types";

export const ImageSequence: React.FC<ShotProps> = ({ shot }) => {
  const frame = useCurrentFrame();
  const p = shot.props as { frames: string; count: number; start?: number; digits?: number; ext?: string; bg?: string };
  const i = Math.min(Math.max(frame, 0), p.count - 1) + (p.start ?? 1);
  const file = `${p.frames.replace(/\/$/, "")}/${String(i).padStart(p.digits ?? 4, "0")}.${p.ext ?? "png"}`;
  return (
    <AbsoluteFill style={{ backgroundColor: theme.bg }}>
      {p.bg ? <Cover file={p.bg} /> : null}
      <Img src={src(file)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
    </AbsoluteFill>
  );
};
