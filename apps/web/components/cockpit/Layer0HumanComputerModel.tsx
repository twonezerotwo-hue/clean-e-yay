"use client";

import { Line } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { Suspense, useMemo, useRef } from "react";
import * as THREE from "three";

type ModelMode = "idle" | "listening" | "thinking" | "speaking";
type Vec3 = [number, number, number];
export type Layer0DataQualityPulse = {
  score: number;
  status: "OK" | "DEGRADED" | "BLOCKED";
  freshness: number;
  completeness: number;
  drift: number;
  reconciliation: number;
  decisionUsage: number;
  // Backend-türetilmiş (DqsBreakdown.stress_score) — 3D nabız animasyon hızı
  // için; burada YENİDEN hesaplanmaz (architecture guard: no frontend decision math).
  stressScore: number;
  ageLabel: string;
};

const MODE_COLOR: Record<ModelMode, string> = {
  idle: "#22d3ee",
  listening: "#34d399",
  thinking: "#fbbf24",
  speaking: "#a78bfa",
};

const DQS_COLOR: Record<Layer0DataQualityPulse["status"], string> = {
  OK: "#34d399",
  DEGRADED: "#fbbf24",
  BLOCKED: "#f87171",
};

function NeuralParticles({ mode }: { mode: ModelMode }) {
  const points = useRef<THREE.Points>(null);
  const positions = useMemo(() => {
    const data = new Float32Array(760 * 3);
    for (let index = 0; index < 760; index += 1) {
      const radius = 1.86 + Math.random() * 2.92;
      const theta = Math.random() * Math.PI * 2;
      const y = (Math.random() - 0.5) * 3.16;
      data[index * 3] = Math.cos(theta) * radius;
      data[index * 3 + 1] = y;
      data[index * 3 + 2] = Math.sin(theta) * radius * 0.72;
    }
    return data;
  }, []);

  useFrame(({ clock }) => {
    if (!points.current) return;
    const t = clock.elapsedTime;
    points.current.rotation.y = t * (mode === "thinking" ? 0.09 : 0.052);
    points.current.rotation.x = Math.sin(t * 0.18) * 0.04;
  });

  return (
    <points ref={points}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={positions.length / 3}
          array={positions}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial
        color={MODE_COLOR[mode]}
        size={0.018}
        transparent
        opacity={mode === "speaking" ? 0.58 : 0.38}
        sizeAttenuation
      />
    </points>
  );
}

function HologramRings({ mode }: { mode: ModelMode }) {
  const group = useRef<THREE.Group>(null);
  const color = MODE_COLOR[mode];

  useFrame(({ clock }) => {
    if (!group.current) return;
    const t = clock.elapsedTime;
    group.current.rotation.y = t * 0.16;
    group.current.rotation.z = Math.sin(t * 0.22) * 0.08;
  });

  return (
    <group ref={group}>
      {[
        { radius: 1.05, tube: 0.006, rotation: [Math.PI / 2.08, 0, 0.16] as Vec3, opacity: 0.58 },
        { radius: 1.58, tube: 0.007, rotation: [1.08, 0.32, 0.82] as Vec3, opacity: 0.38 },
        { radius: 2.08, tube: 0.005, rotation: [1.78, -0.46, -0.42] as Vec3, opacity: 0.28 },
      ].map((ring) => (
        <mesh key={`${ring.radius}-${ring.opacity}`} rotation={ring.rotation}>
          <torusGeometry args={[ring.radius, ring.tube, 8, 192]} />
          <meshBasicMaterial color={color} transparent opacity={ring.opacity} />
        </mesh>
      ))}
      <mesh position={[0, -1.34, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.42, 0.018, 10, 220]} />
        <meshBasicMaterial color="#67e8f9" transparent opacity={0.44} />
      </mesh>
      <mesh position={[0, -1.36, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.38, 1.4, 180]} />
        <meshBasicMaterial
          color="#22d3ee"
          transparent
          opacity={0.08}
          side={THREE.DoubleSide}
        />
      </mesh>
    </group>
  );
}

