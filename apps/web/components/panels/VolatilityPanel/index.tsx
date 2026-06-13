"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { useDataSnapshot } from "@/lib/queries/hooks";
import { selectVolatility } from "@/lib/selectors/snapshot";
import type { VolatilitySnapshot, VolatilityRegime, VolState } from "@/types/generated/api";

// v2.7 D4 — Realized Volatility / Volatility Regime paneli. Mevcut OHLCV
// cache'inden hesaplanan realized vol + rejim + squeeze/expansion/shock
// bağlamı YALNIZCA KISITLAYICI etki yapar (asla size artırmaz). Frontend
// hesap yapmaz; karar etkisi backend gate'inde üretilir, burada gösterilir.

// Karar etkisi etiketi — saf sunum eşlemesi. Gate (volatility_risk): EXTREME →
// açılış durur (15m/1h tam ağırlık; 1d/1w rejim bağlamına yumuşar),
// ELEVATED → size ×0.5, LOW → izle.
const REGIME_IMPACT: Record<VolatilityRegime, { label: string; tone: string }> = {
  LOW: { label: "düşük vol · izle", tone: "text-accent-cyan/80 border-accent-cyan/30 bg-accent-cyan/5" },
  NORMAL: { label: "yalnızca bağlam", tone: "text-white/40 border-white/10" },
  ELEVATED: {
    label: "size ×0.5 (CAUTION)",
    tone: "text-orange-300 border-orange-400/40 bg-orange-400/10",
  },
  EXTREME: {
    label: "açılış durur (NO_POS_INC)",
    tone: "text-signal-down border-signal-down/40 bg-signal-down/10",
  },
};

const STATE_TONE: Record<VolState, string> = {
  normal: "text-white/35",
  squeeze: "text-accent-cyan/80",
  expansion: "text-amber-300/80",
  shock: "text-signal-down",
};

const FRESH_TONE: Record<string, string> = {
  FRESH: "text-signal-up/80",
  RECENT: "text-amber-300/80",
  STALE: "text-signal-down/80",
};

function fmtPct(v: number | null | undefined, digits = 1): string {
  return v == null ? "—" : `${(v * 100).toFixed(digits)}%`;
}

function VolCell({ v }: { v: VolatilitySnapshot }) {
  if (v.status === "DEGRADED") {
    return (
      <div className="flex items-center justify-between rounded border border-white/10 px-2 py-1 text-[10px]">
        <span className="font-medium text-white/60">{v.timeframe}</span>
        <span className="rounded border border-signal-down/40 bg-signal-down/10 px-1 py-px uppercase tracking-wider text-signal-down">
          DEGRADED
        </span>
      </div>
    );
  }
  const impact = REGIME_IMPACT[v.regime];
  return (
    <div className="rounded border border-white/10 px-2 py-1">
      <div className="flex items-center justify-between text-[11px]">
        <span className="font-medium">{v.timeframe}</span>
        <span className={`rounded border px-1.5 py-px text-[9px] uppercase tracking-wider ${impact.tone}`}>
          {v.regime}
          {v.vol_zscore != null ? ` · z${v.vol_zscore >= 0 ? "+" : ""}${v.vol_zscore.toFixed(1)}` : ""}
        </span>
      </div>
      {/* UX4 — önce karar etkisi; teknik sayılar (rv, vol_state) altta/daha küçük. */}
      <div className="mt-0.5">
        <span className={`inline-block rounded border px-1.5 py-0.5 text-[9px] font-semibold ${impact.tone}`}>
          karar etkisi: {impact.label}
        </span>
      </div>
      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-white/60 tabular-nums">
        <span>
          rv <span className="text-white/80">{fmtPct(v.realized_vol)}</span>
        </span>
        {v.vol_state !== "normal" ? (
          <span className={`uppercase tracking-wider ${STATE_TONE[v.vol_state]}`}>
            {v.vol_state}
          </span>
        ) : null}
        {v.freshness ? (
          <span className={`text-[8px] uppercase ${FRESH_TONE[v.freshness] ?? "text-white/40"}`}>
            {v.freshness}
          </span>
        ) : null}
        {!v.verified ? (
          <span className="rounded border border-amber-400/40 bg-amber-400/10 px-1 py-px text-[8px] uppercase text-amber-300">
            doğrulanmamış
          </span>
        ) : null}
      </div>
    </div>
  );
}

export function VolatilityPanel() {
  const { data } = useDataSnapshot();
  const rows = selectVolatility(data);
  return (
    <PanelFrame id="volatility">
      <PanelHeader
        title="Volatilite Rejimi"
        subtitle="realized vol · z-skoru · squeeze/expansion/shock"
      />
      {!rows.length ? (
        <div className="text-xs italic text-white/40">volatilite verisi yok</div>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => (
            <div key={r.symbol}>
              <div className="mb-1 text-[11px] font-medium text-white/70">{r.symbol}</div>
              <div className="space-y-1">
                {r.cells.map((v) => (
                  <VolCell key={v.timeframe} v={v} />
                ))}
              </div>
            </div>
          ))}
          <p className="pt-0.5 text-[9px] leading-snug text-white/30">
            Realized vol annualize edilmiş log-getiri standart sapmasıdır. Karar
            etkisi yalnızca kısıtlayıcı; 15m/1h&apos;de vol shock daha etkili,
            1d/1w&apos;de rejim bağlamı. Asla size artırmaz.
          </p>
        </div>
      )}
    </PanelFrame>
  );
}
