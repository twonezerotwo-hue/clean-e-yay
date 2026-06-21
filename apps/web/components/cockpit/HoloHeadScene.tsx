"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { Suspense, useMemo, useRef } from "react";
import * as THREE from "three";

/**
 * HoloHeadScene — 2047 holografik insan büstü (point-cloud).
 *
 * Saf prosedürel: bir baş+boyun+omuz silüetini yatay "tarama" dilimlerine
 * bölüp her dilime parçacık halkası yerleştiriyoruz (topographic hologram
 * estetiği). Model dosyası yok — tamamen kod. Renk/aktiflik dışarıdan
 * `tone` ile gelir (ok/warn/alert) → backend durumuna bağlanabilir.
 *
 * GÖRSEL — karar üretmez.
 */

type Tone = "idle" | "ok" | "warn" | "alert";

const TONE_COLOR: Record<Tone, string> = {
  idle: "#22d3ee",
  ok: "#34d399",
  warn: "#fbbf24",
  alert: "#f87171",
};

// Büst silüeti: [yükseklik, yarıçap] kontrol noktaları (yukarıdan aşağı).
// Baş (egg) → çene → boyun → omuzlar → göğüs.
const PROFILE: [number, number][] = [
  [1.18, 0.04],
  [1.08, 0.2],
  [0.98, 0.3],
  [0.86, 0.37],
  [0.74, 0.38], // kafatası en geniş
  [0.62, 0.36], // yüz
  [0.5, 0.32], // yanaklar
  [0.4, 0.26], // çene hattı
  [0.32, 0.19], // çene ucu
  [0.24, 0.14], // boyun üst
  [0.1, 0.13], // boyun
  [0.0, 0.17], // boyun dibi
  [-0.12, 0.32], // trapez
  [-0.24, 0.54], // omuz
  [-0.36, 0.67], // omuz geniş
  [-0.54, 0.73],
  [-0.78, 0.75],
  [-1.05, 0.71],
];

function radiusAt(y: number): number {
  if (y >= PROFILE[0][0]) return PROFILE[0][1];
  if (y <= PROFILE[PROFILE.length - 1][0]) return PROFILE[PROFILE.length - 1][1];
  for (let i = 0; i < PROFILE.length - 1; i += 1) {
    const [y0, r0] = PROFILE[i];
    const [y1, r1] = PROFILE[i + 1];
    if (y <= y0 && y >= y1) {
      const t = (y - y0) / (y1 - y0);
      return r0 + (r1 - r0) * t;
    }
  }
  return 0.2;
}

function buildBust(): { positions: Float32Array; sizes: Float32Array } {
  const yTop = 1.18;
  const yBottom = -1.05;
  const slices = 64;
  const pts: number[] = [];
  const szs: number[] = [];

  for (let s = 0; s <= slices; s += 1) {
    const y = yTop - (s / slices) * (yTop - yBottom);
    const r = radiusAt(y);
    if (r <= 0.001) continue;
    // Dilim çevresine, yarıçapla orantılı parçacık sayısı.
    const count = Math.max(10, Math.round(r * 120));
    for (let i = 0; i < count; i += 1) {
      const a = (i / count) * Math.PI * 2 + (s % 2) * 0.18;
      // Yüze derinlik: ön (z>0) hafif öne çıkar (egg yüz profili).
      const front = Math.cos(a) > 0 ? 1.12 : 0.95;
      const jitter = 0.012;
      const x = Math.cos(a) * r * 1.0 + (Math.random() - 0.5) * jitter;
      const z = Math.sin(a) * r * front + (Math.random() - 0.5) * jitter;
      const yy = y + (Math.random() - 0.5) * jitter;
      pts.push(x, yy, z);
      szs.push(Math.random() < 0.12 ? 2.4 : 1.3);
    }
  }

  // Yüz işaret noktaları — gözler (parlak), öne bakan iki nokta.
  const eyeY = 0.66;
  const eyeR = radiusAt(eyeY);
  for (const sign of [-1, 1]) {
    pts.push(sign * eyeR * 0.42, eyeY, eyeR * 1.04);
    szs.push(4.2);
  }

  return { positions: new Float32Array(pts), sizes: new Float32Array(szs) };
}

