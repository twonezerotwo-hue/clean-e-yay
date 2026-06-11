"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useRegimeReport } from "@/lib/queries/hooks";
import { selectCatalysts } from "@/lib/selectors/regime";
import { fmtTime } from "@/lib/format";

const IMP: Record<string, string> = {
  high: "text-signal-down",
  medium: "text-amber-400",
  low: "text-white/40",
};

export function EventCalendarPanel() {
  const { data, isLoading } = useRegimeReport();
  const items = selectCatalysts(data, 8);
  return (
    <PanelFrame id="event_calendar">
      <PanelHeader title="Olay Takvimi" />
      {isLoading ? (
        <LoadingState />
      ) : !items.length ? (
        <EmptyState />
      ) : (
        <ul className="space-y-2 text-sm">
          {items.map((c) => (
            <li key={c.id} className="flex items-center justify-between">
              <span className="text-white/80">{c.title}</span>
              <span className={`text-xs ${IMP[c.importance ?? "low"]}`}>
                {fmtTime(c.ts)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </PanelFrame>
  );
}
