"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { fmtNum, fmtUSD } from "@/lib/format";
import { useCockpitBrief, useIdeas, useOpenIdeaPaperPosition, usePaperTradingState } from "@/lib/queries/hooks";
import {
  dedupeIdeas,
  fmtIdeaStamp,
  selectIdeaBannerFacts,
  formatIdeaEvidence,
  selectIdeaArticleExcerpt,
  selectOpenedPosition,
  selectPaperOpenView,
  stepIdea,
  type IdeaOpenPhase,
  type PaperButtonView,
} from "@/lib/selectors/ideas";
import type { IdeaPaperOpenResult } from "@/types/generated/api";

// Brain — hologramın altında "Yeni Asset Fikri" özet bannerı (Heart'taki ayrıntılı panelin kompakt görünümü).
// Veri: MEVCUT useIdeas() (Heart paneliyle aynı sorgu — ikinci fetch/polling YOK). Onay butonu MEVCUT paper
// emir yoluna bağlıdır (POST /paper-trading/ideas/{symbol}/open → manual_order.place); RiskGate/limit
// doğrulaması backend'dedir, buton hiçbirini bypass edemez. Gerçek broker emri YOK.
// Panodaki TÜM fikirler ROTATE_MS arayla sırayla gösterilir (yalnız bir görsel zamanlayıcı — veri çekmez).
// Üzerine gelince/odaklanınca/tıklayınca ve onay sürerken döngü durur; böylece okunan ya da onaylanan fikir kaymaz.
// Banner yüksekliği her fikirde SABİT tutulur: yükseklik değişirse hologram kartı her turda yeniden boyutlanır.

const ROTATE_MS = 5000;
const HOLD_MS = 10000; // kullanıcı eyleminden sonra döngü bu kadar bekler (sonuç okunabilsin)

const BUTTON_TONE: Record<PaperButtonView["tone"], string> = {
  ready: "border-accent-cyan/55 bg-accent-cyan/15 text-accent-cyan hover:bg-accent-cyan/25",
  busy: "animate-pulse border-white/20 bg-white/[0.06] text-white/70",
  success: "border-emerald-400/45 bg-emerald-400/12 text-emerald-200",
  blocked: "border-red-400/45 bg-red-400/10 text-red-200",
  muted: "border-white/15 bg-white/[0.03] text-white/45",
};

// Onay sonucu/hatası YAZILDIĞI sembole bağlıdır; döngü başka fikre geçince başka fikirde görünmez.
type Attempt = { symbol: string; outcome?: IdeaPaperOpenResult; error?: string };

function Fact({ label, children, title }: { label: string; children: ReactNode; title?: string }) {
  return (
    <div className="min-w-0" title={title}>
      <div className="text-[9px] uppercase leading-3 tracking-[0.14em] text-white/45">{label}</div>
      <div className="mt-0.5 truncate font-mono text-[12px] font-semibold text-white/88">{children}</div>
    </div>
  );
}

function Stat({
  label,
  children,
  title,
  className = "shrink-0",
}: {
  label: string;
  children: ReactNode;
  title?: string;
  className?: string;
}) {
  return (
    <div className={`min-w-0 rounded-lg border border-white/[0.08] bg-black/20 px-2 py-1.5 ${className}`} title={title}>
      <div className="text-[9px] uppercase tracking-[0.12em] text-white/42">{label}</div>
      <div className="mt-0.5 truncate font-mono text-[12px] font-semibold text-white/88">{children}</div>
    </div>
  );
}

function TextRow({ label, text }: { label: string; text: string | null }) {
  return (
    <p className="min-w-0 text-[11px] leading-4 text-white/68" title={text ?? undefined}>
      <span className="font-semibold text-white/48">{label}: </span>
      <span>{text ?? "—"}</span>
    </p>
  );
}

