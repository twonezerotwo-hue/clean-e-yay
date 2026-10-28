"use client";

import { useMemo, useState } from "react";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { MobileFlipCard } from "@/components/cockpit/MobileFlipCard";
import { useCockpitBrief, useNewsCurrent, useRegimeReport } from "@/lib/queries/hooks";
import { headlineImpactBadges } from "@/lib/selectors/regime";
import { fmtRelative } from "@/lib/format";
import { DIRECTION_COLOR } from "@/lib/constants";
import { resolveNewsLink } from "@/lib/news-links";
import type { NewsHeadline } from "@/types/generated/api";
import { NewsMapRadarLayer } from "./NewsMapRadarLayer";

// UX4 — ham haber detaydır: ilk birkaç başlık görünür, gerisi collapsed.
const NEWS_HEAD = 6;

type Headline = NewsHeadline;

const FOCUS_COUNTRIES = [
  { id: "ALL", label: "Tümü" },
  { id: "USA", label: "ABD" },
  { id: "Iran", label: "İran" },
  { id: "China", label: "Çin" },
  { id: "Russia", label: "Rusya" },
  { id: "Israel", label: "İsrail" },
] as const;

function headlineCountries(h: Headline): string[] {
  const countries = (h as Headline & { countries?: string[] }).countries;
  return countries?.length ? countries : h.region ? [h.region] : [];
}

function HeadlineItem({ h }: { h: Headline }) {
  const badges = headlineImpactBadges(h.asset_impact);
  const link = resolveNewsLink(h);
  const disabled = link.href === "#";
  return (
    <li className="border-b border-white/5 pb-2 group">
      <a
        href={link.href}
        target={disabled ? undefined : "_blank"}
        rel={disabled ? undefined : "noopener noreferrer"}
        title={link.title}
        aria-disabled={disabled}
        onClick={(e) => {
          if (disabled) e.preventDefault();
        }}
        className={`block rounded px-1 -mx-1 py-0.5 transition-colors ${
          disabled ? "cursor-not-allowed opacity-70" : "hover:bg-white/[0.02]"
        }`}
      >
      <div className="flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-widest text-white/40">
        <span>{h.source}</span>
        <span>·</span>
        <span>{fmtRelative(h.ts)}</span>
        {headlineCountries(h).slice(0, 3).map((country) => (
          <span key={country} className="rounded border border-cyan-300/20 px-1 text-cyan-200/65">
            {country}
          </span>
        ))}
        {h.sentiment ? (
          <>
            <span>·</span>
            <span className={DIRECTION_COLOR[h.sentiment]}>{h.sentiment}</span>
          </>
        ) : null}
        <span className="ml-auto text-cyan-300/0 group-hover:text-cyan-300/80 transition-colors">
          {link.kind === "direct" ? "kaynak ↗" : `${link.label} ara ↗`}
        </span>
      </div>
      <div className="text-white/85 mt-1 break-words group-hover:text-white">{h.title_tr || h.title}</div>
      {/* P0 — etkilenen semboller (deterministik kararda asset_impact) veya
          yoksa "yalnızca bağlam" rozeti. Haber karar VERMEZ; bağlam sağlar. */}
      <div className="mt-1 flex flex-wrap items-center gap-1">
        {h.actionable && badges.length ? (
          badges.map((b) => (
            <span
              key={b.symbol}
              className={`rounded border border-white/10 px-1 py-px text-[9px] font-mono ${
                b.dir > 0
                  ? "text-signal-up"
                  : b.dir < 0
                    ? "text-signal-down"
                    : "text-white/50"
              }`}
            >
              {b.symbol} {b.arrow}
            </span>
          ))
        ) : (
          <span className="rounded border border-white/10 px-1 py-px text-[9px] uppercase tracking-wider text-white/30">
            yalnızca bağlam
          </span>
        )}
      </div>
      </a>
    </li>
  );
}

type NewsPanelProps = {
  defaultView?: "list" | "radar";
};

