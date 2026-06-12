"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useRegimeReport } from "@/lib/queries/hooks";
import { selectCatalysts, selectEventRisk } from "@/lib/selectors/regime";
import { fmtTime } from "@/lib/format";

const IMP: Record<string, string> = {
  critical: "text-signal-down",
  high: "text-signal-down",
  medium: "text-amber-400",
  low: "text-white/40",
};

// P0 — event riski yalnızca kısıtlayıcı; seviye → görünür actionability rozeti.
const LEVEL_BADGE: Record<string, { label: string; cls: string }> = {
  NO_POSITION_INCREASE: {
    label: "POZ. ARTIŞI DURDU",
    cls: "bg-signal-down/15 text-signal-down border-signal-down/40",
  },
  WATCH: {
    label: "DİKKAT",
    cls: "bg-amber-400/10 text-amber-300 border-amber-400/40",
  },
};

export function EventCalendarPanel() {
  const { data, isLoading } = useRegimeReport();
  const items = selectCatalysts(data, 8);
  const ev = selectEventRisk(data);
  return (
    <PanelFrame id="event_calendar">
      <PanelHeader title="Olay Takvimi" />
      {isLoading ? (
        <LoadingState />
      ) : !items.length ? (
        <EmptyState />
      ) : (
        <div className="space-y-3">
          {ev && ev.level !== "NONE" ? (
            <div
              className={`rounded-md border px-2 py-1.5 text-[11px] leading-snug ${
                ev.restrictive
                  ? "border-signal-down/40 bg-signal-down/10 text-signal-down"
                  : "border-amber-400/40 bg-amber-400/10 text-amber-300"
              }`}
            >
              {ev.reason}
            </div>
          ) : (
            <div className="text-[11px] text-white/35">
              Yaklaşan yüksek etkili olay yok — yeni pozisyon kısıtı yok.
            </div>
          )}
          <ul className="space-y-2 text-sm">
            {items.map((c) => {
              const badge = LEVEL_BADGE[c.event_level ?? "NONE"];
              return (
                <li key={c.id} className="flex items-center justify-between gap-2">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="truncate text-white/80">{c.title}</span>
                    {badge ? (
                      <span
                        className={`shrink-0 rounded border px-1 py-px text-[9px] uppercase tracking-wider ${badge.cls}`}
                      >
                        {badge.label}
                      </span>
                    ) : null}
                  </span>
                  <span className={`shrink-0 text-xs ${IMP[c.importance ?? "low"]}`}>
                    {fmtTime(c.ts)}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </PanelFrame>
  );
}