export function HologramAssetIdeaBanner() {
  const ideas = useIdeas();
  const cockpit = useCockpitBrief();
  const paper = usePaperTradingState();
  const open = useOpenIdeaPaperPosition();
  const list = useMemo(() => dedupeIdeas(ideas.data), [ideas.data]);

  const [activeSymbol, setActiveSymbol] = useState<string | null>(null);
  const idea = list.find((item) => item.symbol === activeSymbol) ?? list[0] ?? null;

  const [phase, setPhase] = useState<IdeaOpenPhase>("idle");
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  // setState asenkron: iki hızlı tıklama aynı render'da geçebilir → eşzamanlı kilit ref ile (backend de tekil).
  const inFlight = useRef(false);
  const pointerInside = useRef(false);
  const keyboardFocus = useRef(false); // yalnız klavye odağı döngüyü durdurur (fareyle tıklanan düğme odak tutar)
  const heldUntil = useRef(0);
  const hold = () => {
    heldUntil.current = Date.now() + HOLD_MS;
  };

  useEffect(() => {
    if (list.length < 2) return;
    const timer = setInterval(() => {
      if (pointerInside.current || keyboardFocus.current || inFlight.current || Date.now() < heldUntil.current) return;
      setActiveSymbol((prev) => stepIdea(list, prev, 1));
      setAttempt(null); // önceki turdaki onay sonucu bayatlar
    }, ROTATE_MS);
    return () => clearInterval(timer);
  }, [list]);

  const go = (delta: number) => {
    hold();
    setAttempt(null);
    setActiveSymbol((prev) => stepIdea(list, prev, delta));
  };

  const own = idea && attempt?.symbol === idea.symbol ? attempt : null;

  const confirm = async () => {
    if (!idea || inFlight.current) return;
    const symbol = idea.symbol;
    inFlight.current = true;
    hold();
    setAttempt(null);
    try {
      // 1) DOĞRULANIYOR — ön-durum backend'den TAZE alınır (aynı sorgunun kullanıcı tetiklemeli yenilemesi).
      setPhase("verifying");
      const fresh = await ideas.refetch();
      if (fresh.isError) {
        setAttempt({
          symbol,
          error: `Fikir verisi yenilenemedi: ${fresh.error instanceof Error ? fresh.error.message : "bilinmeyen hata"}`,
        });
        return;
      }
      const current = dedupeIdeas(fresh.data).find((item) => item.symbol === symbol);
      if (!current) {
        setAttempt({ symbol, error: "Fikir panosu güncellendi, bu fikir artık listede değil." });
        return;
      }
      if (!current.paper_open?.can_open) {
        // Kullanıcı tıklaması ile yapılan taze kontrolde fikir artık açılamıyorsa
        // eski kartı sessizce bırakma; gerçek backend engelini görünür kıl.
        const pre = current.paper_open;
        setAttempt({
          symbol,
          outcome: {
            status: "blocked",
            state: pre?.state ?? "DATA_UNAVAILABLE",
            reason: pre?.reason ?? "Fikir artık paper işlem için uygun değil.",
          },
        });
        return;
      }
      // 2) PAPER İŞLEM AÇILIYOR — backend atomik olarak yeniden doğrular ve açar.
      setPhase("opening");
      setAttempt({ symbol, outcome: await open.mutateAsync(symbol) });
    } catch (error) {
      setAttempt({ symbol, error: error instanceof Error ? error.message : "Beklenmeyen hata" });
    } finally {
      setPhase("idle");
      inFlight.current = false;
      hold();
    }
  };

  const facts = idea ? selectIdeaBannerFacts(idea, ideas.data?.generated_at) : null;
  const evidenceSummary = idea ? formatIdeaEvidence(idea) : null;
  const articleExcerpt = idea ? selectIdeaArticleExcerpt(idea) : null;
  const opened = idea ? selectOpenedPosition(idea, own?.outcome ?? null, paper.data?.open_positions) : null;
  const view = idea ? selectPaperOpenView({ idea, phase, outcome: own?.outcome ?? null, opened }) : null;
  const position = idea ? list.findIndex((item) => item.symbol === idea.symbol) + 1 : 0;
  // Pasif ön-durumları (ör. veri bekleniyor) düğme gibi göstermeyiz. Kullanıcı
  // yalnızca gerçekten onaylayabileceği bir paper işlemi olduğunda aksiyon görür.
  const showPaperAction = Boolean(view && (view.button.tone === "ready" || phase !== "idle"));
  const showReason = Boolean(view?.reason && view.button.tone !== "muted");

  return (
    <PanelFrame id="hologram_asset_idea" className="hologram-idea-banner shrink-0 !border-accent-cyan/25 !bg-[linear-gradient(135deg,rgba(4,28,38,0.92),rgba(5,12,20,0.96))] !p-3 sm:!p-3.5 [&_header]:!mb-2.5 [&_h3]:whitespace-nowrap">
      <div
        onPointerEnter={() => {
          pointerInside.current = true;
        }}
        onPointerLeave={() => {
          pointerInside.current = false;
        }}
        onPointerDown={hold}
        onFocusCapture={(event) => {
          keyboardFocus.current = event.target.matches(":focus-visible");
        }}
        onBlurCapture={() => {
          keyboardFocus.current = false;
        }}
      >
        <PanelHeader
          title="YENİ ASSET FİKRİ"
          actions={
            facts ? (
              <>
                {list.length > 1 ? (
                  <span className="flex items-center gap-0.5 rounded-md border border-white/[0.08] bg-white/[0.03] px-1 font-mono text-[11px] text-white/65" data-testid="idea-counter">
                    <button
                      type="button"
                      onClick={() => go(-1)}
                      disabled={phase !== "idle"}
                      aria-label="Önceki fikir"
                      className="px-1 text-accent-cyan/70 hover:text-accent-cyan disabled:opacity-40"
                    >
                      ‹
                    </button>
                    {position}/{list.length}
                    <button
                      type="button"
                      onClick={() => go(1)}
                      disabled={phase !== "idle"}
                      aria-label="Sonraki fikir"
                      className="px-1 text-accent-cyan/70 hover:text-accent-cyan disabled:opacity-40"
                    >
                      ›
                    </button>
                  </span>
                ) : null}
                <span className="whitespace-nowrap text-[9px] uppercase tracking-[0.12em] text-white/42" title="Son güncelleme">
                  <span className="max-[400px]:hidden">GÜNCEL </span>
                  <span className="font-mono text-[10px] normal-case tracking-normal text-white/65">{facts.updatedAt ?? "—"}</span>
                </span>
              </>
            ) : undefined
          }
        />

        {ideas.isLoading ? (
          <p className="rounded-lg border border-white/[0.08] bg-black/20 px-3 py-3 text-[12px] text-white/55">Fikir verisi yükleniyor…</p>
        ) : ideas.isError ? (
          // API hatası — veri yokluğundan AYRI gösterilir.
          <div className="flex items-center justify-between gap-2 rounded-lg border border-red-400/20 bg-red-400/[0.06] px-3 py-2 text-[12px] text-red-100/85">
            <span>Fikir verisi alınamadı.</span>
            <button
              type="button"
              onClick={() => void ideas.refetch()}
              className="rounded border border-white/15 bg-white/[0.04] px-2 py-0.5 text-[9px] uppercase tracking-widest text-slate-300 hover:bg-white/[0.08]"
            >
              Yenile
            </button>
          </div>
        ) : !idea || !facts || !view ? (
          <p className="rounded-lg border border-white/[0.08] bg-black/20 px-3 py-3 text-[12px] italic text-white/50">Henüz yeni asset fikri yok.</p>
        ) : (
          <div className="space-y-2.5 leading-4">
            <div className="rounded-xl border border-accent-cyan/20 bg-accent-cyan/[0.06] px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-lg font-black tracking-wide text-white">{facts.symbol}</span>
              <span className="min-w-0 flex-1 basis-[9rem] truncate text-[12px] text-white/68">{facts.name}</span>
              <span className="rounded-md border border-white/15 bg-white/[0.06] px-2 py-1 text-[9px] font-semibold uppercase tracking-[0.12em] text-white/65">
                {facts.kindLabel}
              </span>
              <span className={`rounded-md border border-current/25 bg-current/10 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.12em] ${facts.direction.tone}`}>
                {facts.direction.text}
              </span>
              </div>
            </div>

            <div className="space-y-2">
              {opened ? (
                <div
                  className="grid grid-cols-2 gap-2 rounded-xl border border-emerald-400/30 bg-emerald-400/[0.07] px-3 py-2 sm:grid-cols-4"
                  data-testid="idea-opened"
                >
                  <Fact label="Sembol">{opened.symbol}</Fact>
                  <Fact label="Yön">{opened.side === "long" ? "LONG" : "SHORT"}</Fact>
                  <Fact label="Giriş fiyatı">{fmtNum(opened.entry_price, opened.entry_price >= 100 ? 2 : 4)}</Fact>
                  <Fact label="Pozisyon">{fmtUSD(opened.size_usd)}</Fact>
                  <Fact label="Açılış">{fmtIdeaStamp(opened.opened_at) ?? "—"}</Fact>
                  <Fact label="İşlem kimliği" title={opened.position_id}>{opened.position_id}</Fact>
                  <Fact label="Stop-loss">{opened.sl != null ? fmtNum(opened.sl, opened.sl >= 100 ? 2 : 4) : "—"}</Fact>
                  <Fact label="Take-profit">{opened.tp != null ? fmtNum(opened.tp, opened.tp >= 100 ? 2 : 4) : "—"}</Fact>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <Stat label="Fikir skoru" title="Genel fikir kalitesi; mevcut formülün üst sınırı 90 puandır.">
                      {facts.score}/{facts.scoreMax}
                    </Stat>
                    <Stat
                      label="Teknik güven"
                      title="Kalibre edilmiş teknik sinyal güveni; haber, gölge karne ve RiskGate sonucu değildir."
                    >
                      {facts.confidencePct != null ? `%${facts.confidencePct}` : "—"}
                    </Stat>
                    <Stat label="Zaman dilimi">{facts.timeframe ?? "—"}</Stat>
                    <Stat label="Teknik teyit" title={facts.techText} className="min-w-0">
                      <span className={facts.techConfirmed ? "text-emerald-300" : "text-amber-200"}>{facts.techText}</span>
                    </Stat>
                  </div>

                  <div className="rounded-xl border border-accent-cyan/15 bg-accent-cyan/[0.05] px-3 py-2">
                    <div className="text-[9px] font-semibold uppercase tracking-[0.14em] text-accent-cyan/70">Haber etkisi</div>
                    <p className="mt-1 max-h-10 overflow-hidden text-[11px] leading-4 text-white/72" title={facts.impact ?? undefined}>
                      {facts.impact ?? "—"}
                    </p>
                  </div>

                  {(evidenceSummary || articleExcerpt || cockpit.data?.news_consensus) ? (
                    <div className="rounded-xl border border-white/[0.08] bg-black/20 px-3 py-2 text-[10px] leading-4 text-white/55">
                      {evidenceSummary ? (
                        <div>
                          <span className="font-semibold text-cyan-100/45">Haber kanıtı: </span>
                          {evidenceSummary}
                        </div>
                      ) : null}
                      {articleExcerpt ? (
                        <div className="mt-1 line-clamp-2" title={articleExcerpt}>
                          <span className="font-semibold text-white/35">Kaynak özeti: </span>
                          {articleExcerpt}
                        </div>
                      ) : null}
                      {cockpit.data?.news_consensus?.article_coverage?.status ? (
                        <div className="mt-1 text-white/35">
                          Ortak haber kapsamı: {String(cockpit.data.news_consensus.article_coverage.status).toLowerCase()}
                          {cockpit.data.news_consensus.article_coverage.coverage_pct != null
                            ? ` · ${cockpit.data.news_consensus.article_coverage.coverage_pct.toFixed(1)}% makale`
                            : ""}
                        </div>
                      ) : null}
                    </div>
                  ) : null}

                  <details key={idea.symbol} className="group rounded-xl border border-white/[0.08] bg-black/20 px-3 py-2 text-[11px]" data-testid="idea-details">
                    <summary
                      className="flex cursor-pointer list-none items-start gap-2 text-white/72 marker:content-none [&::-webkit-details-marker]:hidden"
                      title={facts.why ?? undefined}
                    >
                      <span className="mt-0.5 text-[9px] text-accent-cyan/80 transition-transform group-open:rotate-90" aria-hidden>▶</span>
                      <span className="min-w-0 flex-1 max-h-8 overflow-hidden group-open:max-h-none">
                        <span className="font-semibold text-white/55">Neden? </span>
                        {facts.why ?? "—"}
                      </span>
                    </summary>
                    <div className="mt-2 space-y-1 border-t border-white/[0.08] pt-2">
                      <TextRow
                        label="Skor kırılımı"
                        text={`Teknik ${facts.components.technical}/40 · Gölge ${facts.components.scorecard}/25 · Haber ${facts.components.news > 0 ? "+" : ""}${facts.components.news}/25 · Risk ${facts.components.risk}`}
                      />
                      <TextRow label="Takip koşulu" text={facts.followCondition} />
                      <TextRow label="Haber–varlık ilişkisi" text={facts.relation} />
                    </div>
                  </details>
                </>
              )}
            </div>

            {showPaperAction ? (
              <div className="flex justify-end rounded-xl border border-accent-cyan/20 bg-accent-cyan/[0.05] p-2.5">
                <button
                  type="button"
                  onClick={() => void confirm()}
                  disabled={view.button.disabled}
                  aria-busy={phase !== "idle"}
                  className={`min-h-9 rounded-lg border px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.11em] transition-colors disabled:cursor-not-allowed sm:min-w-[12rem] ${BUTTON_TONE[view.button.tone]}`}
                >
                  {view.button.label}
                </button>
              </div>
            ) : null}

            {/* Gerçek engel nedeni backend'den gelir; sessizce yutulmaz. Sabit 2 satırlık alan (taşarsa kayar). */}
            <div aria-live="polite" className="max-h-10 overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {showReason ? (
                <p className="text-[10px] leading-4 text-white/60" title={view.reason ?? undefined} data-testid="idea-reason">{view.reason}</p>
              ) : null}
              {own?.error ? (
                <p className="text-[10px] leading-4 text-red-200" role="alert">{own.error}</p>
              ) : null}
            </div>
          </div>
        )}
      </div>
    </PanelFrame>
  );
}
