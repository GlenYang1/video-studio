import React from "react";
import { Composition } from "remotion";
import "./fonts";
import { timeline } from "./theme";
import { Main } from "./Video";

export const RemotionRoot: React.FC = () => (
  <Composition
    id="Main"
    component={Main}
    width={timeline.width}
    height={timeline.height}
    fps={timeline.fps}
    durationInFrames={Math.max(1, timeline.durationInFrames)}
  />
);
