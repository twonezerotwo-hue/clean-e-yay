"use client";

import { useState } from "react";

import { EmptyState } from "@/components/shell/EmptyState";
import { LoadingState } from "@/components/shell/LoadingState";
import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { NewsPreparedSetupsSection } from "@/components/panels/NewsPreparedSetupsPanel";
import { useIdeas } from "@/lib/queries/hooks";
import {
  IDEA_VERDICT_TONE,
  aiSourceLabel,
  biasLabel,
  ideaKindLabel,
  newsArrow,
  selectForecastHitRate,
  selectIdeas,
} from "@/lib/selectors/ideas";
import type { Idea } from "@/types/generated/api";

import { NewsDiscoverySection, WorldBriefLine } from "./NewsDiscovery";

function fmt(value?: number | null, digits = 2) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
}

/** Fikir Panosu — haber akışı → sonuç → keşif → teknik analiz → yapay zekâ değerlendirmesi (salt-gözlem).
 *  Dünya Özeti ve Haber Kaynaklı Hazır Pozisyonlar da burada (owner kararı 2026-10-05, ikinci tur). */
export function IdeasPanel() {
  const { data, isLoading } = useIdeas();
  const ideas = selectIdeas(data);
  const hit = selectForecastHitRate(data);
  const [setupsOpen, setSetupsOpen] = useState(false);

  return (
    <PanelFrame id="ideas" className="border-accent-cyan/20">
      <PanelHeader
        title="Fikirler"
        subtitle="haber akışı → sonuç → keşif · teknik analiz · yapay zekâ değerlendirmesi"
      />
      <WorldBriefLine />
      <NewsDiscoverySection vm={data?.discovery} />
      {isLoading ? (
        <LoadingState />
      ) : !ideas.length ? (
        <EmptyState message="Henüz fikir yok — keşif taraması ve haber öngörüsü her öğrenme turunda güncellenir." />
      ) : (
        <div className="space-y-2">
          {ideas.map((idea) => (
            <IdeaCard key={idea.symbol} idea={idea} />
          ))}
        </div>
      )}
      <div className="mt-3">
        <button
          type="button"
          onClick={() => setSetupsOpen((v) => !v)}
          className="text-[10px] uppercase tracking-widest text-accent-cyan/70 hover:text-accent-cyan"
        >
          {setupsOpen ? "▾" : "▸"} Haber kaynaklı hazır pozisyonlar
        </button>
        {setupsOpen ? (
          <div className="mt-2">
            <NewsPreparedSetupsSection />
          </div>
        ) : null}
      </div>
      <div className="mt-3 border-t border-white/8 pt-2 text-[10px] leading-4 text-white/38">
        {data?.honesty}
        {data?.news ? (
          <span>
            {" "}Haber defteri: {data.news.headlines} başlık
            {hit ? ` · öngörü karnesi (1 gün): %${Math.round(hit.hitRate * 100)} isabet, ${hit.n} öngörü` : " · öngörü karnesi henüz birikiyor"}.
          </span>
        ) : null}
      </div>
    </PanelFrame>
  );
}

