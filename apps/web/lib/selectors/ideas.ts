import type { Idea, IdeaBoardView, IdeaKind, IdeaVerdict } from "@/types/generated/api";

/** Fikir Panosu seçicileri — skor/değerlendirme backend'de hesaplanır; burada yalnız sunum. */
export const IDEA_KIND_LABEL: Record<IdeaKind, string> = {
  crypto: "Kripto",
  commodity: "Emtia",
  sector_etf: "Sektör fonu",
};

export const IDEA_VERDICT_TONE: Record<IdeaVerdict, string> = {
  STRONG: "border-emerald-400/40 bg-emerald-400/10 text-emerald-200",
  WATCH: "border-amber-300/40 bg-amber-300/10 text-amber-200",
  WEAK: "border-red-400/40 bg-red-400/10 text-red-200",
};

const BIAS_LABEL: Record<string, string> = {
  BULLISH: "yükseliş eğilimi",
  BEARISH: "düşüş eğilimi",
  NEUTRAL: "nötr",
};

export const biasLabel = (bias?: string | null) => (bias ? BIAS_LABEL[bias.toUpperCase()] ?? bias : null);

export const selectIdeas = (vm: IdeaBoardView | undefined): Idea[] => vm?.ideas ?? [];

export const aiSourceLabel = (source?: string) =>
  !source || source === "deterministic" ? "kurallı değerlendirme" : `yapay zekâ (${source})`;

export const newsArrow = (direction?: string) =>
  direction === "up" ? "↑" : direction === "down" ? "↓" : "→";

/** Öngörü karnesinin 24 saatlik özeti (yoksa null). */
export const selectForecastHitRate = (vm: IdeaBoardView | undefined) => {
  const horizons = (vm?.news?.scorecard?.horizons ?? {}) as Record<string, { all?: { hit_rate?: number | null; n?: number } }>;
  const day = horizons["24h"]?.all;
  return day && typeof day.hit_rate === "number" ? { hitRate: day.hit_rate, n: day.n ?? 0 } : null;
};
