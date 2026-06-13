import type { ReplayStatus } from "@/types/generated/api";

/** R1 — replay store durumu (frontend hesap yapmaz; backend alanları okunur). */
export const selectReplayActive = (r: ReplayStatus | undefined): boolean =>
  Boolean(r?.available);

export const selectReplayCount = (r: ReplayStatus | undefined): number =>
  r?.snapshot_count ?? 0;

/** Mode rozeti — backend mode'una göre etiket + renk. */
export const selectReplayModeBadge = (
  r: ReplayStatus | undefined,
): { label: string; tone: "active" | "idle" } => {
  switch (r?.mode) {
    case "active_snapshot_replay":
      return { label: "ACTIVE SNAPSHOT REPLAY", tone: "active" };
    case "insufficient_snapshots":
      return { label: "INSUFFICIENT SNAPSHOTS", tone: "idle" };
    default:
      return { label: "REZERVE · AKTİF DEĞİL", tone: "idle" };
  }
};
