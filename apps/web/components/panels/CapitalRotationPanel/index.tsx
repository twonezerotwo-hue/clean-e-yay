"use client";

import { useState } from "react";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { useLiquidityRotation } from "@/lib/queries/hooks";
import type {
  LiquidityAssetFlow,
  LiquidityRegime,
  LiquidityWindow,
} from "@/types/generated/api";

const REGIME_LABEL: Record<LiquidityRegime, string> = {
  RISK_ON: "Risk-On",
  CONTROLLED_RISK_ON: "Kontrollu Risk-On",
  NEUTRAL: "Notr",
  RISK_OFF: "Risk-Off",
  CRISIS: "Kriz / Risk-Off",
};

const REGIME_TONE: Record<LiquidityRegime, string> = {
  RISK_ON: "text-emerald-300 border-emerald-400/40 bg-emerald-400/10",
  CONTROLLED_RISK_ON: "text-emerald-200 border-emerald-400/30 bg-emerald-400/[0.08]",
  NEUTRAL: "text-amber-200 border-amber-400/30 bg-amber-400/[0.08]",
  RISK_OFF: "text-red-200 border-red-400/35 bg-red-400/10",
  CRISIS: "text-red-300 border-red-500/45 bg-red-500/[0.12]",
};

const DIR_COLOR: Record<LiquidityAssetFlow["direction"], string> = {
  in: "#34d399",
  out: "#f87171",
  neutral: "#fbbf24",
};
const DIR_LABEL: Record<LiquidityAssetFlow["direction"], string> = {
  in: "giris",
  out: "cikis",
  neutral: "notr",
};
const DIR_BAR: Record<LiquidityAssetFlow["direction"], string> = {
  in: "bg-emerald-400",
  out: "bg-red-400",
  neutral: "bg-amber-300",
};

const WINDOWS = ["1D", "7D", "30D"];

function fmtPct(v: number | null): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}

function FlowMap({ assets, regime }: { assets: LiquidityAssetFlow[]; regime: LiquidityRegime }) {
  // Sıralı sepeti çevreye yay: sol sütun + sağ sütun, ortada likidite havuzu.
  const half = Math.ceil(assets.length / 2);
  const left = assets.slice(0, half);
  const right = assets.slice(half);
  const rowY = (i: number) => 30 + i * 56;

  return (
    <div className="relative grid grid-cols-[1fr_auto_1fr] items-center gap-2">
      <div className="space-y-2">
        {left.map((a) => (
          <FlowNode key={a.symbol} asset={a} align="right" />
        ))}
      </div>

      <div className="relative flex min-h-[260px] w-[120px] items-center justify-center">
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 120 320" aria-hidden>
          {assets.map((a, i) => {
            const onLeft = i < half;
            const y = rowY(onLeft ? i : i - half);
            const w = 1 + Math.abs(a.flow_score - 50) / 12;
            const d = onLeft ? `M0 ${y} C40 ${y}, 46 160, 60 160` : `M120 ${y} C80 ${y}, 74 160, 60 160`;
            return (
              <path
                key={a.symbol}
                d={d}
                fill="none"
                stroke={DIR_COLOR[a.direction]}
                strokeWidth={w}
                strokeDasharray="5 6"
                opacity={0.6}
                className={a.direction === "out" ? "capital-flow-line-reverse" : "capital-flow-line"}
              />
            );
          })}
        </svg>
        <div className="relative grid h-24 w-24 place-items-center rounded-full border border-accent-cyan/25 bg-[radial-gradient(circle_at_35%_25%,rgba(125,211,252,0.7),rgba(37,99,235,0.5)_40%,rgba(3,12,28,0.94)_78%)] text-center shadow-[0_0_44px_rgba(34,211,238,0.22)]">
          <div>
            <div className="text-[9px] uppercase tracking-[0.24em] text-cyan-100">Likidite</div>
            <div className="text-[9px] uppercase tracking-[0.24em] text-cyan-100">Havuzu</div>
          </div>
        </div>
      </div>

      <div className="space-y-2">
        {right.map((a) => (
          <FlowNode key={a.symbol} asset={a} align="left" />
        ))}
      </div>
    </div>
  );
}

