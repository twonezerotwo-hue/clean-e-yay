"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { useRegimeReport } from "@/lib/queries/hooks";
import { REGIME_COLOR } from "@/lib/constants";

export function ScenarioPanel() {
  const { data } = useRegimeReport();
  const regime = data?.regime_label ?? "—";
  return (
    <PanelFrame id="scenario">
      <PanelHeader title="Senaryo" subtitle="aktif makro rejim" />
      <div className={`text-3xl font-display ${REGIME_COLOR[regime] ?? "text-white"}`}>
        {regime}
      </div>
      <ul className="mt-3 text-xs space-y-1 text-white/60">
        {(data?.layers ?? []).slice(0, 4).map((l) => (
          <li key={l.name} className="flex justify-between">
            <span>{l.name}</span>
            <span className="text-white/80">{l.score.toFixed(0)}</span>
          </li>
        ))}
      </ul>
    </PanelFrame>
  );
}
