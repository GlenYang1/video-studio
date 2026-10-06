import data from "./timeline.json";
import { FONT_FAMILY } from "./fonts";
import type { Theme, Timeline } from "./types";

export const timeline = data as unknown as Timeline;

/** 全片配色与字体：来自 storyboard.json 的 style（参考视频/样张提取的配色写在这里）。 */
export const theme: Theme = {
  bg: "#0f1115",
  fg: "#f5f5f7",
  accent: "#4f8cff",
  muted: "rgba(245,245,247,0.65)",
  ...timeline.style,
  font: `"${timeline.style.font ?? FONT_FAMILY}", "${FONT_FAMILY}", "Microsoft YaHei", sans-serif`,
};

/** 竖屏时字号、边距整体放大一些，保证手机上可读 */
export const isPortrait = timeline.height > timeline.width;
/** 以 1080 短边为基准的缩放系数，组件里的像素值都乘它 */
export const unit = Math.min(timeline.width, timeline.height) / 1080;
/** 字幕占用的底部安全区高度（px），镜头里的文字不要放进这个区域 */
export const captionSafe = timeline.captions.enabled ? timeline.height * (isPortrait ? 0.22 : 0.16) : 0;
