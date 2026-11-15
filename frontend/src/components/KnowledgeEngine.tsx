import { Canvas, useFrame } from "@react-three/fiber";
import { Component } from "react";
import { useMemo, useRef, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";
import type { Group, Mesh } from "three";
import { Line } from "@react-three/drei";
import type { Vector3Tuple } from "three";
import { getThemeDefinition, useTheme } from "../theme";
import { useLanguage } from "../language";

const nodes: { label: string; position: Vector3Tuple }[] = [
  { label: "Knowledge", position: [-2.4, 0.8, 0] },
  { label: "Retrieve", position: [-1.4, -0.75, 0.2] },
  { label: "Context", position: [1.35, 0.8, -0.2] },
  { label: "Evaluate", position: [2.4, -0.55, 0] },
  { label: "Lesson", position: [0, -1.65, 0.25] },
];

function EngineScene({
  visual,
}: {
  visual: ReturnType<typeof getThemeDefinition>["visual"];
}) {
  const group = useRef<Group>(null);
  const core = useRef<Mesh>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const particles = useMemo(
    () =>
      Array.from({ length: 22 }, (_, index) => {
        const angle = (index / 22) * Math.PI * 2;
        const radius = 2.85 + (index % 3) * 0.16;
        return [
          Math.cos(angle) * radius,
          Math.sin(angle) * radius * 0.58,
          ((index % 5) - 2) * 0.22,
        ] as Vector3Tuple;
      }),
    [],
  );

  useFrame((state, delta) => {
    if (group.current) group.current.rotation.y += delta * 0.055;
    if (core.current) {
      core.current.rotation.y += delta * 0.16;
      core.current.scale.setScalar(1 + Math.sin(state.clock.elapsedTime * 0.9) * 0.025);
    }
  });

  return (
    <group ref={group}>
      <ambientLight intensity={0.75} />
      <pointLight position={[0, 0, 3]} color={visual.primary} intensity={20} distance={8} />
      <pointLight position={[-3, 2, 1]} color={visual.secondary} intensity={7} distance={7} />
      <mesh ref={core}>
        <icosahedronGeometry args={[0.72, 4]} />
        <meshStandardMaterial
          color={visual.core}
          emissive={visual.coreEmissive}
          emissiveIntensity={1.15}
          metalness={0.45}
          roughness={0.24}
          wireframe
        />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.51, 36, 36]} />
        <meshPhysicalMaterial
          color={visual.center}
          emissive={visual.centerEmissive}
          emissiveIntensity={0.5}
          roughness={0.2}
          metalness={0.16}
          transparent
          opacity={0.83}
        />
      </mesh>
      <mesh rotation={[Math.PI / 2.5, 0.15, 0]}>
        <torusGeometry args={[1.05, 0.007, 6, 100]} />
        <meshBasicMaterial color={visual.ring} transparent opacity={0.5} />
      </mesh>
      {nodes.map((node, index) => {
        const color = index % 2 === 0 ? visual.primary : visual.secondary;
        return (
          <group key={node.label}>
            <Line
              points={[[0, 0, 0], node.position]}
              color={color}
              lineWidth={1}
              transparent
              opacity={0.36}
            />
            <mesh
              position={node.position}
              onPointerOver={() => setHovered(node.label)}
              onPointerOut={() => setHovered(null)}
            >
              <sphereGeometry args={[hovered === node.label ? 0.12 : 0.085, 16, 16]} />
              <meshStandardMaterial
                color={color}
                emissive={color}
                emissiveIntensity={hovered === node.label ? 2 : 0.8}
              />
            </mesh>
          </group>
        );
      })}
      {particles.map((position, index) => (
        <mesh key={index} position={position}>
          <sphereGeometry args={[index % 4 === 0 ? 0.026 : 0.016, 8, 8]} />
          <meshBasicMaterial color={index % 2 ? visual.particleOne : visual.particleTwo} />
        </mesh>
      ))}
    </group>
  );
}

function hasWebGL() {
  if (typeof document === "undefined") return false;
  const canvas = document.createElement("canvas");
  return Boolean(
    window.WebGLRenderingContext &&
      (canvas.getContext("webgl") || canvas.getContext("experimental-webgl")),
  );
}

class WebGLErrorBoundary extends Component<
  { children: ReactNode; onFallback: () => void },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    this.props.onFallback();
  }

  render() {
    if (this.state.failed) return <StaticEngine />;
    return this.props.children;
  }
}

function StaticEngine() {
  return (
    <div className="engine-static" aria-hidden="true">
      <div className="static-core"><span /></div>
      <div className="static-orbit orbit-one" />
      <div className="static-orbit orbit-two" />
    </div>
  );
}

export function KnowledgeEngine() {
  const { t } = useLanguage();
  const { theme } = useTheme();
  const visual = getThemeDefinition(theme).visual;
  const [webgl] = useState(hasWebGL);
  const [rendererFailed, setRendererFailed] = useState(false);
  const [reducedMotion] = useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  return (
    <section className="engine-card" aria-label={t("AI knowledge engine workflow visualization")}>
      <div className="engine-card-header">
        <div>
          <span className="eyebrow">{t("THE KNOWLEDGE ENGINE")}</span>
          <h2>{t("From trusted context to tested lessons")}</h2>
        </div>
        <span className="engine-live"><span /> {t("WORKFLOW MODEL")}</span>
      </div>
      <div className="engine-visual">
        {webgl ? (
          <WebGLErrorBoundary onFallback={() => setRendererFailed(true)}>
            <Canvas
              camera={{ position: [0, 0, 7.4], fov: 40 }}
              dpr={[1, 1.35]}
              frameloop={reducedMotion ? "never" : "always"}
              gl={{ alpha: true, antialias: false, powerPreference: "low-power" }}
              aria-hidden="true"
            >
              <EngineScene visual={visual} />
            </Canvas>
          </WebGLErrorBoundary>
        ) : (
          <StaticEngine />
        )}
        <div className="engine-caption">
          <span>
            {webgl && !rendererFailed
              ? t("Interactive knowledge map")
              : t("Static visualization · WebGL unavailable")}
          </span>
          {reducedMotion && <span>{t("Reduced motion enabled")}</span>}
        </div>
      </div>
      <div className="engine-flow" aria-label={t("Workflow stages")}>
        {["Knowledge", "Retrieve", "Context", "Evaluate", "Lesson"].map((stage, index) => (
          <div className="engine-flow-item" key={stage}>
            <span className={`flow-dot flow-dot-${index}`} />
            <span>{t(stage)}</span>
            {index < 4 && <i aria-hidden="true" />}
          </div>
        ))}
      </div>
    </section>
  );
}