function VoiceAnalyzer({ mode }: { mode: ModelMode }) {
  const group = useRef<THREE.Group>(null);
  const speaking = mode === "speaking";

  useFrame(({ clock }) => {
    if (!group.current) return;
    const t = clock.elapsedTime;
    group.current.children.forEach((child, index) => {
      const mesh = child as THREE.Mesh;
      const intensity = speaking ? 0.44 + Math.sin(t * 7 + index * 0.9) * 0.22 : 0.2;
      mesh.scale.y = Math.max(0.18, intensity);
    });
  });

  return (
    <group ref={group} position={[0, 1.16, 0.62]}>
      {[-0.18, -0.09, 0, 0.09, 0.18].map((x, index) => (
        <mesh key={x} position={[x, 0, 0]}>
          <boxGeometry args={[0.028, 0.28 + index * 0.02, 0.018]} />
          <meshBasicMaterial color={speaking ? "#a78bfa" : "#67e8f9"} transparent opacity={0.82} />
        </mesh>
      ))}
    </group>
  );
}

function DataQualityCore({
  dataQuality,
}: {
  dataQuality?: Layer0DataQualityPulse | null;
}) {
  const group = useRef<THREE.Group>(null);
  const score = dataQuality?.score ?? 0;
  const color = dataQuality ? DQS_COLOR[dataQuality.status] : "#67e8f9";
  const stress = dataQuality?.stressScore ?? 0.25;
  const bpm = dataQuality?.status === "BLOCKED" ? 2.55 : dataQuality?.status === "DEGRADED" ? 2.15 : 1.62 + stress * 0.8;

  useFrame(({ clock }) => {
    if (!group.current) return;
    const phase = (clock.elapsedTime * bpm) % 1;
    const systole = Math.exp(-Math.pow((phase - 0.08) / 0.034, 2));
    const echo = Math.exp(-Math.pow((phase - 0.24) / 0.06, 2));
    const pulse = 1 + systole * 0.46 + echo * 0.2;
    group.current.scale.setScalar(pulse);
    group.current.rotation.z = Math.sin(clock.elapsedTime * 1.5) * 0.08;
  });

  return (
    <group ref={group} position={[0, 0.44, 0.5]}>
      <mesh>
        <sphereGeometry args={[0.075 + Math.max(0, score) / 1600, 24, 24]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={0.9}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.18, 0.006, 8, 72]} />
        <meshBasicMaterial color={color} transparent opacity={0.72} depthWrite={false} />
      </mesh>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.29, 0.004, 8, 96]} />
        <meshBasicMaterial color={color} transparent opacity={0.34} depthWrite={false} />
      </mesh>
    </group>
  );
}

