import type { RegimeReport } from "@/types/generated/api";

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
