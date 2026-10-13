"use client";

import { useMemo, useRef, useState, type ReactNode } from "react";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { fmtNum, fmtUSD } from "@/lib/format";
import { useIdeas, useOpenIdeaPaperPosition, usePaperTradingState } from "@/lib/queries/hooks";
import {
  fmtIdeaStamp,
  selectBannerIdea,
  selectIdeaBannerFacts,
  selectOpenedPosition,
  selectPaperOpenView,
  type IdeaOpenPhase,
  type PaperButtonView,
} from "@/lib/selectors/ideas";
import type { IdeaPaperOpenResult } from "@/types/generated/api";

// Brain — hologramın altında "Yeni Asset Fikri" özet bannerı (Heart'taki ayrıntılı panelin kompakt görünümü).
// Veri: MEVCUT useIdeas() (Heart paneliyle aynı sorgu — ikinci fetch/polling YOK). Onay butonu MEVCUT paper
// emir yoluna bağlıdır (POST /paper-trading/ideas/{symbol}/open → manual_order.place); RiskGate/limit
// doğrulaması backend'dedir, buton hiçbirini bypass edemez. Gerçek broker emri YOK.

const BUTTON_TONE: Record<PaperButtonView["tone"], string> = {
  ready: "border-accent-cyan/55 bg-accent-cyan/15 text-accent-cyan hover:bg-accent-cyan/25",
  busy: "animate-pulse border-white/20 bg-white/[0.06] text-white/70",
  success: "border-emerald-400/45 bg-emerald-400/12 text-emerald-200",
  blocked: "border-red-400/45 bg-red-400/10 text-red-200",
  muted: "border-white/15 bg-white/[0.03] text-white/45",
};

function Fact({ label, children, title }: { label: string; children: ReactNode; title?: string }) {
  return (
    <div className="min-w-0" title={title}>
      <div className="text-[8px] uppercase tracking-widest text-white/35">{label}</div>
      <div className="truncate font-mono text-[11px] text-white/80">{children}</div>
    </div>
  );
}

function Stat({ label, children, title }: { label: string; children: ReactNode; title?: string }) {
  return (
    <span className="min-w-0 whitespace-nowrap" title={title}>
      <span className="text-[9px] uppercase tracking-widest text-white/35">{label} </span>
      <span className="font-mono text-[11px] text-white/80">{children}</span>
    </span>
  );
}

function TextRow({ label, text }: { label: string; text: string | null }) {
  return (
    <p className="min-w-0 text-[10px] leading-4 text-white/55" title={text ?? undefined}>
      <span className="text-white/35">{label}: </span>
      <span>{text ?? "—"}</span>
    </p>
  );
}

