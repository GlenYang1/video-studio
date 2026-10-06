/**
 * 渲染配置（只对 CLI 生效）。
 * 渲染浏览器用 video-studio 共享目录里的 chrome-headless-shell，新项目不必再下载一次。
 */
import { Config } from "@remotion/cli/config";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const home = process.env.VIDEO_STUDIO_HOME ?? path.join(os.homedir(), ".clawsgo", "video-studio");
const chrome = path.join(home, "chrome-headless-shell", "win64", "chrome-headless-shell-win64", "chrome-headless-shell.exe");
if (fs.existsSync(chrome)) {
  Config.setBrowserExecutable(chrome);
}

Config.setRspack(true);
// 3D 镜头需要 WebGL：angle 在 Windows 上走 GPU，headless 下也能渲染 Three.js
Config.setChromiumOpenGlRenderer("angle");
// 文字和矢量图形多，中间帧用 PNG 避免 JPEG 在细笔画上的压缩噪点
Config.setVideoImageFormat("png");
Config.setOverwriteOutput(true);
