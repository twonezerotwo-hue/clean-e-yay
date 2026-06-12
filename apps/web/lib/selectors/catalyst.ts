import type {
  CatalystActionability,
  CatalystImpact,
  DataSnapshot,
} from "@/types/generated/api";

// v2.7 D5 — haber → catalyst half-life zekâsı. Frontend hesap yapmaz; backend
// CatalystImpact'lerini gösterir. Sıralama yalnızca sunum (kısıtlayıcı önce).

const ACTION_RANK: Record<CatalystActionability, number> = {
  NO_POSITION_INCREASE: 3,
  CAUTION: 2,
  WATCH: 1,
  CONTEXT_ONLY: 0,
};

export const selectCatalystImpacts = (
  s: DataSnapshot | undefined,
): CatalystImpact[] => {
  const items = s?.catalyst_impacts ?? [];
  return [...items].sort(
    (a, b) => ACTION_RANK[b.actionability] - ACTION_RANK[a.actionability],
  );
};

/** valid_until'a kalan dakika (yarı-ömür geri sayımı). null → bilinmiyor. */
export const catalystRemainingMinutes = (
  c: CatalystImpact,
  now: number = Date.now(),
): number | null => {
  if (!c.valid_until) return null;
  const ms = new Date(c.valid_until).getTime() - now;
  return Math.round(ms / 60000);
};

/** Yarı-ömrü dolmuş + verified mi? Süresi dolmuş → yalnızca bağlam. */
export const catalystIsActive = (
  c: CatalystImpact,
  now: number = Date.now(),
): boolean => {
  if (!c.verified || c.actionability === "CONTEXT_ONLY") return false;
  const rem = catalystRemainingMinutes(c, now);
  return rem === null || rem > 0;
};