function FlowNode({ asset, align }: { asset: LiquidityAssetFlow; align: "left" | "right" }) {
  return (
    <div
      className={`rounded-lg border px-2.5 py-1.5 ${
        asset.direction === "in"
          ? "border-emerald-400/40 bg-emerald-400/[0.08]"
          : asset.direction === "out"
            ? "border-red-400/40 bg-red-400/[0.08]"
            : "border-amber-300/30 bg-amber-300/[0.06]"
      } ${align === "left" ? "text-left" : "text-right"}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs font-semibold text-white/85">{asset.label}</span>
        <span className="font-display text-sm tabular-nums text-white/90">{Math.round(asset.flow_score)}</span>
      </div>
      <div className="mt-0.5 flex items-center justify-between gap-2 text-[10px] uppercase tracking-widest">
        <span style={{ color: DIR_COLOR[asset.direction] }}>{DIR_LABEL[asset.direction]}</span>
        <span className="tabular-nums text-white/45">{fmtPct(asset.return_pct)}</span>
      </div>
    </div>
  );
}

export function CapitalRotationPanel() {
  const { data, isLoading } = useLiquidityRotation();
  const windows = data?.windows ?? [];
  const [win, setWin] = useState("1D");
  const active: LiquidityWindow | undefined = windows.find((w) => w.window === win) ?? windows[0];

  const inflow = active?.assets.filter((a) => a.direction === "in").map((a) => a.label) ?? [];
  const outflow = active?.assets.filter((a) => a.direction === "out").map((a) => a.label) ?? [];

  return (
    <PanelFrame id="capital_rotation" className="border-accent-cyan/20">
      <PanelHeader
        title="Kuresel Likidite Rotasyon Haritasi"
        subtitle="nakit nereye akiyor? — fiyat + hacim + makro (DXY/VIX)"
        actions={
          <div className="flex items-center gap-1">
            {WINDOWS.map((w) => (
              <button
                key={w}
                type="button"
                onClick={() => setWin(w)}
                className={`rounded border px-2 py-1 text-[10px] uppercase tracking-widest transition-colors ${
                  (active?.window ?? "1D") === w
                    ? "border-accent-cyan/45 bg-accent-cyan/12 text-accent-cyan"
                    : "border-white/10 bg-white/[0.03] text-white/45 hover:text-white/75"
                }`}
              >
                {w}
              </button>
            ))}
          </div>
        }
      />

      {isLoading && !active ? (
        <div className="text-xs italic text-white/40">yukleniyor…</div>
      ) : !active ? (
        <div className="text-xs italic text-white/40">veri yok</div>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
          {/* Flow map */}
          <div className="relative overflow-hidden rounded-lg border border-white/10 bg-[#04111f] p-3">
            <div className="pointer-events-none absolute inset-0 opacity-[0.07] [background-image:linear-gradient(rgba(34,211,238,0.65)_1px,transparent_1px),linear-gradient(90deg,rgba(34,211,238,0.65)_1px,transparent_1px)] [background-size:42px_42px]" />
            <div className="relative">
              <FlowMap assets={active.assets} regime={active.regime} />
            </div>
          </div>

          {/* Sağ: rejim + ranking + çelişki */}
          <div className="space-y-3">
            <div className={`rounded-lg border px-3 py-2 ${REGIME_TONE[active.regime]}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] uppercase tracking-widest opacity-70">Rejim</span>
                <span className="font-display text-sm uppercase tracking-wide">
                  {REGIME_LABEL[active.regime]}
                </span>
              </div>
              {active.regime_reasons.length ? (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {active.regime_reasons.map((r, i) => (
                    <span key={i} className="rounded bg-black/25 px-1.5 py-0.5 text-[10px] text-white/60">
                      {r}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>

            <div className="rounded-lg border border-white/10 bg-black/24 p-3">
              <div className="mb-2 flex items-center justify-between text-[10px] uppercase tracking-widest text-white/40">
                <span>Rotasyon siralamasi</span>
                <span>flow / getiri</span>
              </div>
              <div className="space-y-1.5">
                {active.assets.map((a, i) => (
                  <div key={a.symbol} className="flex items-center gap-2">
                    <span className="w-4 shrink-0 text-[10px] tabular-nums text-white/35">{i + 1}</span>
                    <span className="w-20 shrink-0 truncate text-xs text-white/78">{a.label}</span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/10">
                      <div
                        className={`h-full rounded-full ${DIR_BAR[a.direction]}`}
                        style={{ width: `${Math.max(4, Math.min(100, a.flow_score))}%` }}
                      />
                    </div>
                    <span className="w-9 shrink-0 text-right font-display text-xs tabular-nums text-white/85">
                      {Math.round(a.flow_score)}
                    </span>
                    <span className="w-14 shrink-0 text-right text-[10px] tabular-nums text-white/40">
                      {fmtPct(a.return_pct)}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-lg border border-white/10 bg-black/24 px-3 py-2 text-[11px] leading-5">
              <span className="text-emerald-300">Ana giris:</span>{" "}
              <span className="text-white/72">{inflow.length ? inflow.join(", ") : "—"}</span>
              <span className="mx-2 text-white/20">•</span>
              <span className="text-red-300">Ana cikis:</span>{" "}
              <span className="text-white/72">{outflow.length ? outflow.join(", ") : "—"}</span>
            </div>

            {active.contradictions.length ? (
              <div className="rounded-lg border border-amber-400/35 bg-amber-400/[0.08] px-3 py-2">
                {active.contradictions.map((c, i) => (
                  <div key={i} className="flex items-start gap-2 text-[11px] leading-5 text-amber-100">
                    <span className="mt-0.5">⚠</span>
                    {c}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      )}

      <div className="mt-2 border-t border-white/8 pt-2 text-center text-[9px] uppercase tracking-widest text-white/30">
        PAPER_SAFE / NO_EXECUTION / ETF-flow MVP'de yok — momentum+hacim+makro
      </div>
    </PanelFrame>
  );
}