function IdeaCard({ idea }: { idea: Idea }) {
  const [open, setOpen] = useState(false);
  const ai = idea.ai;
  const t = idea.technical;
  const ta = t.ta ?? {};
  const news = idea.news;
  const card = idea.scorecard;

  return (
    <div className="rounded-lg border border-white/10 bg-[#03101b]/90 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-display text-sm text-white/90">{idea.symbol}</span>
        <span className="text-[11px] text-white/50">{idea.name}</span>
        <span className="rounded border border-white/10 px-1.5 py-0.5 text-[9px] uppercase tracking-widest text-white/45">
          {ideaKindLabel(idea)}
        </span>
        {idea.status === "AWAITING_APPROVAL" ? (
          <a
            href="/#layer-3"
            className="rounded border border-accent-cyan/40 bg-accent-cyan/10 px-1.5 py-0.5 text-[9px] uppercase tracking-widest text-accent-cyan hover:underline"
          >
            {idea.status_label} → onay ekranı
          </a>
        ) : (
          <span className="text-[9px] uppercase tracking-widest text-white/35">{idea.status_label}</span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <div className="h-1.5 w-20 overflow-hidden rounded-full bg-white/10" title="fikir skoru">
            <div className="h-full bg-accent-cyan/70" style={{ width: `${Math.max(2, idea.score)}%` }} />
          </div>
          <span className="tabular-nums text-xs text-white/75">{idea.score}</span>
        </div>
      </div>

      {ai ? (
        <div className="mt-2 flex flex-wrap items-start gap-2 text-xs">
          <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-widest ${IDEA_VERDICT_TONE[ai.verdict]}`}>
            {ai.verdict_label}
          </span>
          <span className="min-w-0 flex-1 text-white/75">{ai.thesis}</span>
          <span className="text-[9px] text-white/35">{aiSourceLabel(ai.source)}</span>
        </div>
      ) : null}

      {idea.news_chain?.length ? (
        <div className="mt-2 space-y-0.5 rounded border border-white/8 bg-black/20 px-2 py-1.5 text-[11px] leading-5">
          <div className="text-[9px] uppercase tracking-widest text-white/35">Haber zinciri</div>
          {idea.news_chain.slice(0, 2).map((link) => (
            <div key={link.title} className="text-white/65">
              <span className="text-white/80">{link.title}</span>
              {link.consequence ? <span className="text-white/50"> → {link.consequence}</span> : null}
              <span className="text-white/50"> → {newsArrow(link.direction ?? undefined)} {idea.symbol}</span>
            </div>
          ))}
        </div>
      ) : null}

      <div className="mt-2 grid gap-2 text-[11px] text-white/60 sm:grid-cols-3">
        <div>
          <div className="text-[9px] uppercase tracking-widest text-white/35">Haber öngörüsü</div>
          {news ? (
            <>
              <div className="text-white/80">
                {newsArrow(news.direction)} güç {news.strength} · {news.n_headlines ?? 0} başlık
              </div>
              {(news.evidence ?? []).slice(0, 2).map((e, i) => (
                <div key={i} className="truncate text-white/45" title={e.title}>
                  › {e.title}
                </div>
              ))}
            </>
          ) : (
            <div className="text-white/40">haber kanıtı yok</div>
          )}
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-widest text-white/35">Teknik</div>
          <div className="text-white/80">
            {t.verdict === "WOULD_OPEN_LONG" ? `sinyal · ${t.entry_timeframe ?? "?"}` : "sinyal yok"}
            {biasLabel(ta.bias) ? ` · ${biasLabel(ta.bias)}` : ""}
          </div>
          {t.verdict === "WOULD_OPEN_LONG" ? (
            <div className="tabular-nums">
              giriş {fmt(t.entry, 4)} · stop {fmt(t.sl, 4)} · hedef {fmt(t.tp, 4)} · R/Ö {fmt(t.rr, 1)}
            </div>
          ) : null}
          {ta.support != null || ta.resistance != null ? (
            <div className="tabular-nums">destek {fmt(ta.support, 4)} · direnç {fmt(ta.resistance, 4)}</div>
          ) : null}
          {ta.patterns?.length ? <div className="truncate">formasyon: {ta.patterns.join(", ")}</div> : null}
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-widest text-white/35">Gölge karne</div>
          {card.decisive ? (
            <div className="tabular-nums text-white/80">
              {card.missed_win}/{card.decisive} isabet ({fmt((card.win_rate ?? 0) * 100, 0)}%) · alt sınır {fmt(card.wilson_low)}
              {card.avg_r != null ? ` · ort ${fmt(card.avg_r)}R` : ""}
            </div>
          ) : (
            <div className="text-white/40">henüz sonuç yok</div>
          )}
          {idea.market?.chg_30d_pct != null ? (
            <div className="tabular-nums">30g {fmt(idea.market.chg_30d_pct, 0)}% · 7g {fmt(idea.market.chg_7d_pct, 0)}%</div>
          ) : null}
        </div>
      </div>

      {ai ? (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="mt-2 text-[10px] uppercase tracking-widest text-accent-cyan/70 hover:text-accent-cyan"
        >
          {open ? "detayı gizle" : "lehte · aleyhte · riskler"}
        </button>
      ) : null}
      {open && ai ? (
        <div className="mt-1 grid gap-2 text-[11px] sm:grid-cols-3">
          <IdeaList title="Lehte" items={ai.pros} tone="text-emerald-200/80" />
          <IdeaList title="Aleyhte" items={ai.cons} tone="text-red-200/80" />
          <IdeaList title="Riskler" items={[...ai.risks, ...idea.risk_notes.filter((n) => !ai.risks.includes(n))]} tone="text-amber-200/80" />
          {ai.change_mind ? (
            <div className="text-white/50 sm:col-span-3">Ne değiştirir: {ai.change_mind}</div>
          ) : null}
          <div className="text-[10px] text-white/35 sm:col-span-3">
            Skor bileşenleri: teknik {idea.components.technical} · karne {idea.components.scorecard} · haber{" "}
            {idea.components.news} · risk {idea.components.risk}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function IdeaList({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-widest text-white/35">{title}</div>
      {items.length ? (
        <ul className="space-y-0.5">
          {items.slice(0, 4).map((item, i) => (
            <li key={i} className={tone}>
              › {item}
            </li>
          ))}
        </ul>
      ) : (
        <div className="text-white/35">—</div>
      )}
    </div>
  );
}
