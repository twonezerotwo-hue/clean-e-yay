"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { useDataSnapshot } from "@/lib/queries/hooks";
import { selectOptions } from "@/lib/selectors/snapshot";
import type { OptionsRegime, OptionsSnapshot } from "@/types/generated/api";

// v2.7 D3 — Options IV / Skew / Term Structure paneli. Deribit (veya fixture)
// options chain → ATM IV, 25Δ skew proxy, put/call OI, term structure ve
// realized-vs-implied spread. Yalnızca BTC/ETH ve YALNIZCA KISITLAYICI etki.
// skew_25d GERÇEK 25Δ greeks DEĞİLDİR (is_proxy). Frontend hesap yapmaz; karar
// etkisi backend gate'inde üretilir, burada yalnızca gösterilir.

// Rejim → karar etkisi etiketi (saf sunum; backend options_risk gate'te uygular).
const REGIME: Record<OptionsRegime, { label: string; impact: string; tone: string }> = {
  NORMAL: { label: "normal", impact: "yalnızca bağlam", tone: "text-white/40 border-white/10" },
  RICH_VOL: {
    label: "pahalı vol",
    impact: "size ×0.5 (CAUTION)",
    tone: "text-orange-300 border-orange-400/40 bg-orange-400/10",
  },
  CHEAP_VOL: {
    label: "ucuz vol",
    impact: "bağlam · boost YOK",
    tone: "text-amber-300 border-amber-400/40 bg-amber-400/10",
  },
  PUT_SKEW_STRESS: {
    label: "put skew stresi",
    impact: "long → size ×0.5",
    tone: "text-signal-down border-signal-down/40 bg-signal-down/10",
  },
  CALL_SKEW_EUPHORIA: {
    label: "call skew öforisi",
    impact: "long chase → size ×0.5",
    tone: "text-orange-300 border-orange-400/40 bg-orange-400/10",
  },
  TERM_STRESS: {
    label: "term stresi",
    impact: "açılış durur (NO_POS_INC)",
    tone: "text-signal-down border-signal-down/40 bg-signal-down/10",
  },
};

const FRESH_TONE: Record<string, string> = {
  FRESH: "text-signal-up/80",
  RECENT: "text-amber-300/80",
  STALE: "text-signal-down/80",
};

function fmtPct(v: number | null | undefined, digits = 1): string {
  return v == null ? "—" : `${(v * 100).toFixed(digits)}%`;
}

function fmtVolPt(v: number | null | undefined): string {
  if (v == null) return "—";
  const pt = v * 100;
  return `${pt >= 0 ? "+" : ""}${pt.toFixed(1)} vp`;
}

function OptRow({ o }: { o: OptionsSnapshot }) {
  if (o.status !== "OK") {
    return (
      <div className="rounded border border-white/10 px-2 py-1.5">
        <div className="flex items-center justify-between">
          <span className="font-medium">{o.symbol}</span>
          <span className="rounded border border-signal-down/40 bg-signal-down/10 px-1.5 py-px text-[9px] uppercase tracking-wider text-signal-down">
            {o.status}
          </span>
        </div>
        <p className="mt-0.5 text-[10px] text-white/40">
          {o.error ?? "options verisi yok"} — karar zincirine girmez (mock yok).
        </p>
      </div>
    );
  }
  const r = REGIME[o.regime];
  return (
    <div className="rounded border border-white/10 px-2 py-1.5">
      <div className="flex items-center justify-between">
        <span className="font-medium">{o.symbol}</span>
        <span className={`rounded border px-1.5 py-px text-[9px] uppercase tracking-wider ${r.tone}`}>
          {r.label}
        </span>
      </div>
      <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px] text-white/70 tabular-nums">
        <span>
          ATM IV <span className="text-accent-cyan">{fmtPct(o.atm_iv)}</span>
        </span>
        <span className="text-white/50">realized {fmtPct(o.realized_vol)}</span>
        <span>
          IV−RV{" "}
          <span className={(o.iv_rv_spread ?? 0) >= 0 ? "text-orange-300" : "text-signal-up"}>
            {fmtVolPt(o.iv_rv_spread)}
          </span>
        </span>
        <span>
          25Δ skew{" "}
          <span className={(o.skew_25d ?? 0) < 0 ? "text-signal-down" : "text-accent-cyan"}>
            {fmtVolPt(o.skew_25d)}
          </span>
        </span>
        <span>put/call OI {o.put_call_oi_ratio == null ? "—" : o.put_call_oi_ratio.toFixed(2)}</span>
        <span className="text-white/50">term {fmtVolPt(o.term_slope)}</span>
      </div>
      <div className="mt-0.5 text-[10px] text-white/40 tabular-nums">
        term: {o.front_expiry ?? "—"} {fmtPct(o.term_front_iv)} → {o.next_expiry ?? "—"}{" "}
        {fmtPct(o.term_next_iv)} → {o.long_expiry ?? "—"} {fmtPct(o.term_long_iv)}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9px] uppercase tracking-wider">
        <span className={`rounded border px-1 py-px ${r.tone}`}>{r.impact}</span>
        <span className="text-white/35">{o.source}</span>
        {o.freshness ? (
          <span className={FRESH_TONE[o.freshness] ?? "text-white/40"}>{o.freshness}</span>
        ) : null}
        <span className="text-white/35">DQS {Math.round(o.dqs)}</span>
        {o.is_proxy ? (
          <span className="rounded border border-white/15 px-1 py-px text-white/45">skew proxy</span>
        ) : null}
        {!o.verified ? (
          <span className="rounded border border-amber-400/40 bg-amber-400/10 px-1 py-px text-amber-300">
            doğrulanmamış · bağlam
          </span>
        ) : null}
      </div>
    </div>
  );
}

export function OptionsVolPanel() {
  const { data } = useDataSnapshot();
  const rows = selectOptions(data);
  return (
    <PanelFrame id="options_vol">
      <PanelHeader
        title="Options IV / Skew"
        subtitle="ATM IV · 25Δ skew proxy · term structure (BTC/ETH)"
      />
      {!rows.length ? (
        <div className="text-xs italic text-white/40">options verisi yok</div>
      ) : (
        <div className="space-y-1.5">
          {rows.map((o) => (
            <OptRow key={o.symbol} o={o} />
          ))}
          <p className="pt-0.5 text-[9px] leading-snug text-white/30">
            25Δ skew bir VEKİLDİR (moneyness tabanlı, gerçek greeks değil). Karar
            etkisi yalnızca kısıtlayıcı; asla size artırmaz (CHEAP_VOL bile yalnızca
            bağlam). RiskGate / DQS / halt bypass edilmez.
          </p>
        </div>
      )}
    </PanelFrame>
  );
}
