/**
 * 加载 .glb/.gltf：用 delayRender 挡住渲染直到模型就绪，避免首帧空白。
 * 不用 drei 的 useGLTF（它依赖 Suspense + 网络缓存，在 Remotion 多标签页渲染时偶发空帧）。
 */
import { useEffect, useState } from "react";
import { cancelRender, continueRender, delayRender } from "remotion";
import type { GLTF } from "three/examples/jsm/loaders/GLTFLoader.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

const cache = new Map<string, Promise<GLTF>>();

export const useGltf = (url: string): GLTF | null => {
  const [gltf, setGltf] = useState<GLTF | null>(null);
  const [handle] = useState(() => delayRender(`加载模型 ${url}`, { timeoutInMilliseconds: 120000 }));
  useEffect(() => {
    let p = cache.get(url);
    if (!p) {
      p = new GLTFLoader().loadAsync(url);
      cache.set(url, p);
    }
    p.then((g) => {
      setGltf(g);
      continueRender(handle);
    }).catch((e) => cancelRender(e));
  }, [url, handle]);
  return gltf;
};