function HumanComputerBust({
  mode,
  dataQuality,
}: {
  mode: ModelMode;
  dataQuality?: Layer0DataQualityPulse | null;
}) {
  const group = useRef<THREE.Group>(null);
  const cloud = useRef<THREE.Points>(null);
  const color = MODE_COLOR[mode];

  // Layered robot bust: point cloud volume plus hard-surface translucent armor.
  const positions = useMemo(() => {
    const HEAD = 2300;
    const TORSO = 1800;
    const NECK = 360;
    const data = new Float32Array((HEAD + TORSO + NECK) * 3);
    let o = 0;
    const onSphere = (): Vec3 => {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const s = Math.sin(phi);
      return [Math.cos(theta) * s, Math.cos(phi), Math.sin(theta) * s];
    };
    for (let i = 0; i < HEAD; i += 1) {
      const [x, y, z] = onSphere();
      const jaw = y < -0.22 ? 0.66 + (y + 1) * 0.2 : 1;
      const crown = y > 0.38 ? 0.94 - (y - 0.38) * 0.11 : 1;
      const taper = Math.max(0.56, jaw * crown);
      data[o++] = x * 0.5 * taper;
      data[o++] = y * 0.7 + 1.42;
      data[o++] = z * 0.42 * taper;
    }
    for (let i = 0; i < TORSO; i += 1) {
      const [x, y, z] = onSphere();
      const shoulder = 1 + Math.max(0, Math.abs(x) - 0.28) * 0.42;
      data[o++] = x * 1.08 * shoulder;
      data[o++] = -Math.abs(y) * 0.52 + 0.45;
      data[o++] = z * 0.38;
    }
    for (let i = 0; i < NECK; i += 1) {
      const a = Math.random() * Math.PI * 2;
      const r = 0.16 + Math.random() * 0.035;
      data[o++] = Math.cos(a) * r;
      data[o++] = 0.72 + Math.random() * 0.44;
      data[o++] = Math.sin(a) * r * 0.85;
    }
    return data;
  }, []);
  const circuitLines = useMemo<Vec3[][]>(
    () => [
      [
        [-0.32, 1.74, 0.43],
        [-0.18, 1.82, 0.47],
        [0, 1.86, 0.49],
        [0.18, 1.82, 0.47],
        [0.32, 1.74, 0.43],
      ],
      [
        [-0.38, 1.36, 0.47],
        [-0.22, 1.27, 0.51],
        [0, 1.24, 0.53],
        [0.22, 1.27, 0.51],
        [0.38, 1.36, 0.47],
      ],
      [
        [-0.52, 0.38, 0.38],
        [-0.24, 0.14, 0.48],
        [0, 0.44, 0.5],
        [0.24, 0.14, 0.48],
        [0.52, 0.38, 0.38],
      ],
      [
        [-0.74, 0.54, 0.16],
        [-0.44, 0.42, 0.38],
        [-0.2, 0.36, 0.48],
      ],
      [
        [0.74, 0.54, 0.16],
        [0.44, 0.42, 0.38],
        [0.2, 0.36, 0.48],
      ],
    ],
    [],
  );

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    if (group.current) {
      group.current.rotation.y = Math.sin(t * 0.26) * 0.16;
      group.current.position.y = Math.sin(t * 1.1) * 0.02;
    }
    if (cloud.current) {
      const mat = cloud.current.material as THREE.PointsMaterial;
      mat.opacity =
        mode === "speaking"
          ? 0.74 + Math.sin(t * 9) * 0.16
          : mode === "thinking"
            ? 0.6 + Math.sin(t * 4) * 0.12
            : 0.6;
    }
  });

  return (
    <group ref={group}>
      <points ref={cloud}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            count={positions.length / 3}
            array={positions}
            itemSize={3}
          />
        </bufferGeometry>
        <pointsMaterial
          color={color}
          size={0.026}
          transparent
          opacity={0.6}
          sizeAttenuation
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
      <mesh position={[0, 1.42, 0]} scale={[0.5, 0.72, 0.43]}>
        <sphereGeometry args={[0.72, 48, 48]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={0.1}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
      <mesh position={[0, 1.45, 0.43]}>
        <boxGeometry args={[0.64, 0.24, 0.026]} />
        <meshBasicMaterial color="#7dd3fc" transparent opacity={0.18} depthWrite={false} />
      </mesh>
      <mesh position={[-0.17, 1.49, 0.452]}>
        <boxGeometry args={[0.16, 0.034, 0.018]} />
        <meshBasicMaterial color="#e0f2fe" transparent opacity={0.96} />
      </mesh>
      <mesh position={[0.17, 1.49, 0.452]}>
        <boxGeometry args={[0.16, 0.034, 0.018]} />
        <meshBasicMaterial color="#e0f2fe" transparent opacity={0.96} />
      </mesh>
      <mesh position={[0, 1.24, 0.43]}>
        <boxGeometry args={[0.34, 0.12, 0.026]} />
        <meshBasicMaterial color="#38bdf8" transparent opacity={0.2} depthWrite={false} />
      </mesh>
      <mesh position={[-0.5, 1.45, 0.02]} rotation={[0, Math.PI / 2, 0]}>
        <torusGeometry args={[0.12, 0.01, 8, 64]} />
        <meshBasicMaterial color="#67e8f9" transparent opacity={0.52} />
      </mesh>
      <mesh position={[0.5, 1.45, 0.02]} rotation={[0, Math.PI / 2, 0]}>
        <torusGeometry args={[0.12, 0.01, 8, 64]} />
        <meshBasicMaterial color="#67e8f9" transparent opacity={0.52} />
      </mesh>
      <mesh position={[0, 0.8, 0]}>
        <cylinderGeometry args={[0.17, 0.2, 0.5, 32, 1, true]} />
        <meshBasicMaterial color="#67e8f9" transparent opacity={0.08} depthWrite={false} />
      </mesh>
      <mesh position={[0, 0.34, 0]} scale={[0.9, 0.54, 0.34]}>
        <sphereGeometry args={[0.72, 48, 32]} />
        <meshBasicMaterial color={color} transparent opacity={0.08} depthWrite={false} />
      </mesh>
      <mesh position={[0, 0.36, 0.38]}>
        <boxGeometry args={[0.68, 0.48, 0.035]} />
        <meshBasicMaterial color="#22d3ee" transparent opacity={0.09} depthWrite={false} />
      </mesh>
      <mesh position={[-0.84, 0.42, 0]} scale={[0.5, 0.22, 0.28]}>
        <sphereGeometry args={[0.72, 32, 24]} />
        <meshBasicMaterial color="#67e8f9" transparent opacity={0.07} depthWrite={false} />
      </mesh>
      <mesh position={[0.84, 0.42, 0]} scale={[0.5, 0.22, 0.28]}>
        <sphereGeometry args={[0.72, 32, 24]} />
        <meshBasicMaterial color="#67e8f9" transparent opacity={0.07} depthWrite={false} />
      </mesh>
      {circuitLines.map((line, index) => (
        <Line
          key={index}
          points={line}
          color={index === 2 ? "#fbbf24" : "#a5f3fc"}
          transparent
          opacity={index === 2 ? 0.55 : 0.36}
          lineWidth={1}
        />
      ))}
      <VoiceAnalyzer mode={mode} />
      <DataQualityCore dataQuality={dataQuality} />
    </group>
  );
}

