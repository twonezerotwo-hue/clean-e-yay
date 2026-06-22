"use client";

import { Line, Stars } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { Suspense, useMemo, useRef } from "react";
import * as THREE from "three";

import type { AgentBrief } from "@/types/generated/api";

type Vec3 = [number, number, number];

type QuantumNode = {
  key: string;
  position: Vec3;
  color: string;
  score: number;
  phase: number;
};

const STATUS_COLOR: Record<string, string> = {
  ACTIONABLE: "#34d399",
  NO_ACTION: "#14b8a6",
  WATCHING: "#fbbf24",
  FROZEN: "#a78bfa",
  BLOCKED: "#fb7185",
};

const DIRECTION_COLOR: Record<string, string> = {
  bullish: "#34d399",
  bearish: "#fb7185",
  neutral: "#fbbf24",
};

function makeFallbackNodes(color: string): QuantumNode[] {
  return Array.from({ length: 7 }, (_, index) => {
    const angle = (index / 7) * Math.PI * 2;
    const radius = index % 2 ? 4.1 : 3.05;
    return {
      key: `fallback-${index}`,
      position: [
        Math.cos(angle) * radius,
        Math.sin(angle * 1.35) * 0.82,
        Math.sin(angle) * 1.55 - 1.2,
      ],
      color: index % 3 === 0 ? "#a78bfa" : color,
      score: 56 + index * 4,
      phase: index * 0.44,
    };
  });
}

function makeNodes(brief: AgentBrief): QuantumNode[] {
  const baseColor = STATUS_COLOR[brief.status] ?? "#14b8a6";
  const candidates = brief.top_candidates?.slice(0, 9) ?? [];
  if (!candidates.length) return makeFallbackNodes(baseColor);

  return candidates.map((candidate, index) => {
    const count = Math.max(candidates.length, 1);
    const angle = (index / count) * Math.PI * 2;
    const score = Math.max(0, Math.min(candidate.score ?? 50, 100));
    const radius = 2.9 + score / 46 + (index % 2) * 0.5;
    return {
      key: `${candidate.symbol ?? "node"}-${candidate.timeframe ?? "tf"}-${index}`,
      position: [
        Math.cos(angle) * radius,
        Math.sin(angle * 1.7) * 0.9,
        Math.sin(angle) * 1.65 - 1.15,
      ],
      color: DIRECTION_COLOR[candidate.direction ?? "neutral"] ?? baseColor,
      score,
      phase: index * 0.37 + score / 140,
    };
  });
}

function ParticleMesh() {
  const particles = useMemo(() => {
    const values = new Float32Array(420 * 3);
    for (let index = 0; index < 420; index += 1) {
      const lane = index % 12;
      const angle = (index / 420) * Math.PI * 2 * 7.4;
      const radius = 2.4 + lane * 0.42;
      values[index * 3] = Math.cos(angle) * radius;
      values[index * 3 + 1] = Math.sin(index * 0.43) * 0.72;
      values[index * 3 + 2] = Math.sin(angle) * 1.26 - 1.2;
    }
    return values;
  }, []);

  const ref = useRef<THREE.Points>(null);

  useFrame(({ clock }) => {
    if (!ref.current) return;
    ref.current.rotation.y = clock.elapsedTime * 0.018;
    ref.current.rotation.z = Math.sin(clock.elapsedTime * 0.12) * 0.018;
  });

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={particles.length / 3}
          array={particles}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial color="#f8fafc" size={0.012} transparent opacity={0.22} sizeAttenuation />
    </points>
  );
}

function QuantumAtom({ node, index }: { node: QuantumNode; index: number }) {
  const group = useRef<THREE.Group>(null);
  const core = useRef<THREE.Mesh>(null);
  const ringA = useRef<THREE.Mesh>(null);
  const ringB = useRef<THREE.Mesh>(null);

  useFrame(({ clock }) => {
    const t = clock.elapsedTime + node.phase;
    if (group.current) {
      group.current.position.y = node.position[1] + Math.sin(t * 0.9) * 0.08;
      group.current.rotation.y = t * 0.22;
    }
    if (core.current) {
      core.current.scale.setScalar(1 + Math.sin(t * 1.8) * 0.08);
    }
    if (ringA.current) {
      ringA.current.rotation.x = Math.PI / 2 + t * 0.22;
      ringA.current.rotation.z = t * 0.28;
    }
    if (ringB.current) {
      ringB.current.rotation.y = Math.PI / 3 + t * 0.19;
      ringB.current.rotation.z = -t * 0.18;
    }
  });

  const size = 0.055 + node.score / 1100;

  return (
    <group ref={group} position={node.position}>
      <mesh ref={core}>
        <sphereGeometry args={[size, 24, 24]} />
        <meshStandardMaterial
          color={node.color}
          emissive={node.color}
          emissiveIntensity={1.45}
          roughness={0.28}
          metalness={0.18}
        />
      </mesh>
      <mesh ref={ringA} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[size * 2.45, 0.004, 8, 64]} />
        <meshBasicMaterial color={node.color} transparent opacity={0.4} />
      </mesh>
      <mesh ref={ringB} rotation={[0.8, 0.3, 0.2]}>
        <torusGeometry args={[size * 3.2, 0.003, 8, 72]} />
        <meshBasicMaterial color={index % 2 ? "#fbbf24" : "#a78bfa"} transparent opacity={0.3} />
      </mesh>
    </group>
  );
}

