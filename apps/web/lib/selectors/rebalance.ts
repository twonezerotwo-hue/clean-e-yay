import type { RebalanceState, WeightDelta } from "@/types/generated/api";

export const selectPending = (s: RebalanceState | undefined) =>
  s?.current && s.current.status === "PENDING" ? s.current : null;

export const selectActiveVersion = (s: RebalanceState | undefined) =>
  s?.active_version ?? "—";

export const selectHistory = (s: RebalanceState | undefined) =>
  s?.history ?? [];

export const selectTopDeltas = (
  deltas: WeightDelta[] | undefined,
  n = 6,
): WeightDelta[] => {
  if (!deltas) return [];
  return [...deltas].sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, n);
};