function DataRibbons({ mode }: { mode: ModelMode }) {
  const group = useRef<THREE.Group>(null);
  const color = MODE_COLOR[mode];
  const ribbons = useMemo(
    () =>
      Array.from({ length: 8 }, (_, index) => {
        const offset = index * 0.28;
        return Array.from({ length: 42 }, (_point, pointIndex) => {
          const t = pointIndex / 41;
          const angle = t * Math.PI * 2 + offset;
          return [
            Math.cos(angle) * (1.28 + index * 0.05),
            -1.18 + t * 2.8,
            Math.sin(angle) * (0.64 + index * 0.025),
          ] as Vec3;
        });
      }),
    [],
  );

  useFrame(({ clock }) => {
    if (!group.current) return;
    group.current.rotation.y = clock.elapsedTime * 0.08;
  });

  return (
    <group ref={group}>
      {ribbons.map((points, index) => (
        <Line
          key={index}
          points={points}
          color={index % 3 === 0 ? "#fbbf24" : color}
          transparent
          opacity={0.16 + (index % 3) * 0.04}
          lineWidth={1}
        />
      ))}
    </group>
  );
}

function Scene({
  mode,
  dataQuality,
}: {
  mode: ModelMode;
  dataQuality?: Layer0DataQualityPulse | null;
}) {
  const color = MODE_COLOR[mode];

  return (
    <>
      <color attach="background" args={["#020712"]} />
      <fog attach="fog" args={["#020712", 5, 10.4]} />
      <ambientLight intensity={0.36} />
      <pointLight position={[2.6, 3.2, 3.6]} color="#67e8f9" intensity={4.1} />
      <pointLight position={[-3.2, 1.2, 1.6]} color={color} intensity={2.2} />
      <pointLight position={[0, -1.2, 2.8]} color="#fbbf24" intensity={0.9} />
      <group position={[0, -0.06, 0]} scale={0.96}>
        <NeuralParticles mode={mode} />
        <DataRibbons mode={mode} />
        <HologramRings mode={mode} />
        <HumanComputerBust mode={mode} dataQuality={dataQuality} />
      </group>
    </>
  );
}

