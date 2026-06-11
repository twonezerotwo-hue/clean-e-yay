"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { useDashboardState } from "@/lib/queries/hooks";

export function PanelAuditPanel() {
  const { data } = useDashboardState();
  const warnings = data?.warnings ?? [];
  return (
    <PanelFrame id="panel_audit">
      <PanelHeader title="Pano Denetimi" subtitle={`${warnings.length} uyarı`} />
      {warnings.length === 0 ? (
        <div className="text-xs text-white/40 italic">tutarsızlık yok</div>
      ) : (
        <ul className="text-xs space-y-1 text-amber-300">
          {warnings.map((w, i) => (
            <li key={i}>· {w}</li>
          ))}
        </ul>
      )}
    </PanelFrame>
  );
}
