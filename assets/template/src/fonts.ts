/**
 * 字体：项目内置 Noto Sans SC 可变字体（public/fonts，new_project.py 复制进来），渲染不依赖网络。
 * 文件不存在时静默回退到微软雅黑。
 */
import { continueRender, delayRender, staticFile } from "remotion";

export const FONT_FAMILY = "Noto Sans SC";

const handle = delayRender("加载 Noto Sans SC");
new FontFace(FONT_FAMILY, `url(${staticFile("fonts/NotoSansSC-VF.ttf")})`, { weight: "100 900", display: "block" })
  .load()
  .then((f) => {
    document.fonts.add(f);
    return document.fonts.ready;
  })
  .catch(() => undefined)
  .finally(() => continueRender(handle));
