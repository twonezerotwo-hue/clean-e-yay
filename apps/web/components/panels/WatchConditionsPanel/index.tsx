"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useCockpitBrief } from "@/lib/queries/hooks";
import { selectAgentBrief } from "@/lib/selectors/cockpit";

// UX1 — agent ne bekliyor? Bir sonraki izlenecek tetik koşulları. "Sağ kol
// agent" hissi için kritik. Koşullar backend'de deterministik üretilir.

const ICON: Record<string, string> = {
  position_count: "▦",
  cluster_exposure: "⛓",
  time_stop_resolved: "⏱",
  provider_restored: "📡",
  catalyst_halflife: "⚑",
  dqs_verified: "✓",
  risk_gate_clear: "🔓",
};

export function WatchConditionsPanel() {
  const { data, isLoading } = useCockpitBrief();
  if (isLoading) {
    return (
      <PanelFrame id="watch_conditions">
        <PanelHeader title="Watch / Trigger Conditions" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const conditions = selectAgentBrief(data)?.next_watch_conditions ?? [];
  if (!conditions.length) {
    return (
      <PanelFrame id="watch_conditions">
        <PanelHeader title="Watch / Trigger Conditions" subtitle="izlenecek koşul yok" />
        <p className="text-xs text-white/45">
          Agent şu an aktif bir tetik koşulu beklemiyor.
        </p>
      </PanelFrame>
    );
  }
  return (
    <PanelFrame id="watch_conditions">
      <PanelHeader
        title="Watch / Trigger Conditions"
        subtitle={`${conditions.length} koşul izleniyor`}
      />
      <ul className="space-y-1.5 text-xs">
        {conditions.map((w, i) => (
          <li key={i} className="flex items-start gap-2 border-b border-white/5 pb-1">
            <span className="text-accent-cyan/80 w-4 shrink-0 text-center">
              {ICON[w.key] ?? "›"}
            </span>
            <div className="min-w-0">
              <div className="text-white/80">{w.label}</div>
              {w.detail ? (
                <div className="text-[10px] text-white/40">{w.detail}</div>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </PanelFrame>
  );
}