const DQS_METRICS = [
  ["Fresh", "freshness"],
  ["Comp", "completeness"],
  ["Drift", "drift"],
  ["Recon", "reconciliation"],
  ["Use", "decisionUsage"],
] as const;

function clampMetric(value: number) {
  return Math.max(0, Math.min(100, Math.round(value)));
}

export function Layer0HumanComputerModel({
  mode,
  dataQuality,
  onOpenLayer1,
  pttEnabled = false,
  pttActive = false,
  onPressStart,
  onPressEnd,
}: {
  mode: ModelMode;
  dataQuality?: Layer0DataQualityPulse | null;
  onOpenLayer1?: () => void;
  // Bas-konus: holograma basili tutuldukca dinle, birakinca gonder.
  pttEnabled?: boolean;
  pttActive?: boolean;
  onPressStart?: () => void;
  onPressEnd?: () => void;
}) {
  const status = dataQuality?.status ?? "DEGRADED";
  const handlePressStart = () => {
    if (pttEnabled) onPressStart?.();
  };
  const handlePressEnd = () => {
    if (pttEnabled) onPressEnd?.();
  };
  return (
    <div
      className={`layer0-human-model${pttEnabled ? " layer0-human-model--ptt" : ""}${
        pttActive ? " layer0-human-model--listening" : ""
      }`}
      onDoubleClick={onOpenLayer1}
      onPointerDown={handlePressStart}
      onPointerUp={handlePressEnd}
      onPointerLeave={handlePressEnd}
      onPointerCancel={handlePressEnd}
      onContextMenu={(event) => {
        if (pttEnabled) event.preventDefault();
      }}
      title={pttEnabled ? "Bas-konus: basili tut konus, birak; cift tikla Katman 1" : "Katman 1'e geç"}
      style={pttEnabled ? { touchAction: "none", cursor: "pointer", userSelect: "none" } : undefined}
    >
      {pttEnabled ? (
        <div className={`layer0-ptt-hint${pttActive ? " layer0-ptt-hint--on" : ""}`} aria-hidden>
          <span className="layer0-ptt-dot" />
          {pttActive ? "Dinliyorum… birak" : "Bas-konus: basili tut"}
        </div>
      ) : null}
      <Canvas
        camera={{ position: [0, 0.32, 5.15], fov: 40 }}
        dpr={[1, 1.75]}
        gl={{ antialias: true, alpha: false, preserveDrawingBuffer: true }}
      >
        <Suspense fallback={null}>
          <Scene mode={mode} dataQuality={dataQuality} />
        </Suspense>
      </Canvas>
      <div className="layer0-human-model__beam" />
      <div className="layer0-human-model__scan" />
      <div className={`layer0-human-model__dqs layer0-human-model__dqs--${status.toLowerCase()}`}>
        <div className="layer0-human-model__ecg" aria-hidden="true">
          <svg viewBox="0 0 240 42" preserveAspectRatio="none">
            <path d="M0 24 H35 L44 24 L51 10 L59 34 L69 18 L78 24 H112 L121 24 L128 8 L136 36 L146 19 L156 24 H240" />
          </svg>
        </div>
        <div className="layer0-human-model__dqs-metrics">
          {DQS_METRICS.map(([label, key]) => {
            const value = dataQuality ? clampMetric(dataQuality[key]) : 0;
            return (
              <span key={key} title={`${label}: ${dataQuality ? value : "--"}`} aria-label={`${label}: ${dataQuality ? value : "--"}`}>
                <i style={{ width: `${value}%` }} />
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
}
