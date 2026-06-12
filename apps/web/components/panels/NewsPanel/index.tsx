"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useRegimeReport } from "@/lib/queries/hooks";
import { headlineImpactBadges, selectHeadlines } from "@/lib/selectors/regime";
import { fmtRelative } from "@/lib/format";
import { DIRECTION_COLOR } from "@/lib/constants";

export function NewsPanel() {
  const { data, isLoading } = useRegimeReport();
  const items = selectHeadlines(data, 14);
  return (
    <PanelFrame id="news">
      <PanelHeader title="Haberler" subtitle={`${items.length} başlık`} />
      {isLoading ? (
        <LoadingState />
      ) : !items.length ? (
        <EmptyState />
      ) : (
        <ul className="space-y-2 text-sm max-h-[24rem] overflow-y-auto pr-1">
          {items.map((h) => {
            const badges = headlineImpactBadges(h.asset_impact);
            return (
              <li key={h.id} className="border-b border-white/5 pb-2">
                <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-white/40">
                  <span>{h.source}</span>
                  <span>·</span>
                  <span>{fmtRelative(h.ts)}</span>
                  {h.sentiment ? (
                    <>
                      <span>·</span>
                      <span className={DIRECTION_COLOR[h.sentiment]}>{h.sentiment}</span>
                    </>
                  ) : null}
                </div>
                <div className="text-white/85 mt-1">{h.title_tr || h.title}</div>
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
              </li>
            );
          })}
        </ul>
      )}
    </PanelFrame>
  );
}