export function HologramAssetIdeaBanner() {
  const ideas = useIdeas();
  const paper = usePaperTradingState();
  const open = useOpenIdeaPaperPosition();
  const idea = useMemo(() => selectBannerIdea(ideas.data), [ideas.data]);

  const [phase, setPhase] = useState<IdeaOpenPhase>("idle");
  const [outcome, setOutcome] = useState<IdeaPaperOpenResult | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  // setState asenkron: iki hızlı tıklama aynı render'da geçebilir → eşzamanlı kilit ref ile (backend de tekil).
  const inFlight = useRef(false);

  // Başka sembole geçildiyse önceki sembolün sonucu bu fikre ait değildir.
  const outcomeSymbol = outcome?.position?.symbol;
  const ownOutcome = outcome && (outcomeSymbol == null || outcomeSymbol === idea?.symbol) ? outcome : null;

  const confirm = async () => {
    if (!idea || inFlight.current) return;
    inFlight.current = true;
    setOutcome(null);
    setRequestError(null);
    try {
      // 1) DOĞRULANIYOR — ön-durum backend'den TAZE alınır (aynı sorgunun kullanıcı tetiklemeli yenilemesi).
      setPhase("verifying");
      const fresh = await ideas.refetch();
      if (fresh.isError) {
        setRequestError(`Fikir verisi yenilenemedi: ${fresh.error instanceof Error ? fresh.error.message : "bilinmeyen hata"}`);
        return;
      }
      const current = selectBannerIdea(fresh.data);
      if (!current || current.symbol !== idea.symbol) {
        setRequestError("Fikir panosu güncellendi, fikir değişti. Yeni fikri inceleyip tekrar onaylayın.");
        return;
      }
      if (!current.paper_open?.can_open) return; // pasif: gerçek neden bannerda (paper_open.reason) görünür
      // 2) PAPER İŞLEM AÇILIYOR — backend atomik olarak yeniden doğrular ve açar.
      setPhase("opening");
      setOutcome(await open.mutateAsync(current.symbol));
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Beklenmeyen hata");
    } finally {
      setPhase("idle");
      inFlight.current = false;
    }
  };

  const facts = idea ? selectIdeaBannerFacts(idea, ideas.data?.generated_at) : null;
  const opened = idea ? selectOpenedPosition(idea, ownOutcome, paper.data?.open_positions) : null;
  const view = idea ? selectPaperOpenView({ idea, phase, outcome: ownOutcome, opened }) : null;

  return (
    <PanelFrame id="hologram_asset_idea" className="hologram-idea-banner !p-2.5 shrink-0 [&_header]:!mb-1.5">
      <PanelHeader
        title="YENİ ASSET FİKRİ"
        actions={
          facts ? (
            <>
              <span className="text-[9px] uppercase tracking-widest text-white/35">
                Güncelleme <span className="font-mono text-[10px] normal-case tracking-normal text-white/55">{facts.updatedAt ?? "—"}</span>
              </span>
              <span className="rounded bg-white/10 px-1.5 py-0.5 text-[9px] uppercase tracking-widest text-white/55">
                {facts.kindLabel}
              </span>
            </>
          ) : undefined
        }
      />

      {ideas.isLoading ? (
        <p className="py-2 text-[11px] text-white/40">Fikir verisi yükleniyor…</p>
      ) : ideas.isError ? (
        // API hatası — veri yokluğundan AYRI gösterilir.
        <div className="flex items-center justify-between gap-2 py-1 text-[11px] text-red-200/80">
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
        <p className="py-2 text-[11px] italic text-white/40">Henüz yeni asset fikri yok.</p>
      ) : (
        <div className="space-y-1 leading-4">
          <div className="flex items-baseline gap-x-2 leading-5">
            <span className="font-mono text-sm font-bold text-white/90">{facts.symbol}</span>
            <span className="min-w-0 flex-1 truncate text-[11px] text-white/55">{facts.name}</span>
            <span className={`text-[11px] font-semibold uppercase ${facts.direction.tone}`}>{facts.direction.text}</span>
          </div>

          <div className="flex flex-wrap gap-x-3">
            <Stat label="Skor">{facts.score}</Stat>
            <Stat label="Güven">{facts.confidencePct != null ? `%${facts.confidencePct}` : "—"}</Stat>
            <Stat label="Zaman dilimi">{facts.timeframe ?? "—"}</Stat>
          </div>
          <p className="truncate text-[10px]" title={facts.techText}>
            <span className="text-[9px] uppercase tracking-widest text-white/35">Teknik teyit </span>
            <span className={`font-mono ${facts.techConfirmed ? "text-emerald-300" : "text-amber-200"}`}>{facts.techText}</span>
          </p>

          <p className="truncate text-[10px] text-white/55" title={facts.impact ?? undefined}>
            <span className="text-white/35">Haber etkisi: </span>
            {facts.impact ?? "—"}
          </p>

          {opened ? (
            <div
              className="rounded border border-emerald-400/30 bg-emerald-400/[0.06] p-1.5"
              data-testid="idea-opened"
            >
              <div className="grid grid-cols-2 gap-x-2 gap-y-1 sm:grid-cols-4">
                <Fact label="Sembol">{opened.symbol}</Fact>
                <Fact label="Yön">{opened.side === "long" ? "LONG" : "SHORT"}</Fact>
                <Fact label="Giriş fiyatı">{fmtNum(opened.entry_price, opened.entry_price >= 100 ? 2 : 4)}</Fact>
                <Fact label="Pozisyon">{fmtUSD(opened.size_usd)}</Fact>
                <Fact label="Açılış">{fmtIdeaStamp(opened.opened_at) ?? "—"}</Fact>
                <Fact label="İşlem kimliği" title={opened.position_id}>{opened.position_id}</Fact>
                <Fact label="Stop-loss">{opened.sl != null ? fmtNum(opened.sl, opened.sl >= 100 ? 2 : 4) : "—"}</Fact>
                <Fact label="Take-profit">{opened.tp != null ? fmtNum(opened.tp, opened.tp >= 100 ? 2 : 4) : "—"}</Fact>
              </div>
            </div>
          ) : (
            // "Neden?" tek satır; tıklayınca takip koşulu + haber–varlık ilişkisi açılır (hologram boyu korunur).
            <details className="group text-[10px]" data-testid="idea-details">
              <summary
                className="flex cursor-pointer list-none items-baseline gap-1 text-white/55 marker:content-none [&::-webkit-details-marker]:hidden"
                title={facts.why ?? undefined}
              >
                <span className="text-[8px] text-accent-cyan/70 transition-transform group-open:rotate-90" aria-hidden>▶</span>
                <span className="min-w-0 flex-1 truncate group-open:whitespace-normal">
                  <span className="text-white/35">Neden?: </span>
                  {facts.why ?? "—"}
                </span>
              </summary>
              <div className="mt-0.5 space-y-0.5 pl-3">
                <TextRow label="Takip koşulu" text={facts.followCondition} />
                <TextRow label="Haber–varlık ilişkisi" text={facts.relation} />
              </div>
            </details>
          )}

          <div className="flex flex-wrap items-center justify-between gap-2">
            <span
              className="rounded border border-amber-400/30 bg-amber-400/[0.07] px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-widest text-amber-200/90"
              title="Gerçek emir gönderilmez; onay yalnızca paper (kâğıt) pozisyon açar."
            >
              GÖLGE TAKİP · EMİR YOK
            </span>
            <button
              type="button"
              onClick={() => void confirm()}
              disabled={view.button.disabled}
              aria-busy={phase !== "idle"}
              className={`rounded border px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-widest transition-colors disabled:cursor-not-allowed ${BUTTON_TONE[view.button.tone]}`}
            >
              {view.button.label}
            </button>
          </div>

          {/* Gerçek engel nedeni backend'den gelir; sessizce yutulmaz. */}
          <div aria-live="polite" className="empty:hidden">
            {view.reason ? (
              <p className="text-[10px] leading-4 text-white/60" data-testid="idea-reason">{view.reason}</p>
            ) : null}
            {requestError ? (
              <p className="text-[10px] leading-4 text-red-200" role="alert">{requestError}</p>
            ) : null}
          </div>
        </div>
      )}
    </PanelFrame>
  );
}
