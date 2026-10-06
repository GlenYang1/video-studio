/**
 * 视频素材镜头（用户素材、Blender 渲染出的 mp4 等）。
 * props: { video: "renders/s03.mp4", trimBefore?: 跳过开头秒数, volume?: 原声音量(默认静音), fit?: "cover"|"contain" }
 */
import React from "react";
import { Video } from "@remotion/media";
import { AbsoluteFill, useVideoConfig } from "remotion";
import { src } from "../components/Media";
import { TextBlock } from "../components/Text";
import type { ShotProps } from "../types";

export const VideoClip: React.FC<ShotProps> = ({ shot }) => {
  const { fps } = useVideoConfig();
  const p = shot.props as { video: string; trimBefore?: number; volume?: number; fit?: "cover" | "contain" };
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      <Video
        src={src(p.video)}
        trimBefore={p.trimBefore ? Math.round(p.trimBefore * fps) : undefined}
        muted={!p.volume}
        volume={p.volume ?? 0}
        objectFit={p.fit ?? "cover"}
        style={{ width: "100%", height: "100%" }}
      />
      {shot.title || shot.text ? <TextBlock title={shot.title} text={shot.text} position="bottom" align="left" /> : null}
    </AbsoluteFill>
  );
};
