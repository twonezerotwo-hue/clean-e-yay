"use client";

import { OrbitControls, Stars, Line } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { Suspense, useMemo, useRef } from "react";
import * as THREE from "three";

import type { AgentBrief, AgentBriefCandidate } from "@/types/generated/api";

type Vec3 = [number, number, number];

const STATUS_COLOR: Record<string, string> = {
  ACTIONABLE: "#10b981",
  NO_ACTION: "#22d3ee",
  WATCHING: "#38bdf8",
  FROZEN: "#f59e0b",
  BLOCKED: "#ef4444",
};

const DIRECTION_COLOR: Record<string, string> = {
  bullish: "#10b981",
  bearish: "#ef4444",
  neutral: "#f59e0b",
};

function candidatePosition(index: number, count: number, score = 0): Vec3 {
  const safeCount = Math.max(count, 1);
  const angle = (index / safeCount) * Math.PI * 2;
  const radius = 2.05 + Math.min(Math.max(score, 0), 100) / 130;
  const y = Math.sin(angle * 1.7) * 0.42;
  return [Math.cos(angle) * radius, y, Math.sin(angle) * radius];
}

function ParticleField() {
  const particles = useMemo(() => {
    const values = new Float32Array(780 * 3);
    for (let i = 0; i < 780; i += 1) {
      const radius = 4.2 + Math.random() * 5.5;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      values[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
      values[i * 3 + 1] = radius * Math.cos(phi) * 0.58;
      values[i * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);
    }
    return values;
  }, []);

  return (
    <points>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={particles.length / 3} array={particles} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial color="#7dd3fc" size={0.018} transparent opacity={0.42} sizeAttenuation />
    </points>
  );
}

function BrainCore({ color, dqs }: { color: string; dqs: number }) {
  const group = useRef<THREE.Group>(null);
  const mesh = useRef<THREE.Mesh>(null);
  const wire = useRef<THREE.Mesh>(null);
  const pulse = 0.72 + Math.min(Math.max(dqs, 0), 100) / 250;

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    if (group.current) {
      group.current.rotation.y = t * 0.18;
      group.current.rotation.x = Math.sin(t * 0.34) * 0.08;
    }
    if (mesh.current) {
      mesh.current.scale.setScalar(pulse + Math.sin(t * 1.7) * 0.025);
    }
    if (wire.current) {
      wire.current.rotation.z = -t * 0.22;
      wire.current.rotation.y = t * 0.12;
    }
  });

  return (
    <group ref={group}>
      <mesh ref={mesh}>
        <icosahedronGeometry args={[0.94, 5]} />
        <meshPhysicalMaterial
          color="#b9f6ff"
          emissive={color}
          emissiveIntensity={1.55}
          roughness={0.22}
          metalness={0.2}
          transparent
          opacity={0.7}
          clearcoat={0.9}
        />
      </mesh>
      <mesh ref={wire}>
        <icosahedronGeometry args={[1.24, 2]} />
        <meshBasicMaterial color={color} wireframe transparent opacity={0.5} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.18, 32, 32]} />
        <meshStandardMaterial color="#ffffff" emissive="#fef3c7" emissiveIntensity={1.1} />
      </mesh>
    </group>
  );
}

