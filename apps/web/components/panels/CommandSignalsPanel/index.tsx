"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useCockpitBrief, useRegimeReport } from "@/lib/queries/hooks";
import { selectTopAssets } from "@/lib/selectors/regime";
import { selectAgentBrief } from "@/lib/selectors/cockpit";
import { DIRECTION_COLOR } from "@/lib/constants";

const STATUS_COLOR: Record<string, string> = {
  CONFIRMED: "text-signal-up",
  PENDING: "text-amber-400",
  BLOCKING: "text-signal-down",
};

// UX1 — bunlar HAM aday sinyaller (raw candidate), final karar DEĞİL. Final
// karar RiskGate'ten geçer; agent act edemiyorsa NOT_ACTIONABLE rozeti.
export function CommandSignalsPanel() {
  const { data, isLoading } = useRegimeReport();
  const brief = selectAgentBrief(useCockpitBrief().data);
  const notActionable = brief ? !brief.can_act : false;
  if (isLoading) {
    return (
      <PanelFrame id="command_signals">
        <PanelHeader title="Aday Sinyalleri" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const assets = selectTopAssets(data, 8);
  if (!assets.length) {
    return (
      <PanelFrame id="command_signals">
        <PanelHeader title="Aday Sinyalleri" />
        <EmptyState />
      </PanelFrame>
    );
  }
  return (
    <PanelFrame id="command_signals">
      <PanelHeader
        title="Aday Sinyalleri"
        subtitle={`${assets.length} varlık · ham candidate (final değil)`}
        actions={
          notActionable ? (
            <span className="rounded px-1.5 py-0.5 bg-accent-magenta/20 text-accent-magenta uppercase tracking-wide text-[10px]">
              NOT_ACTIONABLE
            </span>
          ) : undefined
        }
      />
      <p className="mb-2 text-[10px] text-white/40">
        Ham aday sinyal — final karar RiskGate sonrası belirlenir
        {notActionable ? " (şu an aksiyon kapalı)" : ""}.
      </p>
      <ul className="space-y-1.5 text-sm">
        {assets.map((a) => (
          <li
            key={a.symbol}
            className="flex items-center justify-between border-b border-white/5 pb-1"
          >
            <span className="font-medium">{a.symbol}</span>
            <span className="flex items-center gap-3">
              <span className={DIRECTION_COLOR[a.direction]}>{a.direction}</span>
              <span className={STATUS_COLOR[a.status]}>{a.status}</span>
              <span className="text-white/40">{a.score.toFixed(0)}</span>
            </span>
          </li>
        ))}
      </ul>
    </PanelFrame>
  );
}