function QuantumLinks({ nodes, baseColor }: { nodes: QuantumNode[]; baseColor: string }) {
  const points = useMemo(() => {
    return nodes.flatMap((node, index) => {
      const next = nodes[(index + 1) % nodes.length];
      const opposite = nodes[(index + 3) % nodes.length];
      return next && opposite
        ? [
            [node.position, next.position] as [Vec3, Vec3],
            [node.position, [0, 0, -1.15] as Vec3] as [Vec3, Vec3],
            [node.position, opposite.position] as [Vec3, Vec3],
          ]
        : [];
    });
  }, [nodes]);

  return (
    <group>
      {points.map((line, index) => (
        <Line
          key={index}
          points={line}
          color={index % 3 === 0 ? "#fbbf24" : index % 2 ? "#a78bfa" : baseColor}
          transparent
          opacity={index % 3 === 0 ? 0.1 : 0.16}
          lineWidth={1}
        />
      ))}
    </group>
  );
}

function CentralReactor({ color, dqs }: { color: string; dqs: number }) {
  const group = useRef<THREE.Group>(null);
  const shell = useRef<THREE.Mesh>(null);

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    if (group.current) {
      group.current.rotation.y = t * 0.1;
      group.current.rotation.x = Math.sin(t * 0.21) * 0.06;
    }
    if (shell.current) {
      shell.current.scale.setScalar(0.82 + Math.min(Math.max(dqs, 0), 100) / 320 + Math.sin(t * 1.1) * 0.025);
    }
  });

  return (
    <group ref={group} position={[0, -0.02, -1.15]}>
      <mesh ref={shell}>
        <icosahedronGeometry args={[0.62, 3]} />
        <meshPhysicalMaterial
          color="#f8fafc"
          emissive={color}
          emissiveIntensity={1.1}
          transparent
          opacity={0.38}
          roughness={0.18}
          metalness={0.24}
          clearcoat={0.8}
        />
      </mesh>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.92, 0.006, 8, 160]} />
        <meshBasicMaterial color="#fbbf24" transparent opacity={0.34} />
      </mesh>
      <mesh rotation={[1.0, 0.42, 0.4]}>
        <torusGeometry args={[1.2, 0.005, 8, 160]} />
        <meshBasicMaterial color="#a78bfa" transparent opacity={0.26} />
      </mesh>
    </group>
  );
}

function QuantumBackplaneModel({ brief }: { brief: AgentBrief }) {
  const nodes = useMemo(() => makeNodes(brief), [brief]);
  const color = STATUS_COLOR[brief.status] ?? "#14b8a6";
  const dqs = brief.dqs?.score ?? 70;

  return (
    <>
      <fog attach="fog" args={["#02030a", 7.5, 15]} />
      <ambientLight intensity={0.36} />
      <pointLight position={[3.2, 1.8, 2.4]} color="#14b8a6" intensity={1.8} />
      <pointLight position={[-3.6, 1.4, -1.7]} color="#a78bfa" intensity={1.1} />
      <pointLight position={[0, -2.2, 2.2]} color="#fbbf24" intensity={0.82} />
      <Stars radius={16} depth={8} count={420} factor={1.75} saturation={0.18} fade speed={0.18} />
      <ParticleMesh />
      <QuantumLinks nodes={nodes} baseColor={color} />
      <CentralReactor color={color} dqs={dqs} />
      {nodes.map((node, index) => (
        <QuantumAtom key={node.key} node={node} index={index} />
      ))}
    </>
  );
}

export function QuantumBackplaneScene({
  brief,
  active = true,
}: {
  brief: AgentBrief;
  active?: boolean;
}) {
  return (
    <div className="quantum-backplane-canvas pointer-events-none absolute inset-x-0 top-0 z-0 h-[1180px] opacity-70 md:h-[1320px]">
      <Canvas
        camera={{ position: [0, 2.45, 8.2], fov: 46 }}
        dpr={[1, 1.5]}
        frameloop={active ? "always" : "never"}
        gl={{ antialias: true, alpha: true, preserveDrawingBuffer: true }}
        className="h-full w-full"
        style={{ width: "100%", height: "100%" }}
      >
        <Suspense fallback={null}>
          <QuantumBackplaneModel brief={brief} />
        </Suspense>
      </Canvas>
    </div>
  );
}