export function NewsPanel({ defaultView = "list" }: NewsPanelProps) {
  const wall = useNewsCurrent();
  const cockpit = useCockpitBrief();
  const regime = useRegimeReport();
  const [focus, setFocus] = useState<(typeof FOCUS_COUNTRIES)[number]["id"]>("ALL");
  const sourceItems = wall.data?.headlines?.length
    ? wall.data.headlines
    : cockpit.data?.headlines?.length
      ? cockpit.data.headlines
      : regime.data?.headlines ?? [];
  const allItems = useMemo(() => sourceItems.slice(0, 96), [sourceItems]);
  const items = useMemo(
    () => focus === "ALL"
      ? allItems
      : allItems.filter((headline) => headlineCountries(headline).includes(focus)),
    [allItems, focus],
  );
  const isLoading = wall.isLoading && cockpit.isLoading && regime.isLoading;
  const headlineCount = wall.data?.count ?? allItems.length;
  const head = items.slice(0, NEWS_HEAD);
  const rest = items.slice(NEWS_HEAD);
  const [view, setView] = useState<"list" | "radar">(defaultView);
  const hasItems = items.length > 0;
  const primary = items[0];
  const primaryBadges = primary ? headlineImpactBadges(primary.asset_impact).slice(0, 2) : [];
  const eventRisk = regime.data?.event_risk?.level ?? "clear";
  const liveSetups = (cockpit.data?.news_prepared_setups ?? []).filter((setup) =>
    setup.status === "ARMED" || setup.status === "WAITING_RISK",
  );
  return (
    <>
    <div className="h-full">
    <PanelFrame id="news" className="h-full">
      <PanelHeader
        title="Haberler"
        subtitle={`${items.length}/${headlineCount} başlık · ${wall.data?.coverage?.foreign_affairs_feeds ?? 5} dış politika akışı`}
        actions={
          hasItems ? (
            <div className="flex items-center gap-1 text-[10px] font-mono">
              <button
                type="button"
                onClick={() => setView("list")}
                className={`rounded border px-1.5 py-0.5 uppercase tracking-widest ${
                  view === "list"
                    ? "border-accent-cyan/60 text-accent-cyan"
                    : "border-white/15 text-white/40 hover:text-white/70"
                }`}
              >
                Liste
              </button>
              <button
                type="button"
                onClick={() => setView("radar")}
                className={`rounded border px-1.5 py-0.5 uppercase tracking-widest ${
                  view === "radar"
                    ? "border-accent-cyan/60 text-accent-cyan"
                    : "border-white/15 text-white/40 hover:text-white/70"
                }`}
              >
                Radar
              </button>
            </div>
          ) : undefined
        }
      />
      <div className="mb-2 flex flex-wrap gap-1">
        {FOCUS_COUNTRIES.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={() => setFocus(option.id)}
            className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wider transition-colors ${
              focus === option.id
                ? "border-accent-cyan/60 text-accent-cyan"
                : "border-white/10 text-white/40 hover:text-white/70"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
      <div className="mb-2 rounded border border-emerald-300/15 bg-emerald-300/[0.03] px-2 py-1 text-[10px] text-emerald-100/65">
        {liveSetups.length
          ? `Haber + teknik teyit: ${liveSetups.length} aday RiskGate için izleniyor · emir yalnız paper-safe kapıdan geçer.`
          : "Haber + grafik teyidi birlikte oluştuğunda aday hazırlanır; haber tek başına emir üretmez."}
      </div>
      {isLoading ? (
        <LoadingState />
      ) : !hasItems ? (
        <EmptyState />
      ) : view === "radar" ? (
        <NewsMapRadarLayer headlines={items} />
      ) : (
        <>
          <ul className="space-y-2 text-sm">
            {head.map((h) => (
              <HeadlineItem key={h.id} h={h} />
            ))}
          </ul>
          {rest.length ? (
            <details className="group mt-2">
              <summary className="cursor-pointer select-none list-none text-[11px] text-accent-cyan/70 hover:text-accent-cyan">
                +{rest.length} başlık daha ▾
              </summary>
              <ul className="space-y-2 text-sm mt-2 max-h-[20rem] overflow-y-auto pr-1">
                {rest.map((h) => (
                  <HeadlineItem key={h.id} h={h} />
                ))}
              </ul>
            </details>
          ) : null}
        </>
      )}
    </PanelFrame>
    </div>
    <MobileFlipCard
      className="mobile-force-hidden"
      title="Haberler"
      front={
        <div className="mobile-news-front">
          <div className="mobile-back-head">
            <div>
              <p className="mobile-kicker">Haberler</p>
              <strong>{items.length} başlık</strong>
            </div>
            <span>Risk: {String(eventRisk)}</span>
          </div>
          <div className="mobile-news-map-preview" aria-hidden="true">
            <span />
            <i />
            <b />
          </div>
          {isLoading ? (
            <p className="mobile-summary-line">Yükleniyor...</p>
          ) : !primary ? (
            <p className="mobile-summary-line">Aktif son dakika haber kaydı yok.</p>
          ) : (
            <div className="mobile-news-main">
              <p>{primary.source} · {fmtRelative(primary.ts)}</p>
              <strong>{primary.title_tr || primary.title}</strong>
              <div>
                {primaryBadges.length ? (
                  primaryBadges.map((badge) => (
                    <span key={badge.symbol}>
                      {badge.symbol} {badge.arrow}
                    </span>
                  ))
                ) : (
                  <span>yalnızca bağlam</span>
                )}
              </div>
            </div>
          )}
          <p className="mobile-flip-hint">Detay için dokun</p>
        </div>
      }
      back={
        <div className="mobile-flip-card__scroll mobile-news-back">
          <div className="mobile-back-head">
            <div>
              <p className="mobile-kicker">Haber detayı</p>
              <strong>{view === "radar" ? "Radar" : "Liste"}</strong>
            </div>
            <div className="mobile-window-tabs" data-no-flip>
              <button
                type="button"
                onClick={() => setView("list")}
                className={view === "list" ? "is-active" : ""}
              >
                Liste
              </button>
              <button
                type="button"
                onClick={() => setView("radar")}
                className={view === "radar" ? "is-active" : ""}
              >
                Radar
              </button>
            </div>
          </div>
          {isLoading ? (
            <LoadingState />
          ) : !hasItems ? (
            <EmptyState />
          ) : view === "radar" ? (
            <div className="mobile-news-radar-shell">
              <NewsMapRadarLayer headlines={items} />
            </div>
          ) : (
            <ul className="space-y-2 text-sm">
              {items.map((h) => (
                <HeadlineItem key={h.id} h={h} />
              ))}
            </ul>
          )}
        </div>
      }
    />
    </>
  );
}
