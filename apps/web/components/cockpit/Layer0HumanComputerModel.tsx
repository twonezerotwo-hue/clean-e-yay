"use client";

import { Line } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { Suspense, useMemo, useRef } from "react";
import * as THREE from "three";

type ModelMode = "idle" | "listening" | "thinking" | "speaking";
type Vec3 = [number, number, number];

const MODE_COLOR: Record<ModelMode, string> = {
  idle: "#22d3ee",
  listening: "#34d399",
  thinking: "#fbbf24",
  speaking: "#a78bfa",
};

function NeuralParticles({ mode }: { mode: ModelMode }) {
  const points = useRef<THREE.Points>(null);
  const positions = useMemo(() => {
    const data = new Float32Array(620 * 3);
    for (let index = 0; index < 620; index += 1) {
      const radius = 2.2 + Math.random() * 3.4;
      const theta = Math.random() * Math.PI * 2;
      const y = (Math.random() - 0.5) * 3.4;
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
        { radius: 1.18, tube: 0.006, rotation: [Math.PI / 2.1, 0, 0.16] as Vec3, opacity: 0.52 },
        { radius: 1.78, tube: 0.007, rotation: [1.1, 0.32, 0.82] as Vec3, opacity: 0.34 },
        { radius: 2.34, tube: 0.005, rotation: [1.8, -0.46, -0.42] as Vec3, opacity: 0.26 },
      ].map((ring) => (
        <mesh key={`${ring.radius}-${ring.opacity}`} rotation={ring.rotation}>
          <torusGeometry args={[ring.radius, ring.tube, 8, 192]} />
          <meshBasicMaterial color={color} transparent opacity={ring.opacity} />
        </mesh>
      ))}
      <mesh position={[0, -1.42, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.54, 0.018, 10, 220]} />
        <meshBasicMaterial color="#67e8f9" transparent opacity={0.44} />
      </mesh>
      <mesh position={[0, -1.44, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.42, 1.52, 180]} />
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

function FaceCircuits({ mode }: { mode: ModelMode }) {
  const color = MODE_COLOR[mode];
  const lines: Vec3[][] = [
    [
      [-0.22, 1.38, 0.53],
      [-0.12, 1.28, 0.58],
      [0.02, 1.28, 0.6],
      [0.16, 1.36, 0.56],
    ],
    [
      [0.28, 1.58, 0.45],
      [0.46, 1.48, 0.36],
      [0.5, 1.22, 0.28],
    ],
    [
      [-0.42, 1.58, 0.36],
      [-0.52, 1.42, 0.28],
      [-0.42, 1.24, 0.36],
    ],
    [
      [-0.06, 1.72, 0.56],
      [0.05, 1.82, 0.5],
      [0.22, 1.78, 0.44],
    ],
  ];

  return (
    <group>
      {lines.map((points, index) => (
        <Line
          key={index}
          points={points}
          color={index % 2 ? "#67e8f9" : color}
          transparent
          opacity={0.72}
          lineWidth={1}
        />
      ))}
      {[
        [-0.26, 1.48, 0.55],
        [0.24, 1.48, 0.55],
        [0.46, 1.25, 0.3],
        [-0.48, 1.32, 0.3],
        [0.04, 1.82, 0.5],
      ].map((position, index) => (
        <mesh key={index} position={position as Vec3}>
          <sphereGeometry args={[0.024, 14, 14]} />
          <meshBasicMaterial color={index % 2 ? "#67e8f9" : color} transparent opacity={0.9} />
        </mesh>
      ))}
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

function HumanComputerBust({ mode }: { mode: ModelMode }) {
  const group = useRef<THREE.Group>(null);
  const color = MODE_COLOR[mode];

  useFrame(({ clock }) => {
    if (!group.current) return;
    const t = clock.elapsedTime;
    group.current.rotation.y = Math.sin(t * 0.28) * 0.13;
    group.current.position.y = Math.sin(t * 1.12) * 0.025;
  });

  return (
    <group ref={group}>
      <mesh position={[0, 1.46, 0]} scale={[0.66, 0.86, 0.56]}>
        <sphereGeometry args={[0.72, 64, 64]} />
        <meshPhysicalMaterial
          color="#c8fbff"
          emissive={color}
          emissiveIntensity={1.18}
          roughness={0.18}
          metalness={0.16}
          clearcoat={1}
          transparent
          opacity={0.54}
          transmission={0.35}
        />
      </mesh>
      <mesh position={[0.2, 1.45, 0.015]} scale={[0.4, 0.82, 0.48]}>
        <sphereGeometry args={[0.72, 32, 32, 0, Math.PI]} />
        <meshBasicMaterial color={color} wireframe transparent opacity={0.32} />
      </mesh>
      <mesh position={[0, 0.62, 0]} scale={[0.9, 0.8, 0.36]}>
        <sphereGeometry args={[0.98, 64, 32]} />
        <meshPhysicalMaterial
          color="#e0f7ff"
          emissive="#0ea5e9"
          emissiveIntensity={0.58}
          roughness={0.22}
          metalness={0.34}
          transparent
          opacity={0.34}
          clearcoat={0.9}
        />
      </mesh>
      <mesh position={[0, 0.88, 0]} scale={[0.22, 0.42, 0.18]}>
        <cylinderGeometry args={[0.24, 0.32, 0.6, 32]} />
        <meshPhysicalMaterial color="#a7f3d0" emissive={color} emissiveIntensity={0.45} transparent opacity={0.44} />
      </mesh>
      <mesh position={[-0.23, 1.5, 0.52]}>
        <sphereGeometry args={[0.045, 24, 24]} />
        <meshBasicMaterial color="#e0f2fe" transparent opacity={0.95} />
      </mesh>
      <mesh position={[0.23, 1.5, 0.52]}>
        <sphereGeometry args={[0.045, 24, 24]} />
        <meshBasicMaterial color="#e0f2fe" transparent opacity={0.95} />
      </mesh>
      <FaceCircuits mode={mode} />
      <VoiceAnalyzer mode={mode} />
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

function Scene({ mode }: { mode: ModelMode }) {
  const color = MODE_COLOR[mode];

  return (
    <>
      <color attach="background" args={["#020712"]} />
      <fog attach="fog" args={["#020712", 5, 10.4]} />
      <ambientLight intensity={0.36} />
      <pointLight position={[2.6, 3.2, 3.6]} color="#67e8f9" intensity={4.1} />
      <pointLight position={[-3.2, 1.2, 1.6]} color={color} intensity={2.2} />
      <pointLight position={[0, -1.2, 2.8]} color="#fbbf24" intensity={0.9} />
      <NeuralParticles mode={mode} />
      <DataRibbons mode={mode} />
      <HologramRings mode={mode} />
      <HumanComputerBust mode={mode} />
    </>
  );
}

export function Layer0HumanComputerModel({ mode }: { mode: ModelMode }) {
  return (
    <div className="layer0-human-model">
      <Canvas
        camera={{ position: [0, 0.52, 4.55], fov: 42 }}
        dpr={[1, 1.75]}
        gl={{ antialias: true, alpha: false, preserveDrawingBuffer: true }}
      >
        <Suspense fallback={null}>
          <Scene mode={mode} />
        </Suspense>
      </Canvas>
      <div className="layer0-human-model__beam" />
      <div className="layer0-human-model__scan" />
    </div>
  );
}
