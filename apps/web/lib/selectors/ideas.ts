import type {
  Idea,
  IdeaBoardView,
  IdeaPaperOpenResult,
  IdeaPaperOpenState,
  IdeaPaperPosition,
  Position,
} from "@/types/generated/api";

// Fikir Panosu (mevcut /api/v1/ideas) — Heart "Yeni Asset / Emtia Fırsatları" paneli ve
// Brain "Yeni Asset Fikri" bannerı AYNI fikri iki görünümde gösterir. Seçim/etiket mantığı
// burada tek yerde durur (frontend hesap yapmaz; backend ViewModel'ini biçimler).

export const IDEA_KIND_LABEL: Record<string, string> = {
  crypto: "Kripto",
  commodity: "Emtia",
  sector_etf: "Sektör ETF",
  news: "Haber",
};

/** Sembol bazında tekilleştir — aynı aday için duplicate kart oluşmaz. Sıra backend'in skor sırası. */
export function dedupeIdeas(board: IdeaBoardView | undefined): Idea[] {
  const seen = new Map<string, Idea>();
  for (const idea of board?.ideas ?? []) {
    if (idea?.symbol && !seen.has(idea.symbol)) seen.set(idea.symbol, idea);
  }
  return Array.from(seen.values());
}

/** Brain bannerı fikirleri sırayla gösterir: `symbol`'den `delta` adım sonraki fikrin sembolü (başa/sona sarar). */
export function stepIdea(ideas: Idea[], symbol: string | null | undefined, delta: number): string | null {
  if (ideas.length === 0) return null;
  const at = ideas.findIndex((idea) => idea.symbol === (symbol ?? ideas[0].symbol));
  // Gösterilen sembol panodan kalktıysa başa dön.
  if (at < 0) return ideas[0].symbol;
  return ideas[(((at + delta) % ideas.length) + ideas.length) % ideas.length].symbol;
}

export function ideaDirection(direction: string | null | undefined): { text: string; tone: string } {
  if (direction === "up") return { text: "bullish", tone: "text-signal-up/80" };
  if (direction === "down") return { text: "bearish", tone: "text-signal-down/80" };
  return { text: "nötr", tone: "text-white/50" };
}

export function fmtIdeaStamp(value: string | null | undefined): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value.slice(0, 16).replace("T", " ");
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

export type IdeaBannerFacts = {
  symbol: string;
  name: string;
  kindLabel: string;
  direction: { text: string; tone: string };
  score: number;
  confidencePct: number | null;
  timeframe: string | null;
  techConfirmed: boolean;
  techText: string;
  impact: string | null;
  why: string | null;
  followCondition: string | null;
  relation: string | null;
  updatedAt: string | null;
};

/** Banner alanları — hepsi fikrin kendi verisinden; olmayan alan null (uydurma metin yok). */
export function selectIdeaBannerFacts(idea: Idea, boardAt?: string | null): IdeaBannerFacts {
  const tech = idea.technical;
  const chain = idea.news_chain?.[0];
  const evidence = idea.news?.evidence?.[0];
  const confirmed = tech.verdict === "WOULD_OPEN_LONG";
  const tfs = tech.bullish_tfs?.length ? ` · ${tech.bullish_tfs.join("/")}` : "";
  const firstConfirmation = tech.ta?.confirmations?.[0];
  const newsDir = idea.news?.direction;
  return {
    symbol: idea.symbol,
    name: idea.name || idea.symbol,
    kindLabel: IDEA_KIND_LABEL[idea.kind] ?? idea.kind,
    // Haber yönü yoksa teknik teyitli fikir yukarıdır (keşif yalnız LONG üretir).
    direction: ideaDirection(newsDir ?? (confirmed ? "up" : null)),
    score: Math.round(idea.score),
    confidencePct: tech.confidence != null ? Math.round(tech.confidence * 100) : null,
    timeframe: tech.entry_timeframe ?? null,
    techConfirmed: confirmed,
    techText: confirmed
      ? `teyitli${tfs}${firstConfirmation ? ` · ${firstConfirmation}` : ""}`
      : `teyit yok (${tech.verdict || "veri yok"})`,
    impact: chain?.consequence || chain?.title || evidence?.title || null,
    why: idea.ai?.thesis || tech.reasons?.[0] || null,
    followCondition: idea.ai?.change_mind || null,
    relation: chain?.mechanism
      || (chain?.title && chain.consequence
        ? `${chain.title} → ${chain.consequence}${chain.direction ? ` → ${chain.direction}` : ""}`
        : null)
      || (idea.news ? `${idea.news.n_headlines ?? 0} haber başlığı, güç ${Math.round(idea.news.strength)}` : null),
    updatedAt: fmtIdeaStamp(tech.checked_at ?? boardAt),
  };
}

