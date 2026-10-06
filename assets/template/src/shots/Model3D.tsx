/**
 * 3D 模型镜头（@remotion/three）。所有运动都由 useCurrentFrame 驱动，禁止 useFrame，否则渲染会闪烁。
 * props: {
 *   model: "models/robot.glb",
 *   clip?: 动画名或序号（模型自带骨骼/关键帧动画时按帧号 setTime，可逐帧确定地渲染）；不写时播放第 0 段，写 false 不播放,
 *   orbit?: 整个镜头内相机绕 Y 轴转过的角度（默认 30）, from?: 起始方位角（默认 -15）,
 *   distance?: 相机距离倍数（默认 3.4，相对模型包围球半径，正好完整入画）, height?: 相机仰角（默认 15 度）,
 *   push?: 镜头内推近比例（0.15 = 推近 15%）, light?: 整体亮度倍数（默认 1，画面偏暗时调高）,
 *   bg?: 背景图（不写则用主题背景色）, ground?: 是否加接触阴影地面（默认 true）,
 *   target?: [x,y,z] 相机环绕和注视的中心（归一化坐标，模型半径 = 1，默认原点；做眼睛/耳朵等局部特写用）,
 *   lift?: 镜头内模型在画面中上移的量（归一化单位，注视点向下移动，给下方标题留位置）
 * }
 * 模型会自动居中并缩放到单位尺寸，换模型不用改相机参数。
 */
import React, { useMemo } from "react";
import { useThree } from "@react-three/fiber";
import { ThreeCanvas } from "@remotion/three";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";
import { Cover, src } from "../components/Media";
import { TextBlock } from "../components/Text";
import { theme } from "../theme";
import { useGltf } from "../three/useGltf";
import type { ShotProps } from "../types";

type P = {
  model: string;
  clip?: string | number | false;
  orbit?: number;
  from?: number;
  distance?: number;
  height?: number;
  push?: number;
  light?: number;
  bg?: string;
  ground?: boolean;
  target?: [number, number, number];
  lift?: number;
};

const deg = Math.PI / 180;

const Scene: React.FC<{ p: P; duration: number }> = ({ p, duration }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const gltf = useGltf(src(p.model));

  // 居中 + 归一化到半径 1，并准备动画混合器。按镜头克隆一份，同一模型在相邻镜头里同时出现（转场）也不冲突
  const prepared = useMemo(() => {
    if (!gltf) return null;
    const root = cloneSkinned(gltf.scene);
    const box = new THREE.Box3().setFromObject(root);
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const scale = 1 / (sphere.radius || 1);
    root.traverse((o) => {
      const m = o as THREE.Mesh;
      if (m.isMesh) {
        m.castShadow = true;
        m.receiveShadow = true;
      }
    });
    const mixer = new THREE.AnimationMixer(root);
    const clips = gltf.animations;
    const clip =
      p.clip === false
        ? undefined
        : typeof p.clip === "string" ? clips.find((c) => c.name === p.clip) : clips[typeof p.clip === "number" ? p.clip : 0];
    if (clip) mixer.clipAction(clip).play();
    return { root, scale, center: sphere.center.clone(), minY: box.min.y, mixer, hasClip: Boolean(clip) };
  }, [gltf, p.clip]);

  if (!prepared) return null;
  // 动画按帧号确定性地求值
  if (prepared.hasClip) prepared.mixer.setTime(frame / fps);

  const t = interpolate(frame, [0, duration], [0, 1], { extrapolateRight: "clamp" });
  const ease = t * t * (3 - 2 * t);
  const az = ((p.from ?? -15) + (p.orbit ?? 30) * ease) * deg;
  const el = (p.height ?? 15) * deg;
  const dist = (p.distance ?? 3.4) * (1 - (p.push ?? 0) * ease);
  const tg = p.target ?? [0, 0, 0];
  const look: [number, number, number] = [tg[0], tg[1] - (p.lift ?? 0) * ease, tg[2]];
  const cam: [number, number, number] = [
    tg[0] + dist * Math.sin(az) * Math.cos(el),
    tg[1] + dist * Math.sin(el),
    tg[2] + dist * Math.cos(az) * Math.cos(el),
  ];
  const k = p.light ?? 1;
  const groundY = (prepared.minY - prepared.center.y) * prepared.scale;

  return (
    <ThreeCanvas
      width={width}
      height={height}
      shadows
      gl={{ antialias: true, preserveDrawingBuffer: true, toneMapping: THREE.ACESFilmicToneMapping }}
      camera={{ fov: 35, near: 0.01, far: 100, position: cam }}
    >
      <CameraRig position={cam} look={look} />
      <Environment intensity={0.8 * k} />
      <hemisphereLight args={["#ffffff", "#444455", 0.9 * k]} />
      <directionalLight position={[3, 5, 4]} intensity={2.2 * k} castShadow shadow-mapSize={[2048, 2048]} />
      <directionalLight position={[-4, 2, -3]} intensity={0.8 * k} color={theme.accent} />
      <group scale={prepared.scale}>
        <primitive
          object={prepared.root}
          position={[-prepared.center.x, -prepared.center.y, -prepared.center.z]}
        />
      </group>
      {p.ground !== false ? (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, groundY - 0.001, 0]} receiveShadow>
          <planeGeometry args={[20, 20]} />
          <shadowMaterial opacity={0.35} />
        </mesh>
      ) : null}
    </ThreeCanvas>
  );
};

/** 本地生成的室内环境贴图：金属/光滑材质靠它出反射，否则会发黑。不走网络，渲染结果确定。 */
const Environment: React.FC<{ intensity: number }> = ({ intensity }) => {
  const gl = useThree((s) => s.gl);
  const scene = useThree((s) => s.scene);
  const env = useMemo(() => {
    const pmrem = new THREE.PMREMGenerator(gl);
    const tex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    pmrem.dispose();
    return tex;
  }, [gl]);
  scene.environment = env;
  scene.environmentIntensity = intensity;
  return null;
};

/** 每帧把相机移到计算好的位置并看向原点（用 R3F 的 useThree 拿相机，不用 useFrame）。 */
const CameraRig: React.FC<{ position: [number, number, number]; look: [number, number, number] }> = ({
  position,
  look,
}) => {
  const camera = useThree((s) => s.camera);
  camera.position.set(...position);
  camera.lookAt(...look);
  camera.updateProjectionMatrix();
  return null;
};

export const Model3D: React.FC<ShotProps> = ({ shot }) => {
  const p = shot.props as P;
  return (
    <AbsoluteFill style={{ backgroundColor: theme.bg }}>
      {/* 背景和画布各占一个绝对定位层：Cover 是 100% 高的 <Img>，和画布放在同一个 flex 列里会把画布容器挤成 0 高，
          R3F 测不到尺寸就不会创建画布，渲染卡在 "Waiting for <ThreeCanvas/> to be created" */}
      {p.bg ? (
        <AbsoluteFill>
          <Cover file={p.bg} />
        </AbsoluteFill>
      ) : null}
      <AbsoluteFill>
        <Scene p={p} duration={shot.durationInFrames} />
      </AbsoluteFill>
      {shot.title || shot.text ? <TextBlock title={shot.title} text={shot.text} position="bottom" align="left" /> : null}
    </AbsoluteFill>
  );
};
