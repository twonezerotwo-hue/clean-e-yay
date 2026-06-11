"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useRegimeReport } from "@/lib/queries/hooks";
import { selectHeadlines } from "@/lib/selectors/regime";
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
          {items.map((h) => (
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
            </li>
          ))}
        </ul>
      )}
    </PanelFrame>
  );
}
