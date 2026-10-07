"use client";

import { useMemo } from "react";

import { EmptyState } from "@/components/shell/EmptyState";
import { LoadingState } from "@/components/shell/LoadingState";
import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { useIdeas } from "@/lib/queries/hooks";
import type { Idea, IdeaBoardView, IdeaStatus } from "@/types/generated/api";

// Heart — "Yeni Asset / Emtia Fırsatları" (SALT-GÖZLEM).
// Kaynak: MEVCUT /api/v1/ideas (IdeaBoardView). Yeni endpoint / polling / SSE YOK;
// aynı bildirim akışını besleyen keşif adaylarını gösterir. Emir açmaz;
// RiskGate / consensus / paper trading / karar motoruna dokunmaz.

const KIND_LABEL: Record<string, string> = {
  crypto: "Kripto",
  commodity: "Emtia",
  sector_etf: "Sektör ETF",
  news: "Haber",
};

// Durum etiketi backend'in `status_label`'ından gelir (uydurma yok); yalnız RENK
// status enum'undan seçilir — mevcut tema token'larıyla.
const STATUS_TONE: Record<IdeaStatus, string> = {
  WATCHING: "border-amber-400/40 bg-amber-400/10 text-amber-200",
  PROMOTION_READY: "border-emerald-400/40 bg-emerald-400/10 text-emerald-200",
  AWAITING_APPROVAL: "border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan",
};

function dirLabel(direction: string | null | undefined): { text: string; tone: string } {
  if (direction === "up") return { text: "bullish", tone: "text-signal-up/80" };
  if (direction === "down") return { text: "bearish", tone: "text-signal-down/80" };
  return { text: "nötr", tone: "text-white/50" };
}

function fmtStamp(value: string | null | undefined): string | null {
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

function AssetOpportunityCard({ idea, onOpen }: { idea: Idea; onOpen?: (symbol: string) => void }) {
  const dir = dirLabel(idea.news?.direction);
  const chain = idea.news_chain?.[0];
  const confidence = idea.technical?.confidence;
  const timeframe = idea.technical?.entry_timeframe;
  const evidence = idea.news?.n_headlines ?? idea.scorecard?.signals;
  const updated = fmtStamp(idea.technical?.checked_at);
  const tone = STATUS_TONE[idea.status] ?? "border-white/15 bg-white/[0.04] text-white/70";
  const statusLabel = idea.status_label || idea.status;

  return (
    <article className="rounded border border-white/10 bg-white/[0.02] px-2.5 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-mono text-xs font-bold text-white/85">{idea.symbol}</span>
          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[9px] uppercase tracking-widest text-white/55">
            {KIND_LABEL[idea.kind] ?? idea.kind}
          </span>
          {idea.review ? (
            <span className="rounded border border-accent-cyan/50 bg-accent-cyan/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-widest text-accent-cyan">
              yeni
            </span>
          ) : null}
        </div>
        <span className={`rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-widest ${tone}`}>
          {statusLabel}
        </span>
      </div>

      <p className="mt-1 truncate text-[11px] text-white/60">{idea.name || idea.symbol}</p>

      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[10px] text-white/55">
        <span className={dir.tone}>{dir.text}</span>
        <span>skor {Math.round(idea.score)}</span>
        {confidence != null ? <span>güven {Math.round(confidence * 100)}%</span> : null}
        {timeframe ? <span>{timeframe}</span> : null}
        {evidence != null ? <span>kanıt {evidence}</span> : null}
        {idea.news?.strength != null ? <span>haber {Math.round(idea.news.strength)}</span> : null}
      </div>

      {chain?.title ? (
        <p className="mt-1.5 text-[10px] leading-4 text-white/50">
          <span className="text-white/35">Neden: </span>
          {chain.title}
          {chain.consequence ? ` → ${chain.consequence}` : ""}
        </p>
      ) : null}
      {idea.ai?.verdict_label ? (
        <p className="mt-0.5 text-[10px] leading-4 text-white/45">
          <span className="text-white/30">YZ: </span>
          {idea.ai.verdict_label}
        </p>
      ) : null}

      <div className="mt-1.5 flex items-center justify-between gap-2">
        <span className="truncate font-mono text-[9px] text-white/30">
          {updated ? `güncelleme ${updated}` : ""}
        </span>
        {onOpen ? (
          <button
            type="button"
            onClick={() => onOpen(idea.symbol)}
            className="rounded border border-white/15 bg-white/[0.04] px-2 py-0.5 text-[9px] uppercase tracking-widest text-slate-300 hover:bg-white/[0.08]"
          >
            Detay
          </button>
        ) : null}
      </div>
    </article>
  );
}

export function AssetOpportunitiesPanel({
  onOpenSymbol,
}: {
  onOpenSymbol?: (symbol: string) => void;
}) {
  const { data, isLoading, isError } = useIdeas();
  const board: IdeaBoardView | undefined = data;

  // Sembol bazında tekilleştir — aynı aday için duplicate kart oluşmaz.
  const ideas = useMemo(() => {
    const seen = new Map<string, Idea>();
    for (const idea of board?.ideas ?? []) {
      if (idea?.symbol && !seen.has(idea.symbol)) seen.set(idea.symbol, idea);
    }
    return Array.from(seen.values());
  }, [board?.ideas]);

  return (
    <PanelFrame id="asset_opportunities" className="h-full">
      <PanelHeader
        title="YENİ ASSET / EMTİA FIRSATLARI"
        subtitle="Sistem tarafından haber, piyasa ve teknik analiz sonucunda keşfedilen yeni adaylar."
        actions={
          ideas.length ? (
            <span className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-[10px] text-white/60">
              {ideas.length} aday
            </span>
          ) : undefined
        }
      />

      {/* Yalnızca gözlem — her zaman görünür dürüstlük satırı. */}
      <div className="mb-2 rounded border border-amber-400/20 bg-amber-400/[0.06] px-2 py-1 text-[10px] leading-4 text-amber-200/80">
        ⚠ Bu alan yalnızca gözlem ve hazırlık bilgisidir. Emir oluşturmaz.
      </div>

      {isLoading ? (
        <LoadingState label="Keşif verileri yükleniyor…" />
      ) : isError ? (
        // API hatası — veri yokluğundan AYRI gösterilir.
        <EmptyState message="Keşif verileri alınamadı." />
      ) : ideas.length === 0 ? (
        <EmptyState message="Henüz yeni asset keşfedilmedi." />
      ) : (
        <div className="grid grid-cols-1 gap-2">
          {ideas.map((idea) => (
            <AssetOpportunityCard key={idea.symbol} idea={idea} onOpen={onOpenSymbol} />
          ))}
        </div>
      )}
    </PanelFrame>
  );
}
