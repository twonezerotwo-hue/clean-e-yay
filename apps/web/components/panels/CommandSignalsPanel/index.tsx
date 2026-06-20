"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useCockpitBrief, useDataSnapshot, useRegimeReport } from "@/lib/queries/hooks";
import { selectTopAssets } from "@/lib/selectors/regime";
import { selectAgentBrief } from "@/lib/selectors/cockpit";

import HolographicLayer from "./HolographicLayer";
import HolographicErrorBoundary from "./HolographicErrorBoundary";
import MultiTfMatrix from "./MultiTfMatrix";
import { adaptToHolo } from "./holo-adapter";

// UX1 — ham aday sinyaller (raw candidate), final karar DEĞİL. Holografik
// görünüm; karar üretmez, PAPER_SAFE / NO_EXECUTION.
export function CommandSignalsPanel() {
  const { data: regime, isLoading } = useRegimeReport();
  const { data: snap } = useDataSnapshot();
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
  const assets = selectTopAssets(regime, 8);
  if (!assets.length) {
    return (
      <PanelFrame id="command_signals">
        <PanelHeader title="Aday Sinyalleri" />
        <EmptyState />
      </PanelFrame>
    );
  }
  const holoSignals = adaptToHolo(assets, snap?.prices, snap?.technicals_by_tf);
  return (
    <PanelFrame id="command_signals">
      <PanelHeader
        title="Aday Sinyalleri"
        subtitle="ham candidate · final değil · holografik görünüm"
        actions={
          notActionable ? (
            <span className="rounded px-1.5 py-0.5 bg-accent-magenta/20 text-accent-magenta uppercase tracking-wide text-[10px]">
              NOT_ACTIONABLE
            </span>
          ) : undefined
        }
      />
      <HolographicErrorBoundary>
        <div className="space-y-3">
          <HolographicLayer signals={holoSignals} />
          <div className="rounded-lg border border-slate-700/50 bg-[#070d18] overflow-hidden">
            <MultiTfMatrix signals={holoSignals} />
          </div>
        </div>
      </HolographicErrorBoundary>
    </PanelFrame>
  );
}
