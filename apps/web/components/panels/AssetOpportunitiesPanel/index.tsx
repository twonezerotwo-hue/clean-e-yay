"use client";

import { useMemo } from "react";

import { EmptyState } from "@/components/shell/EmptyState";
import { LoadingState } from "@/components/shell/LoadingState";
import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { useIdeas } from "@/lib/queries/hooks";
import {
  dedupeIdeas,
  fmtIdeaStamp,
  formatIdeaNewsImpact,
  formatIdeaReason,
  IDEA_SCORE_MAX,
  IDEA_KIND_LABEL,
  ideaDirection,
} from "@/lib/selectors/ideas";
import type { Idea, IdeaStatus } from "@/types/generated/api";

// Heart — "Yeni Asset / Emtia Fırsatları" (SALT-GÖZLEM).
// Kaynak: MEVCUT /api/v1/ideas (IdeaBoardView). Yeni endpoint / polling / SSE YOK;
// aynı bildirim akışını besleyen keşif adaylarını gösterir. Emir açmaz;
// RiskGate / consensus / paper trading / karar motoruna dokunmaz.

// Durum etiketi backend'in `status_label`'ından gelir (uydurma yok); yalnız RENK
// status enum'undan seçilir — mevcut tema token'larıyla.
const STATUS_TONE: Record<IdeaStatus, string> = {
  WATCHING: "border-amber-400/40 bg-amber-400/10 text-amber-200",
  PROMOTION_READY: "border-emerald-400/40 bg-emerald-400/10 text-emerald-200",
  AWAITING_APPROVAL: "border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan",
};

function AssetOpportunityCard({ idea, onOpen }: { idea: Idea; onOpen?: (symbol: string) => void }) {
  const dir = ideaDirection(idea.news?.direction);
  const confidence = idea.technical?.confidence;
  const timeframe = idea.technical?.entry_timeframe;
  const evidence = idea.news?.n_headlines ?? idea.scorecard?.signals;
  const updated = fmtIdeaStamp(idea.technical?.checked_at);
  const newsImpact = formatIdeaNewsImpact(idea);
  const reason = formatIdeaReason(idea);
  const tone = STATUS_TONE[idea.status] ?? "border-white/15 bg-white/[0.04] text-white/70";
  const statusLabel = idea.status_label || idea.status;
  const paperReady = idea.paper_open?.can_open === true;

  return (
    <article className="rounded border border-white/10 bg-white/[0.02] px-2.5 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-mono text-xs font-bold text-white/85">{idea.symbol}</span>
          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[9px] uppercase tracking-widest text-white/55">
            {IDEA_KIND_LABEL[idea.kind] ?? idea.kind}
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
        <span>fikir {Math.round(idea.score)}/{IDEA_SCORE_MAX}</span>
        {confidence != null ? <span>teknik güven {Math.round(confidence * 100)}%</span> : null}
        {timeframe ? <span>{timeframe}</span> : null}
        {evidence != null ? <span>kanıt {evidence}</span> : null}
        {idea.news?.strength != null ? <span>haber {Math.round(idea.news.strength)}</span> : null}
      </div>

      {newsImpact ? (
        <p className="mt-1.5 text-[10px] leading-4 text-white/50">
          <span className="text-white/35">Haber etkisi: </span>
          {newsImpact}
        </p>
      ) : null}
      <p className="mt-0.5 text-[10px] leading-4 text-white/45">
        <span className="text-white/30">Neden izleniyor: </span>
        {reason ?? "Güncel kanıt özeti yok."}
      </p>
      {idea.ai?.verdict_label ? (
        <p className="mt-0.5 text-[10px] leading-4 text-white/45">
          <span className="text-white/30">YZ: </span>
          {idea.ai.verdict_label}
        </p>
      ) : null}

      <p
        className={`mt-1 text-[10px] leading-4 ${paperReady ? "text-emerald-200/75" : "text-amber-200/65"}`}
        title={idea.paper_open?.reason ?? undefined}
      >
        {paperReady ? "Paper onayına hazır" : `Paper bekliyor: ${idea.paper_open?.reason ?? "güncel doğrulama gerekli"}`}
      </p>

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

  // Sembol bazında tekilleştir — aynı aday için duplicate kart oluşmaz (Brain bannerıyla ortak seçici).
  const ideas = useMemo(() => dedupeIdeas(data), [data]);

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

      {/* Salt-gözlem paneli: Brain'deki owner onayı ayrı paper akışıdır. */}
      <div className="mb-2 rounded border border-amber-400/20 bg-amber-400/[0.06] px-2 py-1 text-[10px] leading-4 text-amber-200/80">
        ⚠ Bu panel gözlem ve hazırlık içindir. Brain onayı yalnızca paper pozisyonu açabilir; gerçek broker emri gönderilmez.
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
