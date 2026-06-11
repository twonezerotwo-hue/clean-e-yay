import type { MistakesState, MistakeVerdict } from "@/types/generated/api";

export const selectFlagged = (s: MistakesState | undefined): MistakeVerdict[] =>
  (s?.verdicts ?? []).filter((v) =>
    ["AVOID", "BOOST", "WARNING"].includes(v.action),
  );

export const selectRecordsByFp = (s: MistakesState | undefined) => {
  const map = new Map<string, MistakesState["records"][number]>();
  (s?.records ?? []).forEach((r) => map.set(r.fingerprint, r));
  return map;
};

export const selectCounts = (s: MistakesState | undefined) => ({
  total: s?.total_fingerprints ?? 0,
  flagged: s?.flagged_count ?? 0,
});
