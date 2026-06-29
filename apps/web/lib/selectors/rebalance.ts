import type {
  RebalanceState,
  WeightAutoApplyEntry,
  WeightDelta,
} from "@/types/generated/api";

export const selectPending = (s: RebalanceState | undefined) =>
  s?.current && s.current.status === "PENDING" ? s.current : null;

export const selectActiveVersion = (s: RebalanceState | undefined) =>
  s?.active_version ?? "—";

export const selectHistory = (s: RebalanceState | undefined) =>
  s?.history ?? [];

// G3 — otomatik-uygulama görünürlüğü (conscious layer).
export const selectAutoApplyActive = (
  s: RebalanceState | undefined,
): WeightAutoApplyEntry | null => s?.auto_apply?.active ?? null;

export const selectAutoApplyLedger = (
  s: RebalanceState | undefined,
): WeightAutoApplyEntry[] => s?.auto_apply?.ledger ?? [];

export const selectTopDeltas = (
  deltas: WeightDelta[] | undefined,
  n = 6,
): WeightDelta[] => {
  if (!deltas) return [];
  return [...deltas].sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, n);
};