// ── Onay butonu ──────────────────────────────────────────────────────────────────────────────

/** İstemci tarafı aşama: DOĞRULANIYOR (ön-durum backend'den tazelenir) → PAPER İŞLEM AÇILIYOR (POST). */
export type IdeaOpenPhase = "idle" | "verifying" | "opening";

export type PaperButtonView = {
  label: string;
  tone: "ready" | "busy" | "success" | "blocked" | "muted";
  disabled: boolean;
};

const STATE_LABEL: Record<IdeaPaperOpenState | "OPENED", PaperButtonView> = {
  READY: { label: "ONAYLA ve KAĞIT İŞLEMİ AÇ", tone: "ready", disabled: false },
  OPENED: { label: "PAPER POZİSYON AÇILDI", tone: "success", disabled: true },
  NO_IDEA: { label: "FİKİR BULUNAMADI", tone: "muted", disabled: true },
  NO_SIGNAL: { label: "SİNYAL GEÇERSİZ", tone: "muted", disabled: true },
  SIGNAL_EXPIRED: { label: "SİNYAL SÜRESİ DOLDU", tone: "muted", disabled: true },
  ALREADY_OPEN: { label: "POZİSYON ZATEN AÇIK", tone: "muted", disabled: true },
  RISK_BLOCKED: { label: "RİSK NEDENİYLE ENGELLENDİ", tone: "blocked", disabled: true },
  DATA_UNAVAILABLE: { label: "GÜNCEL VERİ BEKLENİYOR", tone: "muted", disabled: true },
};

/** Buton + gerçek neden. Öncelik: aşama → onay sonucu → backend ön-durumu (`paper_open`). */
export function selectPaperOpenView(args: {
  idea: Idea;
  phase: IdeaOpenPhase;
  outcome: IdeaPaperOpenResult | null;
  opened: IdeaPaperPosition | null;
}): { button: PaperButtonView; reason: string | null } {
  const { idea, phase, outcome, opened } = args;
  if (phase === "verifying") {
    return { button: { label: "DOĞRULANIYOR...", tone: "busy", disabled: true }, reason: null };
  }
  if (phase === "opening") {
    return { button: { label: "PAPER İŞLEM AÇILIYOR...", tone: "busy", disabled: true }, reason: null };
  }
  if (opened) {
    return { button: STATE_LABEL.OPENED, reason: null };
  }
  if (outcome?.status === "blocked") {
    return { button: STATE_LABEL[outcome.state as IdeaPaperOpenState], reason: outcome.reason };
  }
  const pre = idea.paper_open;
  if (!pre) {
    // Backend ön-durum üretmedi (eski sürüm/hata): tahmin etme, pasif bırak.
    return {
      button: STATE_LABEL.DATA_UNAVAILABLE,
      reason: "Backend bu fikir için işlem ön-durumu döndürmedi.",
    };
  }
  return { button: STATE_LABEL[pre.state], reason: pre.state === "READY" ? null : pre.reason };
}

/** Başarı kartı kaynağı: bu oturumdaki onay sonucu; yoksa fikir için açık olan, fikirden açılmış pozisyon. */
export function selectOpenedPosition(
  idea: Idea,
  outcome: IdeaPaperOpenResult | null,
  positions: Position[] | undefined,
): IdeaPaperPosition | null {
  if (outcome?.status === "opened" && outcome.position) return outcome.position;
  const pre = idea.paper_open;
  if (pre?.state !== "ALREADY_OPEN" || !pre.position_id) return null;
  const pos = (positions ?? []).find((p) => p.id === pre.position_id);
  // "owner_idea" = bu butonla açılmış; başka kökenli açık pozisyon başarı kartı DEĞİL, "zaten açık".
  if (!pos || pos.open_reason !== "owner_idea") return null;
  return {
    position_id: pos.id,
    symbol: pos.symbol,
    side: pos.side,
    entry_price: pos.entry_price,
    size_usd: pos.size_usd,
    opened_at: pos.opened_at,
    timeframe: pos.timeframe ?? null,
    sl: pos.sl ?? null,
    tp: pos.tp ?? null,
  };
}
