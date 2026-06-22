"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { useRegimeReport } from "@/lib/queries/hooks";
import { REGIME_COLOR } from "@/lib/constants";

type ScenarioWeight = {
  id: "risk_on" | "base" | "risk_off";
  label: string;
  value: number;
  tone: string;
  bar: string;
  trigger: string;
};

function normalize(values: [number, number, number]) {
  const total = values.reduce((sum, value) => sum + Math.max(0, value), 0) || 1;
  return values.map((value) => Math.round((Math.max(0, value) / total) * 100)) as [number, number, number];
}

function scenarioWeights(data: ReturnType<typeof useRegimeReport>["data"]): ScenarioWeight[] {
  const assets = data?.assets ?? [];
  const layers = data?.layers ?? [];
  const bullishAssets = assets.filter((asset) => asset.direction === "bullish");
  const bearishAssets = assets.filter((asset) => asset.direction === "bearish");
  const neutralAssets = assets.filter((asset) => asset.direction === "neutral");
  const bullishLayerScore = layers
    .filter((layer) => layer.direction === "bullish")
    .reduce((sum, layer) => sum + layer.score, 0);
  const bearishLayerScore = layers
    .filter((layer) => layer.direction === "bearish")
    .reduce((sum, layer) => sum + layer.score, 0);
  const neutralLayerScore = layers
    .filter((layer) => layer.direction === "neutral")
    .reduce((sum, layer) => sum + layer.score, 0);

  // Ağırlıklar YALNIZCA backend skorlarından (yön bazında asset + layer skoru).
  // Frontend sabit/bonus eklemez — regime_label zaten bu skorlardan türediği için
  // ayrıca eklemek çift sayım olur (panel başlığındaki "derived from backend" iddiası).
  const riskOnRaw =
    bullishAssets.reduce((sum, asset) => sum + asset.score, 0) + bullishLayerScore;
  const riskOffRaw =
    bearishAssets.reduce((sum, asset) => sum + asset.score, 0) + bearishLayerScore;
  const baseRaw =
    neutralAssets.reduce((sum, asset) => sum + asset.score, 0) + neutralLayerScore;
  const [riskOn, base, riskOff] = normalize([riskOnRaw, baseRaw, riskOffRaw]);

  return [
    {
      id: "risk_on",
      label: "Risk-on",
      value: riskOn,
      tone: "text-emerald-300",
      bar: "bg-emerald-300",
      trigger: bullishAssets.length ? bullishAssets.slice(0, 3).map((asset) => asset.symbol).join(" / ") : "bullish layer confirmation",
    },
    {
      id: "base",
      label: "Base",
      value: base,
      tone: "text-amber-300",
      bar: "bg-amber-300",
      trigger: `${data?.regime_label ?? "regime"} / balanced evidence`,
    },
    {
      id: "risk_off",
      label: "Risk-off",
      value: riskOff,
      tone: "text-red-300",
      bar: "bg-red-300",
      trigger: bearishAssets.length ? bearishAssets.slice(0, 3).map((asset) => asset.symbol).join(" / ") : "restrictive layer pressure",
    },
  ];
}

