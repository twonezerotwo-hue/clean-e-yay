"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { MobileFlipCard } from "@/components/cockpit/MobileFlipCard";
import { api } from "@/lib/api/client";
import { useLiquidityRotation } from "@/lib/queries/hooks";
import type {
  LiquidityAssetFlow,
  LiquidityRotation,
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
  CONTROLLED_RISK_ON:
    "text-emerald-200 border-emerald-400/30 bg-emerald-400/[0.08]",
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

function fmtPct(value: number | null): string {
  if (value == null) return "--";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function flowPressure(asset: LiquidityAssetFlow) {
  const pressure = Math.abs(asset.flow_score - 50);
  return Math.max(0.32, Math.min(1, 0.42 + pressure / 58));
}

function FlowMap({
  assets,
  regime,
}: {
  assets: LiquidityAssetFlow[];
  regime: LiquidityRegime;
}) {
  const half = Math.ceil(assets.length / 2);
  const left = assets.slice(0, half);
  const right = assets.slice(half);
  const rows = Math.max(left.length, right.length, 1);
  const mapHeight = 320;
  const rowGap = 12;
  const rowHeight = (mapHeight - rowGap * Math.max(0, rows - 1)) / rows;
  const rowY = (index: number) => rowHeight / 2 + index * (rowHeight + rowGap);
  const strongest = assets[0];

  return (
    <div
      className="capital-rotation-map relative grid grid-cols-[minmax(0,1fr)_minmax(162px,200px)_minmax(0,1fr)] items-center gap-3"
      style={
        {
          "--flow-row-count": rows,
          "--flow-row-gap": `${rowGap}px`,
          "--flow-map-height": `${mapHeight}px`,
        } as CSSProperties
      }
    >
      <div className="capital-map-haze" aria-hidden="true" />

      <div className="capital-flow-column">
        {left.map((asset, index) => (
          <FlowNode key={asset.symbol} asset={asset} align="right" index={index} />
        ))}
      </div>

      <div className="capital-flow-axis relative flex items-center justify-center">
        <svg
          className="capital-flow-svg absolute inset-y-0 left-1/2 h-full w-[250px] -translate-x-1/2"
          viewBox={`0 0 230 ${mapHeight}`}
          aria-hidden="true"
        >
          <defs>
            <filter id="capital-flow-glow" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="3.5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <marker
              id="capital-flow-arrow-in"
              markerHeight="8"
              markerWidth="8"
              orient="auto"
              refX="7"
              refY="4"
              viewBox="0 0 8 8"
            >
              <path d="M1 1.4 7 4 1 6.6Z" fill="#34d399" />
            </marker>
            <marker
              id="capital-flow-arrow-out"
              markerHeight="8"
              markerWidth="8"
              orient="auto-start-reverse"
              refX="1"
              refY="4"
              viewBox="0 0 8 8"
            >
              <path d="M7 1.4 1 4 7 6.6Z" fill="#f87171" />
            </marker>
          </defs>

          {assets.map((asset, index) => {
            const onLeft = index < half;
            const y = rowY(onLeft ? index : index - half);
            const pressure = flowPressure(asset);
            const width = 1.2 + pressure * 3.2;
            const d = onLeft
              ? `M4 ${y} C52 ${y}, 70 ${mapHeight / 2}, 115 ${mapHeight / 2}`
              : `M226 ${y} C178 ${y}, 160 ${mapHeight / 2}, 115 ${mapHeight / 2}`;
            const pathId = `capital-flow-${index}-${asset.symbol.replace(/[^a-zA-Z0-9]/g, "")}`;
            const markerProps =
              asset.direction === "in"
                ? { markerEnd: "url(#capital-flow-arrow-in)" }
                : asset.direction === "out"
                  ? { markerStart: "url(#capital-flow-arrow-out)" }
                  : {};

            return (
              <g key={asset.symbol}>
                <path id={pathId} d={d} fill="none" opacity="0" />
                <path
                  d={d}
                  fill="none"
                  stroke={DIR_COLOR[asset.direction]}
                  strokeWidth={width}
                  strokeLinecap="round"
                  strokeDasharray={asset.direction === "neutral" ? "3 10" : "10 8"}
                  opacity={asset.direction === "neutral" ? 0.42 : 0.74}
                  filter="url(#capital-flow-glow)"
                  {...markerProps}
                  className={
                    asset.direction === "out"
                      ? "capital-flow-line-reverse"
                      : "capital-flow-line"
                  }
                />
                {asset.direction !== "neutral" ? (
                  <circle
                    r={2.4 + pressure * 2.2}
                    fill={DIR_COLOR[asset.direction]}
                    opacity="0.96"
                  >
                    <animateMotion
                      dur={`${2.6 - pressure * 0.8}s`}
                      begin={`${0.18 + index * 0.23}s`}
                      repeatCount="indefinite"
                    >
                      <mpath href={`#${pathId}`} />
                    </animateMotion>
                  </circle>
                ) : null}
              </g>
            );
          })}
        </svg>

        <div
          className="capital-money-pool capital-core"
          data-regime={regime}
          style={
            {
              "--pool-color": strongest ? DIR_COLOR[strongest.direction] : "#22d3ee",
            } as CSSProperties
          }
        >
          <div className="capital-pool-backplate" aria-hidden="true" />
          <div className="capital-pool-orbit capital-pool-orbit-a" aria-hidden="true" />
          <div className="capital-pool-orbit capital-pool-orbit-b" aria-hidden="true" />
          <div className="capital-pool-vault-ring" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
          </div>
          <div className="capital-pool-liquid" aria-hidden="true">
            <span />
            <span />
          </div>
          <div className="capital-pool-depth" aria-hidden="true" />
          <div className="capital-money-stack" aria-hidden="true">
            <i />
            <i />
            <i />
            <i />
            <i />
          </div>
          <div className="capital-coin-field" aria-hidden="true">
            <i />
            <i />
            <i />
            <i />
            <i />
            <i />
          </div>
          <div className="capital-pool-glint" aria-hidden="true" />
          <div className="capital-pool-label">
            <span>Likidite</span>
            <strong>Havuzu</strong>
          </div>
        </div>
      </div>

      <div className="capital-flow-column">
        {right.map((asset, index) => (
          <FlowNode
            key={asset.symbol}
            asset={asset}
            align="left"
            index={index + half}
          />
        ))}
      </div>
    </div>
  );
}

function FlowNode({
  asset,
  align,
  index,
}: {
  asset: LiquidityAssetFlow;
  align: "left" | "right";
  index: number;
}) {
  return (
    <div
      className={`capital-flow-node rounded-lg border px-2.5 py-1.5 ${
        asset.direction === "in"
          ? "border-emerald-400/40 bg-emerald-400/[0.08]"
          : asset.direction === "out"
            ? "border-red-400/40 bg-red-400/[0.08]"
            : "border-amber-300/30 bg-amber-300/[0.06]"
      } ${align === "left" ? "text-left" : "text-right"}`}
      style={
        {
          "--node-color": DIR_COLOR[asset.direction],
          "--node-delay": `${index * 0.11}s`,
        } as CSSProperties
      }
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs font-semibold text-white/85">
          {asset.label}
        </span>
        <span className="font-display text-sm tabular-nums text-white/90">
          {Math.round(asset.flow_score)}
        </span>
      </div>
      <div className="mt-0.5 flex items-center justify-between gap-2 text-[10px] uppercase tracking-widest">
        <span style={{ color: DIR_COLOR[asset.direction] }}>
          {DIR_LABEL[asset.direction]}
        </span>
        <span className="tabular-nums text-white/45">{fmtPct(asset.return_pct)}</span>
      </div>
    </div>
  );
}

export function CapitalRotationPanel() {
  const { data, isLoading } = useLiquidityRotation();
  const [fallbackData, setFallbackData] = useState<LiquidityRotation | null>(null);
  const effectiveData = data ?? fallbackData;
  const windows = effectiveData?.windows ?? [];
  const [win, setWin] = useState("1D");
  const active: LiquidityWindow | undefined =
    windows.find((window) => window.window === win) ?? windows[0];
  const rankedAssets = useMemo(
    () => [...(active?.assets ?? [])].sort((a, b) => b.flow_score - a.flow_score),
    [active?.assets],
  );

  const inflow =
    active?.assets.filter((asset) => asset.direction === "in").map((asset) => asset.label) ??
    [];
  const outflow =
    active?.assets
      .filter((asset) => asset.direction === "out")
      .map((asset) => asset.label) ?? [];

  useEffect(() => {
    if (data || fallbackData) return;
    let cancelled = false;
    void api.liquidityRotation().then((next) => {
      if (!cancelled) setFallbackData(next);
    }).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [data, fallbackData]);

  return (
    <>
    <div className="h-full">
    <PanelFrame id="capital_rotation" className="h-full border-accent-cyan/20">
      <PanelHeader
        title="Kuresel Likidite Rotasyon Haritasi"
        subtitle="nakit nereye akiyor? - fiyat + hacim + makro (DXY/VIX)"
        actions={
          <div className="flex items-center gap-1">
            {WINDOWS.map((window) => (
              <button
                key={window}
                type="button"
                onClick={() => setWin(window)}
                className={`rounded border px-2 py-1 text-[10px] uppercase tracking-widest transition-colors ${
                  (active?.window ?? "1D") === window
                    ? "border-accent-cyan/45 bg-accent-cyan/12 text-accent-cyan"
                    : "border-white/10 bg-white/[0.03] text-white/45 hover:text-white/75"
                }`}
              >
                {window}
              </button>
            ))}
          </div>
        }
      />

      {isLoading && !active ? (
        <div className="text-xs italic text-white/40">yukleniyor...</div>
      ) : !active ? (
        <div className="text-xs italic text-white/40">veri yok</div>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
          <div className="capital-rotation-stage relative overflow-hidden rounded-lg border border-white/10 bg-[#04111f] p-3">
            <div className="capital-stage-grid pointer-events-none absolute inset-0" />
            <div className="relative">
              <FlowMap assets={active.assets} regime={active.regime} />
            </div>
          </div>

          <div className="space-y-3">
            <div className={`rounded-lg border px-3 py-2 ${REGIME_TONE[active.regime]}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] uppercase tracking-widest opacity-70">
                  Rejim
                </span>
                <span className="font-display text-sm uppercase tracking-wide">
                  {REGIME_LABEL[active.regime]}
                </span>
              </div>
              {active.regime_reasons.length ? (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {active.regime_reasons.map((reason, index) => (
                    <span
                      key={index}
                      className="rounded bg-black/25 px-1.5 py-0.5 text-[10px] text-white/60"
                    >
                      {reason}
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
                {rankedAssets.map((asset, index) => (
                  <div
                    key={`${active.window}-${asset.symbol}`}
                    className="capital-rank-row flex items-center gap-2"
                    style={
                      {
                        "--rank-color": DIR_COLOR[asset.direction],
                        "--rank-delay": `${index * 0.08}s`,
                      } as CSSProperties
                    }
                  >
                    <span className="capital-rank-index w-4 shrink-0 text-[10px] tabular-nums text-white/35">
                      {index + 1}
                    </span>
                    <span className="w-20 shrink-0 truncate text-xs text-white/78">
                      {asset.label}
                    </span>
                    <div className="capital-rank-track h-1.5 flex-1 overflow-hidden rounded-full bg-white/10">
                      <div
                        className={`capital-rank-fill h-full rounded-full ${DIR_BAR[asset.direction]}`}
                        style={{
                          width: `${Math.max(4, Math.min(100, asset.flow_score))}%`,
                        }}
                      />
                    </div>
                    <span className="w-9 shrink-0 text-right font-display text-xs tabular-nums text-white/85">
                      {Math.round(asset.flow_score)}
                    </span>
                    <span className="w-14 shrink-0 text-right text-[10px] tabular-nums text-white/40">
                      {fmtPct(asset.return_pct)}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-lg border border-white/10 bg-black/24 px-3 py-2 text-[11px] leading-5">
              <span className="text-emerald-300">Ana giris:</span>{" "}
              <span className="text-white/72">
                {inflow.length ? inflow.join(", ") : "--"}
              </span>
              <span className="mx-2 text-white/20">/</span>
              <span className="text-red-300">Ana cikis:</span>{" "}
              <span className="text-white/72">
                {outflow.length ? outflow.join(", ") : "--"}
              </span>
            </div>

            {active.contradictions.length ? (
              <div className="rounded-lg border border-amber-400/35 bg-amber-400/[0.08] px-3 py-2">
                {active.contradictions.map((item, index) => (
                  <div
                    key={index}
                    className="flex items-start gap-2 text-[11px] leading-5 text-amber-100"
                  >
                    <span className="mt-0.5">!</span>
                    {item}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      )}
    </PanelFrame>
    </div>
    <MobileFlipCard
      className="mobile-force-hidden"
      title="Küresel Likidite Rotasyonu"
      front={
        <div className="mobile-capital-front">
          <div className="mobile-back-head">
            <div>
              <p className="mobile-kicker">Küresel Likidite Rotasyonu</p>
              <strong>{active ? REGIME_LABEL[active.regime] : "Veri yok"}</strong>
            </div>
            <span>{active?.window ?? win}</span>
          </div>

          <div className="mobile-window-tabs" data-no-flip>
            {WINDOWS.map((window) => (
              <button
                key={window}
                type="button"
                onClick={() => setWin(window)}
                className={(active?.window ?? "1D") === window ? "is-active" : ""}
              >
                {window}
              </button>
            ))}
          </div>

          {isLoading && !active ? (
            <p className="mobile-summary-line">Yükleniyor...</p>
          ) : !active ? (
            <p className="mobile-summary-line">Veri yok.</p>
          ) : (
            <>
              <div className="mobile-capital-pool">
                <div className="capital-money-pool capital-core" data-regime={active.regime}>
                  <div className="capital-pool-backplate" aria-hidden="true" />
                  <div className="capital-pool-liquid" aria-hidden="true">
                    <span />
                    <span />
                  </div>
                  <div className="capital-money-stack" aria-hidden="true">
                    <i />
                    <i />
                    <i />
                    <i />
                    <i />
                  </div>
                  <div className="capital-pool-label">
                    <span>Likidite</span>
                    <strong>Havuzu</strong>
                  </div>
                </div>
              </div>
              <div className="mobile-rank-list">
                {rankedAssets.slice(0, 3).map((asset, index) => (
                  <MobileCapitalRow key={asset.symbol} asset={asset} index={index} />
                ))}
              </div>
              <p className="mobile-summary-line">
                Ana giriş: {inflow.length ? inflow.slice(0, 2).join(", ") : "--"} / Ana çıkış:{" "}
                {outflow.length ? outflow.slice(0, 2).join(", ") : "--"}
              </p>
            </>
          )}
          <p className="mobile-flip-hint">Detay için dokun</p>
        </div>
      }
      back={
        <div className="mobile-flip-card__scroll mobile-capital-back">
          <div className="mobile-back-head">
            <div>
              <p className="mobile-kicker">Rotasyon sıralaması</p>
              <strong>{active ? REGIME_LABEL[active.regime] : "Veri yok"}</strong>
            </div>
            <span>flow / getiri</span>
          </div>

          {active ? (
            <>
              <div className="mobile-rank-list mobile-rank-list--full">
                {rankedAssets.map((asset, index) => (
                  <MobileCapitalRow key={`${active.window}-${asset.symbol}`} asset={asset} index={index} />
                ))}
              </div>
              {active.regime_reasons.length ? (
                <div className="mobile-reason-box">
                  <p className="mobile-kicker">Rejim nedenleri</p>
                  {active.regime_reasons.map((reason, index) => (
                    <span key={index}>{reason}</span>
                  ))}
                </div>
              ) : null}
              {active.contradictions.length ? (
                <div className="mobile-reason-box is-warning">
                  <p className="mobile-kicker">Çelişkiler</p>
                  {active.contradictions.map((item, index) => (
                    <span key={index}>{item}</span>
                  ))}
                </div>
              ) : null}
            </>
          ) : (
            <p className="mobile-summary-line">Veri yok.</p>
          )}
        </div>
      }
    />
    </>
  );
}

function MobileCapitalRow({
  asset,
  index,
}: {
  asset: LiquidityAssetFlow;
  index: number;
}) {
  return (
    <div
      className="mobile-capital-row"
      style={
        {
          "--rank-color": DIR_COLOR[asset.direction],
          "--rank-delay": `${index * 0.08}s`,
        } as CSSProperties
      }
    >
      <span>{index + 1}</span>
      <div>
        <strong>{asset.label}</strong>
        <em>{DIR_LABEL[asset.direction]}</em>
      </div>
      <div className="mobile-capital-bar">
        <i style={{ width: `${Math.max(4, Math.min(100, asset.flow_score))}%` }} />
      </div>
      <b>{Math.round(asset.flow_score)}</b>
      <small>{fmtPct(asset.return_pct)}</small>
    </div>
  );
}
