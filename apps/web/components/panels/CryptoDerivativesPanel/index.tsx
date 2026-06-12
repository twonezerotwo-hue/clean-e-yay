"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { useDataSnapshot } from "@/lib/queries/hooks";
import { selectDerivatives } from "@/lib/selectors/snapshot";
import type { DerivativesSnapshot, SqueezeLevel } from "@/types/generated/api";

// v2.7 D2 — Crypto Derivatives Intelligence paneli. Funding / OI / squeeze
// proxy yalnızca kripto sembolleri için ve YALNIZCA KISITLAYICI etki yapar.
// squeeze_proxy GERÇEK liquidation DEĞİLDİR (is_proxy). Frontend hesap yapmaz;
// karar etkisi backend gate'inde üretilir, burada yalnızca gösterilir.

// Karar etkisi etiketi — saf sunum eşlemesi (hesap değil; backend squeeze_level'i
// gate'te uygular: HIGH → açılış durur, ELEVATED → size ×0.5).
const IMPACT: Record<SqueezeLevel, { label: string; tone: string }> = {
  NONE: { label: "yalnızca bağlam", tone: "text-white/40 border-white/10" },
  LOW: { label: "izle (WATCH)", tone: "text-amber-300 border-amber-400/40 bg-amber-400/10" },
  ELEVATED: {
    label: "size ×0.5 (CAUTION)",
    tone: "text-orange-300 border-orange-400/40 bg-orange-400/10",
  },
  HIGH: {
    label: "açılış durur (NO_POS_INC)",
    tone: "text-signal-down border-signal-down/40 bg-signal-down/10",
  },
};

const FRESH_TONE: Record<string, string> = {
  FRESH: "text-signal-up/80",
  RECENT: "text-amber-300/80",
  STALE: "text-signal-down/80",
};

function fmtUsd(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toFixed(0)}`;
}

function fmtPct(v: number | null, digits = 2): string {
  return v == null ? "—" : `${(v * 100).toFixed(digits)}%`;
}

function DerivRow({ d }: { d: DerivativesSnapshot }) {
  if (d.status === "DEGRADED") {
    return (
      <div className="rounded border border-white/10 px-2 py-1.5">
        <div className="flex items-center justify-between">
          <span className="font-medium">{d.symbol}</span>
          <span className="rounded border border-signal-down/40 bg-signal-down/10 px-1.5 py-px text-[9px] uppercase tracking-wider text-signal-down">
            DEGRADED
          </span>
        </div>
        <p className="mt-0.5 text-[10px] text-white/40">
          {d.error ?? "türev verisi yok"} — karar zincirine girmez (mock yok).
        </p>
      </div>
    );
  }
  const impact = IMPACT[d.squeeze_level];
  return (
    <div className="rounded border border-white/10 px-2 py-1.5">
      <div className="flex items-center justify-between">
        <span className="font-medium">{d.symbol}</span>
        <span className={`rounded border px-1.5 py-px text-[9px] uppercase tracking-wider ${impact.tone}`}>
          squeeze {d.squeeze_level} · {Math.round(d.squeeze_proxy)}
        </span>
      </div>
      <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px] text-white/70 tabular-nums">
        <span>
          funding{" "}
          <span className={d.funding_bias === "neutral" ? "text-white/60" : "text-accent-cyan"}>
            {fmtPct(d.funding_rate, 4)}/8s
          </span>
        </span>
        <span className="text-white/50">{d.funding_bias}</span>
        <span>OI {fmtUsd(d.open_interest_usd)}</span>
        <span className="text-white/50">
          ΔOI {d.oi_change_pct == null ? "—" : `${d.oi_change_pct >= 0 ? "+" : ""}${fmtPct(d.oi_change_pct, 1)}`}
        </span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9px] uppercase tracking-wider">
        <span className={`rounded border px-1 py-px ${impact.tone}`}>{impact.label}</span>
        <span className="text-white/35">{d.source}</span>
        {d.freshness ? (
          <span className={FRESH_TONE[d.freshness] ?? "text-white/40"}>{d.freshness}</span>
        ) : null}
        <span className="text-white/35">DQS {Math.round(d.dqs)}</span>
        {!d.verified ? (
          <span className="rounded border border-amber-400/40 bg-amber-400/10 px-1 py-px text-amber-300">
            doğrulanmamış · bağlam
          </span>
        ) : null}
      </div>
    </div>
  );
}

export function CryptoDerivativesPanel() {
  const { data } = useDataSnapshot();
  const rows = selectDerivatives(data);
  return (
    <PanelFrame id="crypto_derivatives">
      <PanelHeader
        title="Kripto Türevleri"
        subtitle="funding · OI · squeeze proxy (gerçek liq değil)"
      />
      {!rows.length ? (
        <div className="text-xs italic text-white/40">türev verisi yok</div>
      ) : (
        <div className="space-y-1.5">
          {rows.map((d) => (
            <DerivRow key={d.symbol} d={d} />
          ))}
          <p className="pt-0.5 text-[9px] leading-snug text-white/30">
            squeeze_proxy bir VEKİLDİR (funding + OI + momentum + volatilite) —
            gerçek liquidation API&apos;si değildir. Karar etkisi yalnızca
            kısıtlayıcı; asla size artırmaz.
          </p>
        </div>
      )}
    </PanelFrame>
  );
}
