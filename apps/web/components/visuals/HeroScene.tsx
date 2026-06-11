"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { useRef } from "react";
import type { Mesh } from "three";

/**
 * Hero — 3D temayı korumak için ince animasyonlu sahne.
 * Eski projedeki 3D layer'ların ruhunu taşır. v2.5'te gerçek veri
 * (rejim, ısı haritası) ile beslenir.
 */
function SpinningCore() {
  const ref = useRef<Mesh>(null);
  useFrame((_, dt) => {
    if (!ref.current) return;
    ref.current.rotation.x += dt * 0.25;
    ref.current.rotation.y += dt * 0.35;
  });
  return (
    <mesh ref={ref}>
      <icosahedronGeometry args={[1.4, 1]} />
      <meshStandardMaterial
        color="#22d3ee"
        wireframe
        emissive="#22d3ee"
        emissiveIntensity={0.35}
      />
    </mesh>
  );
}

export function HeroScene() {
  return (
    <Canvas camera={{ position: [0, 0, 4], fov: 50 }} dpr={[1, 1.6]}>
      <ambientLight intensity={0.3} />
      <pointLight position={[3, 3, 3]} intensity={1.2} color="#d946ef" />
      <pointLight position={[-3, -2, 2]} intensity={0.6} color="#22d3ee" />
      <SpinningCore />
    </Canvas>
  );
}
