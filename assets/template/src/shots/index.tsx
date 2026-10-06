/**
 * 镜头组件注册表。storyboard.json 里镜头的 component 字段写这里的名字。
 * 新做的定制镜头放进 src/shots/，在 SHOTS 里登记即可；component 留空时按 type/props 自动选择。
 */
import React from "react";
import type { Shot } from "../types";
import { ImageSequence } from "./ImageSequence";
import { ImageShot } from "./ImageShot";
import { ManimClip } from "./ManimClip";
import { Model3D } from "./Model3D";
import { Points } from "./Points";
import { TitleCard } from "./TitleCard";
import { VideoClip } from "./VideoClip";

export const SHOTS: Record<string, React.FC<{ shot: Shot }>> = {
  TitleCard,
  ImageShot,
  Points,
  ManimClip,
  VideoClip,
  ImageSequence,
  Model3D,
};

const pick = (shot: Shot): string => {
  if (shot.component && SHOTS[shot.component]) return shot.component;
  const p = shot.props;
  if (shot.type === "3d") return p.frames ? "ImageSequence" : "Model3D";
  if (shot.type === "manim") return "ManimClip";
  if (p.video) return "VideoClip";
  if (p.points) return "Points";
  if (p.image) return "ImageShot";
  return "TitleCard";
};

export const renderShot = (shot: Shot): React.ReactNode => {
  const C = SHOTS[pick(shot)];
  return <C shot={shot} />;
};
