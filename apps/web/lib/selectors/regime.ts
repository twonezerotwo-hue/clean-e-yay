import type { EventRiskView, RegimeReport } from "@/types/generated/api";

export const selectTopAssets = (r: RegimeReport | undefined, n = 8) =>
  (r?.assets ?? [])
    .slice()
    .sort((a, b) => b.score - a.score)
    .slice(0, n);

export const selectConfirmedAssets = (r: RegimeReport | undefined) =>
  (r?.assets ?? []).filter((a) => a.status === "CONFIRMED");

export const selectHeadlines = (r: RegimeReport | undefined, n = 12) =>
  (r?.headlines ?? []).slice(0, n);

export const selectCatalysts = (r: RegimeReport | undefined, n = 10) =>
  (r?.catalysts ?? []).slice(0, n);

/** P0 — olay riski özeti (yalnızca kısıtlayıcı; frontend hesap yapmaz). */
export const selectEventRisk = (
  r: RegimeReport | undefined,
): EventRiskView | undefined => r?.event_risk;

/** Bir haberin etkilediği semboller → "SEM ↑/↓" rozet etiketleri. */
export const headlineImpactBadges = (impact?: Record<string, number>) =>
  Object.entries(impact ?? {}).map(([symbol, dir]) => ({
    symbol,
    arrow: dir > 0 ? "↑" : dir < 0 ? "↓" : "→",
    dir,
  }));
