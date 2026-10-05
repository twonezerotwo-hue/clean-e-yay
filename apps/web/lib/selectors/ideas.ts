import type {
  Idea,
  IdeaBoardView,
  IdeaKind,
  IdeaVerdict,
  NewsDiscoveryEvent,
  NewsDiscoveryView,
} from "@/types/generated/api";

/** Fikir Panosu seçicileri — skor/değerlendirme backend'de hesaplanır; burada yalnız sunum. */
export const IDEA_KIND_LABEL: Record<IdeaKind, string> = {
  crypto: "Kripto",
  commodity: "Emtia",
  sector_etf: "Sektör fonu",
  news: "Haber keşfi",
};

/** Haber keşfinin doğruladığı varlık türü. */
export const ASSET_TYPE_LABEL: Record<string, string> = {
  equity: "Hisse",
  etf: "Fon (ETF)",
  future: "Vadeli",
  crypto: "Kripto",
  fx: "Döviz",
};

export const ideaKindLabel = (idea: Pick<Idea, "kind" | "asset_type">) =>
  idea.kind === "news" && idea.asset_type
    ? `${IDEA_KIND_LABEL.news} · ${ASSET_TYPE_LABEL[idea.asset_type] ?? idea.asset_type}`
    : IDEA_KIND_LABEL[idea.kind] ?? idea.kind;

export const CONFIDENCE_LABEL: Record<string, string> = { low: "düşük", med: "orta", high: "yüksek" };

/** Doğrulamada elenen önerilerin nedenleri (YZ uydurması / yanlış eşleme şeffaf görünür). */
const REJECT_LABEL: Record<string, string> = {
  sembol_yok: "sembol yok",
  ad_uyusmuyor: "ad tutmuyor",
  likidite_dusuk: "likidite düşük",
  tur_uygun_degil: "tür uygun değil",
  gecmis_yetersiz: "geçmiş yetersiz",
};

export const discoveryRejectSummary = (vm: NewsDiscoveryView | undefined) =>
  Object.entries(vm?.stats?.rejected ?? {})
    .filter(([, n]) => n > 0)
    .map(([k, n]) => `${REJECT_LABEL[k] ?? k} ${n}`)
    .join(" · ");

/** Olayın gösterilecek varlıkları: doğrulanmış keşif adayı ya da takipteki (kayıtlı) varlık. */
export const shownAssets = (ev: NewsDiscoveryEvent) =>
  ev.assets.filter((a) => a.status === "valid" || a.status === "registry");

export const DISCOVERY_STATUS_LABEL: Record<string, string> = {
  OK: "çalışıyor",
  LOCAL_LLM_OFF: "yerel YZ kapalı",
  DAILY_CAP: "günlük sınır doldu",
  DISABLED: "kapalı",
  UNKNOWN: "henüz çalışmadı",
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
