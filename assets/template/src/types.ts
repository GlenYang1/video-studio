/** src/timeline.json 的结构，由 scripts/timeline.py 生成，不要手改（改 storyboard.json 后重新生成）。 */
export type Transition = "cut" | "fade" | "slide" | "wipe" | "zoom";

export type Shot = {
  id: string;
  type: string; // 2d | 3d | manim | mixed
  component: string; // src/shots/index.ts 里注册的组件名，留空时按 type/props 自动选择
  from: number;
  durationInFrames: number;
  transition: Transition;
  transitionFrames: number;
  title: string;
  visual: string;
  text: string;
  props: Record<string, unknown>;
  vo: { src: string; from: number; trimBefore: number; durationInFrames: number } | null;
};

export type Timeline = {
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
  title: string;
  style: Partial<Theme>;
  shots: Shot[];
  music: {
    src: string;
    volume: number;
    duck: number;
    fadeInFrames: number;
    fadeOutFrames: number;
    segments: { from: number; durationInFrames: number; trimBefore: number }[];
    bpm: number | null;
  } | null;
  duckRanges: [number, number][];
  captions: { enabled: boolean; lines: { text: string; startMs: number; endMs: number }[] };
};

export type Theme = {
  bg: string;
  fg: string;
  accent: string;
  muted: string;
  font: string;
};

export type ShotProps = { shot: Shot };
