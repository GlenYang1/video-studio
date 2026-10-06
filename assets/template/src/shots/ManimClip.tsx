/**
 * Manim 片段（manim_clip.py 渲染到 public/manim/）。
 * props: { video: "manim/Pythagoras.webm", bg?: 底图（透明片段叠在它上面）, fit?: "contain"|"cover", rate?: 播放速度 }
 * 透明片段用 WebM（VP9 带 alpha），<Video> 会自动保留透明通道；@remotion/media 不能解码 ProRes .mov。
 */
import React from "react";
import { Video } from "@remotion/media";
import { AbsoluteFill } from "remotion";
import { Cover, src } from "../components/Media";
import { captionSafe, theme } from "../theme";
import type { ShotProps } from "../types";

export const ManimClip: React.FC<ShotProps> = ({ shot }) => {
  const p = shot.props as { video: string; bg?: string; fit?: "contain" | "cover"; rate?: number };
  return (
    <AbsoluteFill style={{ backgroundColor: theme.bg }}>
      {p.bg ? <Cover file={p.bg} /> : null}
      <AbsoluteFill style={{ bottom: p.fit === "cover" ? 0 : captionSafe }}>
        <Video
          src={src(p.video)}
          muted
          playbackRate={p.rate ?? 1}
          objectFit={p.fit ?? "contain"}
          style={{ width: "100%", height: "100%" }}
        />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
