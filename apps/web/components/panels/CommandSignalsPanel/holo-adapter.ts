/**
 * Holographic Command Signals — local data adapter.
 *
 * Bizim AssetSignal + DataSnapshot.prices + technicals_by_tf → legacy
 * "HoloSignal" shape. Backend dokunulmaz; tip tamamen local.
 */
import type { AssetSignal, LivePrice, TechnicalTf, Timeframe } from "@/types/generated/api";

export type HoloAction =
  | "LONG"
  | "LONG_AWAIT"
  | "SHORT"
  | "SHORT_AWAIT"
  | "AVOID"
  | "WATCH";

export type HoloStatus = "CONFIRMED" | "PENDING" | "BLOCKING";

export interface HoloSignal {
  asset_code: string;
  asset_action: HoloAction;
  status: HoloStatus;
  value: number | null;
  unit: string;
  delta_7d_pct: number | null;
  reason: string;
  action_trigger: string | null;
  recommended_timeframe: string | null;
  recheck_interval_minutes: number | null;
  // Per-TF teknik göstergeler — sinyal detayında 4 satır tablo halinde gösterilir.
  technicals: Partial<Record<Timeframe, TechnicalTf>>;
  // Final score (consensus) — sinyal kartında ring olarak gösterilir.
  consensus_score: number;
}

const ACTION_BY: Record<string, Record<string, HoloAction>> = {
  bullish: { CONFIRMED: "LONG",  PENDING: "LONG_AWAIT",  BLOCKING: "AVOID" },
  bearish: { CONFIRMED: "SHORT", PENDING: "SHORT_AWAIT", BLOCKING: "AVOID" },
  neutral: { CONFIRMED: "WATCH", PENDING: "WATCH",       BLOCKING: "AVOID" },
};

function reasonFor(s: AssetSignal): string {
  const direction = s.direction;
  const status = s.status;
  const module = s.dominant_module ?? "consensus";
  if (status === "BLOCKING") {
    return `${s.symbol}: RiskGate veya DQS kısıtlı; baskın katkı ${module}.`;
  }
  if (status === "CONFIRMED") {
    return `${s.symbol}: ${direction} yön onaylandı, baskın katkı ${module}.`;
  }
  return `${s.symbol}: ${direction} aday — consensus eşiği aşılmadı (${module}).`;
}

export function adaptToHolo(
  assets: AssetSignal[],
  prices: LivePrice[] | undefined,
  technicalsByTf: Record<string, Partial<Record<Timeframe, TechnicalTf>>> | undefined,
): HoloSignal[] {
  const priceBy = new Map<string, number>();
  for (const p of prices ?? []) {
    if (p.price !== null && Number.isFinite(p.price)) {
      priceBy.set(p.symbol, p.price);
    }
  }
  return assets.map((s) => {
    const action = ACTION_BY[s.direction]?.[s.status] ?? "WATCH";
    const value = priceBy.get(s.symbol) ?? null;
    const tech = technicalsByTf?.[s.symbol] ?? {};
    return {
      asset_code: s.symbol,
      asset_action: action,
      status: s.status as HoloStatus,
      value,
      unit: value !== null ? "USD" : "",
      delta_7d_pct: null,
      reason: reasonFor(s),
      action_trigger: null,
      recommended_timeframe: null,
      recheck_interval_minutes: null,
      technicals: tech,
      consensus_score: s.score,
    };
  });
}
