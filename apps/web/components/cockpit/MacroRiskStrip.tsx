"use client";

import Link from "next/link";
import type { CSSProperties } from "react";

import { QuantumPanelField, getQuantumPanelStyle } from "@/components/shell/QuantumPanelField";
import { useCockpitBrief, useRegimeReport } from "@/lib/queries/hooks";
import { selectAgentBrief } from "@/lib/selectors/cockpit";
import type { RegimeLayer } from "@/types/generated/api";

type Tone = "good" | "neutral" | "watch" | "risk" | "hedge";

const TONE_CLASS: Record<Tone, string> = {
  good: "border-emerald-400/35 bg-emerald-400/10 text-emerald-200",
  neutral: "border-white/15 bg-white/[0.04] text-white/65",
  watch: "border-cyan-400/35 bg-cyan-400/10 text-cyan-200",
  risk: "border-red-400/35 bg-red-400/10 text-red-200",
  hedge: "border-fuchsia-400/35 bg-fuchsia-400/10 text-fuchsia-200",
};

function findLayer(layers: RegimeLayer[] | undefined, words: string[]) {
  const normalized = words.map((w) => w.toLowerCase());
  return (layers ?? []).find((layer) => {
    const name = layer.name.toLowerCase();
    return normalized.some((word) => name.includes(word));
  });
}

function layerTone(layer?: RegimeLayer): Tone {
  if (!layer) return "neutral";
  if (layer.direction === "bearish") return layer.score >= 65 ? "risk" : "neutral";
  if (layer.direction === "bullish") return layer.score >= 65 ? "good" : "watch";
  return "neutral";
}

function Chip({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: Tone;
}) {
  return (
    <span
      className={`inline-flex min-h-[26px] items-center gap-1 rounded-full border px-2 py-1 text-[10px] uppercase tracking-widest ${TONE_CLASS[tone]}`}
    >
      <span className="text-white/42">{label}</span>
      <span className="font-semibold">{value}</span>
    </span>
  );
}

export function MacroRiskStrip() {
  const { data: regime } = useRegimeReport();
  const brief = selectAgentBrief(useCockpitBrief().data);
  const layers = regime?.layers ?? [];
  const macro = findLayer(layers, ["macro", "makro", "liquidity", "likidite"]);
  const risk = findLayer(layers, ["risk", "appetite", "istah"]);
  const rotation = findLayer(layers, ["rotation", "rotasyon", "capital", "sermaye"]);
  const catalyst = findLayer(layers, ["catalyst", "haber", "news", "olay"]);
  const structure = findLayer(layers, ["structure", "market", "piyasa"]);
  const eventRisk = regime?.event_risk;
  const dataMode = brief?.data_mode ?? "WAIT";

  return (
    <section
      className="quantum-panel rounded-lg border border-white/10 bg-[#070c13]/88 p-3 shadow-[0_0_32px_rgba(20,184,166,0.08)]"
      style={getQuantumPanelStyle("macro_risk_filter", "#14b8a6", "#fbbf24") as CSSProperties}
    >
      <QuantumPanelField id="macro_risk_filter" density="compact" />
      <div className="relative z-10 flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-accent-cyan shadow-[0_0_14px_rgba(34,211,238,0.95)]" />
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-[0.24em] text-accent-cyan/80">
              Macro / Risk Filter
            </div>
            <div className="truncate text-[11px] text-white/45">
              regime, event risk, data trust and capital rotation context
            </div>
          </div>
        </div>
        <Link
          href="/dashboard#catalyst_impact"
          className="rounded border border-accent-cyan/30 bg-accent-cyan/8 px-2 py-1 text-[10px] uppercase tracking-widest text-accent-cyan/90 hover:bg-accent-cyan/15"
        >
          Details
        </Link>
      </div>

      <div className="relative z-10 mt-3 flex flex-wrap gap-2">
        <Chip
          label="Regime"
          value={regime?.regime_label ?? "waiting"}
          tone={regime?.regime_label === "CRISIS" ? "risk" : regime?.regime_label === "OFFENSIVE" ? "good" : "watch"}
        />
        <Chip label="Data" value={dataMode} tone={dataMode === "BLOCKED" ? "risk" : dataMode === "LIVE_VERIFIED" ? "good" : "neutral"} />
        <Chip label="Macro" value={macro ? `${Math.round(macro.score)}` : "--"} tone={layerTone(macro)} />
        <Chip label="Risk" value={risk ? `${Math.round(risk.score)}` : "--"} tone={layerTone(risk)} />
        <Chip label="Rotation" value={rotation ? `${Math.round(rotation.score)}` : "--"} tone={layerTone(rotation)} />
        <Chip label="Catalyst" value={catalyst ? `${Math.round(catalyst.score)}` : "--"} tone={eventRisk?.restrictive ? "risk" : layerTone(catalyst)} />
        <Chip label="Structure" value={structure ? `${Math.round(structure.score)}` : "--"} tone={layerTone(structure)} />
        <Chip
          label="Event gate"
          value={eventRisk?.level ?? "NONE"}
          tone={eventRisk?.restrictive ? "risk" : eventRisk?.level === "WATCH" ? "hedge" : "good"}
        />
      </div>
    </section>
  );
}
