import type {
  EventOutcomeRecord,
  EventOutcomeStatus,
  EventOutcomeUpcoming,
  EventOutcomesView,
} from "@/types/generated/api";

/** Olay-sonrası takip — panel seçicileri (frontend hesap yapmaz; backend ölçer). */
export const EVENT_OUTCOME_STATUS_LABEL: Record<EventOutcomeStatus, string> = {
  UPCOMING: "bekleniyor",
  AWAITING_RESULT: "açıklandı · sonuç bekleniyor",
  MEASURING: "tepki ölçülüyor",
  DONE: "tamamlandı",
};

/** Açıklanmış (UPCOMING olmayan) ve son `hours` saat içindeki olaylar, en yeni önce. */
export const selectRecentEventOutcomes = (
  vm: EventOutcomesView | undefined,
  now: number,
  hours = 48,
  limit = 3,
): EventOutcomeRecord[] =>
  (vm?.recent ?? [])
    .filter((r) => r.status !== "UPCOMING")
    .filter((r) => now - new Date(r.release_ts).getTime() <= hours * 3_600_000)
    .slice(0, limit);

export const selectNextEvent = (vm: EventOutcomesView | undefined): EventOutcomeUpcoming | undefined =>
  (vm?.upcoming ?? []).find((u) => u.minutes_until >= 0);

/** Satır sırası: önce beklenen yönü olan semboller, sonra en çok hareket edenler. */
export const selectOutcomeRows = (rec: EventOutcomeRecord, horizons: string[], extra = 3) => {
  const expected = Object.keys(rec.expected);
  const lastMoves = horizons
    .map((h) => rec.realized[h]?.moves)
    .filter((m): m is Record<string, number> => Boolean(m && Object.keys(m).length))
    .pop() ?? {};
  const measured = new Set(horizons.flatMap((h) => Object.keys(rec.realized[h]?.moves ?? {})));
  const movers = Object.keys(lastMoves)
    .filter((s) => !rec.expected[s])
    .sort((a, b) => Math.abs(lastMoves[b]) - Math.abs(lastMoves[a]))
    .slice(0, extra);
  return [...expected.filter((s) => measured.has(s) || !measured.size), ...movers].map((symbol) => ({
    symbol,
    expected: rec.expected[symbol] ?? 0,
    cells: horizons.map((h) => ({
      horizon: h,
      move: rec.realized[h]?.moves?.[symbol],
      mark: rec.realized[h]?.hits?.per_asset?.[symbol],
    })),
  }));
};