function Bust({ color }: { color: THREE.Color }) {
  const ref = useRef<THREE.Points>(null);
  const { positions, sizes } = useMemo(() => buildBust(), []);

  const geom = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    g.setAttribute("aSize", new THREE.BufferAttribute(sizes, 1));
    return g;
  }, [positions, sizes]);

  useFrame((state) => {
    if (!ref.current) return;
    const t = state.clock.elapsedTime;
    ref.current.rotation.y = Math.sin(t * 0.18) * 0.5 - 0.25;
    ref.current.position.y = Math.sin(t * 0.6) * 0.04;
  });

  return (
    <points ref={ref} geometry={geom}>
      <pointsMaterial
        size={0.03}
        sizeAttenuation
        color={color}
        transparent
        opacity={0.92}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

function OrbitRing({
  radius,
  tilt,
  speed,
  color,
  opacity = 0.5,
}: {
  radius: number;
  tilt: [number, number, number];
  speed: number;
  color: THREE.Color;
  opacity?: number;
}) {
  const ref = useRef<THREE.Line>(null);
  const geom = useMemo(() => {
    const pts: THREE.Vector3[] = [];
    for (let i = 0; i <= 128; i += 1) {
      const a = (i / 128) * Math.PI * 2;
      pts.push(new THREE.Vector3(Math.cos(a) * radius, 0, Math.sin(a) * radius));
    }
    return new THREE.BufferGeometry().setFromPoints(pts);
  }, [radius]);

  useFrame((state) => {
    if (ref.current) ref.current.rotation.y = state.clock.elapsedTime * speed;
  });

  return (
    // @ts-expect-error drei/three line primitive
    <line ref={ref} geometry={geom} rotation={tilt}>
      <lineBasicMaterial color={color} transparent opacity={opacity} blending={THREE.AdditiveBlending} />
    </line>
  );
}

function BaseDisc({ color }: { color: THREE.Color }) {
  const ref = useRef<THREE.Points>(null);
  const positions = useMemo(() => {
    const arr: number[] = [];
    const rings = 7;
    for (let r = 0; r < rings; r += 1) {
      const radius = 0.5 + r * 0.18;
      const count = 40 + r * 14;
      for (let i = 0; i < count; i += 1) {
        const a = (i / count) * Math.PI * 2;
        arr.push(Math.cos(a) * radius, -1.18, Math.sin(a) * radius);
      }
    }
    return new Float32Array(arr);
  }, []);

  const geom = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    return g;
  }, [positions]);

  useFrame((state) => {
    if (ref.current) ref.current.rotation.y = -state.clock.elapsedTime * 0.12;
  });

  return (
    <points ref={ref} geometry={geom}>
      <pointsMaterial
        size={0.028}
        sizeAttenuation
        color={color}
        transparent
        opacity={0.55}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

function Scene({ tone }: { tone: Tone }) {
  const color = useMemo(() => new THREE.Color(TONE_COLOR[tone]), [tone]);
  const accent = useMemo(() => new THREE.Color("#a78bfa"), []);

  return (
    <>
      <ambientLight intensity={0.4} />
      <Bust color={color} />
      <OrbitRing radius={1.5} tilt={[1.35, 0, 0.1]} speed={0.32} color={color} opacity={0.45} />
      <OrbitRing radius={1.9} tilt={[1.2, 0.4, -0.2]} speed={-0.22} color={accent} opacity={0.32} />
      <OrbitRing radius={2.4} tilt={[1.5, 0, 0.3]} speed={0.16} color={color} opacity={0.22} />
      <BaseDisc color={color} />
    </>
  );
}

export function HoloHeadScene({ tone = "idle" }: { tone?: Tone }) {
  return (
    <div className="holo-head-canvas absolute inset-0">
      <Canvas
        camera={{ position: [0.6, 0.35, 4.2], fov: 42 }}
        dpr={[1, 1.75]}
        gl={{ antialias: true, alpha: true }}
        className="h-full w-full"
        style={{ width: "100%", height: "100%" }}
      >
        <Suspense fallback={null}>
          <Scene tone={tone} />
        </Suspense>
      </Canvas>
    </div>
  );
}
