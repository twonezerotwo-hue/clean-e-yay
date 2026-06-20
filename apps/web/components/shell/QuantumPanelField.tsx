import type { CSSProperties } from "react";

const ACCENTS = ["#14b8a6", "#fbbf24", "#a78bfa", "#34d399", "#fb7185", "#22d3ee"];
const SECONDARY = ["#fbbf24", "#a78bfa", "#34d399", "#fb7185", "#14b8a6", "#f59e0b"];

function hashPanelId(id: string) {
  let hash = 0;
  for (let index = 0; index < id.length; index += 1) {
    hash = (hash * 31 + id.charCodeAt(index)) % 997;
  }
  return hash;
}

export function getQuantumPanelStyle(
  id: string,
  accent?: string,
  secondary?: string,
): CSSProperties {
  const hash = hashPanelId(id);
  return {
    "--quantum-accent": accent ?? ACCENTS[hash % ACCENTS.length],
    "--quantum-accent-2": secondary ?? SECONDARY[hash % SECONDARY.length],
    "--quantum-delay": `${-(hash % 11) * 0.28}s`,
  } as CSSProperties;
}

export function QuantumPanelField({
  id,
  density = "normal",
}: {
  id: string;
  density?: "normal" | "compact" | "deck";
}) {
  return (
    <div className={`quantum-panel-field quantum-panel-field-${density}`} aria-hidden="true">
      <span className="quantum-orbit quantum-orbit-a" />
      <span className="quantum-orbit quantum-orbit-b" />
      <span className="quantum-orbit quantum-orbit-c" />
      <span className="quantum-link quantum-link-a" />
      <span className="quantum-link quantum-link-b" />
      <span className="quantum-link quantum-link-c" />
      <span className="quantum-atom quantum-atom-a" />
      <span className="quantum-atom quantum-atom-b" />
      <span className="quantum-atom quantum-atom-c" />
      <span className="quantum-pulse quantum-pulse-a" />
      <span className="quantum-pulse quantum-pulse-b" />
      <span className="quantum-panel-id">{id.replaceAll("_", ".")}</span>
    </div>
  );
}
