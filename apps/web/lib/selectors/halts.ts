import type { HaltEvent, HaltsState } from "@/types/generated/api";

export const selectHaltActive = (s: HaltsState | undefined): boolean =>
  s?.halt_active ?? false;

export const selectActiveHalts = (s: HaltsState | undefined): HaltEvent[] =>
  s?.active ?? [];

/** En yeni önce (backend zaten sıralı gönderir). */
export const selectTimeline = (s: HaltsState | undefined): HaltEvent[] =>
  s?.timeline ?? [];

/** Gauge değerleri — backend hesaplar, frontend sadece gösterir. */
export const selectGauges = (s: HaltsState | undefined) => ({
  dailyLossRatio: s?.metrics?.daily_loss_ratio ?? 0,
  dailyPnlUsd: s?.metrics?.daily_pnl_usd ?? 0,
  dailyLossLimitUsd: s?.metrics?.daily_loss_limit_usd ?? 0,
  drawdownRatio: s?.metrics?.drawdown_ratio ?? 0,
  drawdownPct: s?.metrics?.drawdown_pct ?? 0,
  maxDrawdownPct: s?.metrics?.max_drawdown_pct ?? 0,
});

/** En kısıtlayıcı aktif halt seviyesi (badge için). */
export const selectHaltLevel = (
  s: HaltsState | undefined,
): "KILL_SWITCH" | "RISK_REDUCE" | null => {
  const active = s?.active ?? [];
  if (active.some((h) => h.level === "KILL_SWITCH")) return "KILL_SWITCH";
  if (active.some((h) => h.level === "RISK_REDUCE")) return "RISK_REDUCE";
  return null;
};