function OrbitShell({ color }: { color: string }) {
  const group = useRef<THREE.Group>(null);

  useFrame(({ clock }) => {
    if (!group.current) return;
    const t = clock.elapsedTime;
    group.current.rotation.y = t * 0.11;
    group.current.rotation.z = Math.sin(t * 0.22) * 0.1;
  });

  return (
    <group ref={group}>
      {[
        { radius: 1.62, rot: [Math.PI / 2, 0.1, 0] as Vec3, opacity: 0.52 },
        { radius: 2.05, rot: [1.08, 0.36, 0.62] as Vec3, opacity: 0.34 },
        { radius: 2.48, rot: [1.82, -0.36, -0.48] as Vec3, opacity: 0.24 },
      ].map((ring) => (
        <mesh key={ring.radius} rotation={ring.rot}>
          <torusGeometry args={[ring.radius, 0.008, 8, 192]} />
          <meshBasicMaterial color={color} transparent opacity={ring.opacity} />
        </mesh>
      ))}
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <ringGeometry args={[2.78, 2.79, 192]} />
        <meshBasicMaterial color="#f59e0b" transparent opacity={0.18} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

function CandidateSatellites({
  candidates,
}: {
  candidates: AgentBriefCandidate[];
}) {
  const group = useRef<THREE.Group>(null);
  const positions = useMemo(
    () =>
      candidates.slice(0, 8).map((candidate, index) => ({
        candidate,
        position: candidatePosition(index, Math.min(candidates.length, 8), candidate.score ?? 0),
      })),
    [candidates],
  );

  useFrame(({ clock }) => {
    if (!group.current) return;
    group.current.rotation.y = clock.elapsedTime * 0.24;
  });

  if (!positions.length) {
    return null;
  }

  return (
    <group ref={group}>
      {positions.map(({ candidate, position }, index) => {
        const color = DIRECTION_COLOR[candidate.direction ?? "neutral"] ?? "#f59e0b";
        const size = 0.07 + Math.min(candidate.score ?? 0, 100) / 900;
        return (
          <group key={`${candidate.symbol ?? "candidate"}-${index}`} position={position}>
            <Line points={[[0, 0, 0], [-position[0] * 0.7, -position[1] * 0.7, -position[2] * 0.7]]} color={color} transparent opacity={0.22} lineWidth={1} />
            <mesh>
              <sphereGeometry args={[size, 24, 24]} />
              <meshStandardMaterial color={color} emissive={color} emissiveIntensity={1.2} roughness={0.35} />
            </mesh>
            <mesh>
              <ringGeometry args={[size * 1.7, size * 1.82, 40]} />
              <meshBasicMaterial color={color} transparent opacity={0.32} side={THREE.DoubleSide} />
            </mesh>
          </group>
        );
      })}
    </group>
  );
}

function SynapseWeb({ candidates, color }: { candidates: AgentBriefCandidate[]; color: string }) {
  const lines = useMemo(() => {
    const nodes = candidates
      .slice(0, 8)
      .map((candidate, index) => candidatePosition(index, Math.min(candidates.length, 8), candidate.score ?? 0));
    return nodes.flatMap((node, index) => {
      const next = nodes[(index + 1) % nodes.length];
      return next ? [[node, [0, 0, 0] as Vec3], [node, next] as [Vec3, Vec3]] : [];
    });
  }, [candidates]);

  return (
    <group>
      {lines.map((points, index) => (
        <Line key={index} points={points} color={index % 2 ? "#a78bfa" : color} transparent opacity={0.18} lineWidth={1} />
      ))}
    </group>
  );
}

function BrainModel({ brief }: { brief: AgentBrief }) {
  const color = STATUS_COLOR[brief.status] ?? "#22d3ee";
  const candidates = brief.top_candidates ?? [];
  const dqs = brief.dqs?.score ?? 70;

  return (
    <>
      <color attach="background" args={["#02030a"]} />
      <fog attach="fog" args={["#02030a", 5.8, 12]} />
      <ambientLight intensity={0.36} />
      <pointLight position={[2.5, 2.2, 3.2]} color="#22d3ee" intensity={3.2} />
      <pointLight position={[-3, -1.6, -2.4]} color="#d946ef" intensity={1.4} />
      <pointLight position={[0.2, 3.2, -2.2]} color="#f59e0b" intensity={1.2} />
      <Stars radius={18} depth={12} count={900} factor={2.6} saturation={0.25} fade speed={0.55} />
      <ParticleField />
      <SynapseWeb candidates={candidates} color={color} />
      <OrbitShell color={color} />
      <CandidateSatellites candidates={candidates} />
      <BrainCore color={color} dqs={dqs} />
      <OrbitControls enablePan={false} enableZoom={false} autoRotate autoRotateSpeed={0.35} />
    </>
  );
}

export function SpaceBrainScene({ brief }: { brief: AgentBrief }) {
  return (
    <div className="space-brain-canvas absolute inset-0">
      <Canvas
        camera={{ position: [0, 0.62, 6.1], fov: 45 }}
        dpr={[1, 1.75]}
        gl={{ antialias: true, alpha: false, preserveDrawingBuffer: true }}
        className="h-full w-full"
        style={{ width: "100%", height: "100%" }}
      >
        <Suspense fallback={null}>
          <BrainModel brief={brief} />
        </Suspense>
      </Canvas>
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,rgba(2,3,10,0.94)_0%,rgba(2,3,10,0.58)_30%,rgba(2,3,10,0.14)_54%,rgba(2,3,10,0.7)_100%)]" />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(2,3,10,0.25)_0%,rgba(2,3,10,0)_36%,rgba(2,3,10,0.82)_100%)]" />
      <div className="pointer-events-none absolute inset-0 opacity-[0.08] [background-image:linear-gradient(rgba(255,255,255,0.8)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.8)_1px,transparent_1px)] [background-size:56px_56px]" />
    </div>
  );
}