export function ScenarioPanel() {
  const { data } = useRegimeReport();
  const regime = data?.regime_label ?? "WAIT";
  const scenarios = scenarioWeights(data);
  const dominant = scenarios.slice().sort((a, b) => b.value - a.value)[0];
  const clash = Math.min(1, Math.abs(scenarios[0].value - scenarios[2].value) / 100);

  return (
    <PanelFrame id="scenario" className="border-accent-cyan/20">
      <PanelHeader
        title="Senaryo"
        subtitle="risk-on / base / risk-off visual battle"
        actions={
          <span className={`rounded border border-white/10 bg-white/[0.04] px-2 py-1 text-[10px] uppercase tracking-widest ${REGIME_COLOR[regime] ?? "text-white/70"}`}>
            {regime}
          </span>
        }
      />
      <div className="relative overflow-hidden rounded-lg border border-white/10 bg-[radial-gradient(circle_at_50%_20%,rgba(34,211,238,0.18),transparent_42%),linear-gradient(180deg,rgba(3,13,28,0.98),rgba(1,5,13,0.98))]">
        <div className="pointer-events-none absolute inset-0 opacity-[0.08] [background-image:linear-gradient(rgba(34,211,238,0.7)_1px,transparent_1px),linear-gradient(90deg,rgba(34,211,238,0.7)_1px,transparent_1px)] [background-size:44px_44px]" />

        <div className="relative px-3 pt-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.24em] text-accent-cyan/75">
                Scenario engine
              </div>
              <div className="text-[11px] text-white/45">
                weights are derived from backend layer and asset scores
              </div>
            </div>
            <div className={`font-display text-2xl ${dominant.tone}`}>%{dominant.value}</div>
          </div>
        </div>

        <div className="relative mt-2 min-h-[270px] overflow-hidden">
          <div className="absolute bottom-0 left-0 right-0 h-[34%] bg-[linear-gradient(180deg,transparent,rgba(0,0,0,0.75))]" />
          <div className="scenario-clash absolute left-1/2 top-1/2 h-40 w-40 -translate-x-1/2 -translate-y-1/2 rounded-full"
            style={{
              opacity: 0.72 - clash * 0.24,
              background: "radial-gradient(circle, rgba(255,255,255,0.2), rgba(34,211,238,0.16) 34%, transparent 72%)",
            }}
          />

          <div className="absolute left-[5%] top-[18%] w-[38%]">
            <ScenarioFigure side="left" power={scenarios[0].value} />
          </div>
          <div className="absolute right-[5%] top-[18%] w-[38%]">
            <ScenarioFigure side="right" power={scenarios[2].value} />
          </div>

          <div className="absolute left-1/2 top-[56%] -translate-x-1/2 -translate-y-1/2 text-center">
            <div className={`text-[10px] uppercase tracking-[0.32em] ${dominant.tone}`}>dominant</div>
            <div className={`font-display text-4xl leading-none ${dominant.tone}`}>{dominant.label}</div>
          </div>
        </div>

        <div className="relative grid gap-2 p-3 sm:grid-cols-3">
          {scenarios.map((scenario) => (
            <div key={scenario.id} className="rounded-lg border border-white/10 bg-white/[0.035] p-3">
              <div className="flex items-center justify-between gap-3">
                <span className={`font-display text-sm ${scenario.tone}`}>{scenario.label}</span>
                <span className={`font-display text-xl ${scenario.tone}`}>%{scenario.value}</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                <div className={`h-full rounded-full ${scenario.bar}`} style={{ width: `${scenario.value}%` }} />
              </div>
              <div className="mt-2 min-h-[32px] text-[11px] leading-4 text-white/54">{scenario.trigger}</div>
            </div>
          ))}
        </div>

        <div className="relative border-t border-white/8 px-3 py-2 text-center text-[9px] uppercase tracking-widest text-white/32">
          PAPER_SAFE / NO_EXECUTION / visual scenario weighting only
        </div>
      </div>
    </PanelFrame>
  );
}

function ScenarioFigure({ side, power }: { side: "left" | "right"; power: number }) {
  const isLeft = side === "left";
  const color = isLeft ? "#34d399" : "#f87171";
  const fill = isLeft ? "rgba(16,185,129,0.16)" : "rgba(248,113,113,0.16)";
  const points = isLeft
    ? "8,130 20,72 54,36 96,26 142,48 178,112 145,142 92,118 52,134"
    : "192,130 180,72 146,36 104,26 58,48 22,112 55,142 108,118 148,134";
  const scale = 0.82 + power / 330;

  return (
    <svg
      viewBox="0 0 200 160"
      className="scenario-figure h-full w-full"
      style={{
        transform: `scale(${scale})`,
        filter: `drop-shadow(0 0 ${8 + power / 4}px ${color})`,
      }}
      aria-hidden
    >
      <polygon points={points} fill={fill} stroke={color} strokeWidth="1.6" />
      <polyline
        points={isLeft ? "20,72 96,26 92,118 178,112 54,36 52,134 142,48" : "180,72 104,26 108,118 22,112 146,36 148,134 58,48"}
        fill="none"
        stroke={color}
        strokeWidth="0.75"
        opacity="0.55"
      />
      {[28, 58, 94, 128, 162].map((x, index) => (
        <circle key={index} cx={isLeft ? x : 200 - x} cy={42 + (index % 3) * 30} r="2" fill={color} opacity="0.9" />
      ))}
    </svg>
  );
}
