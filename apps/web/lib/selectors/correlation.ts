import type {
  CorrelationEntry,
  CorrelationState,
  ExposureCluster,
} from "@/types/generated/api";

/** Matristen sembol-sıralı kare grid (heatmap render'ı için). */
export const selectMatrixGrid = (
  s: CorrelationState | undefined,
): { symbols: string[]; cell: (a: string, b: string) => CorrelationEntry | null } => {
  const symbols = s?.symbols ?? [];
  const byPair = new Map<string, CorrelationEntry>();
  (s?.matrix ?? []).forEach((e) => {
    byPair.set(`${e.symbol_a}|${e.symbol_b}`, e);
    byPair.set(`${e.symbol_b}|${e.symbol_a}`, e);
  });
  return {
    symbols,
    cell: (a, b) => (a === b ? null : byPair.get(`${a}|${b}`) ?? null),
  };
};

/** Cap'e göre sıralı cluster listesi (backend zaten sıralı gönderir). */
export const selectClusters = (
  s: CorrelationState | undefined,
): ExposureCluster[] => s?.clusters ?? [];

export const selectFlaggedClusters = (
  s: CorrelationState | undefined,
): ExposureCluster[] =>
  (s?.clusters ?? []).filter((c) => c.status !== "OK");

export const selectInsufficientPairs = (
  s: CorrelationState | undefined,
): string[] => s?.insufficient_pairs ?? [];

export const selectLimits = (s: CorrelationState | undefined) => ({
  threshold: s?.threshold ?? 0.7,
  maxClusterPct: s?.max_cluster_pct ?? 0.3,
  windowDays: s?.window_days ?? 30,
});
