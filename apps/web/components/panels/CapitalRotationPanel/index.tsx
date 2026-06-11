"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { useRegimeReport } from "@/lib/queries/hooks";
import { DIRECTION_COLOR } from "@/lib/constants";

const ROTATION_LAYER = "Sermaye Rotasyonu";

export function CapitalRotationPanel() {
  const { data } = useRegimeReport();
  const layer = (data?.layers ?? []).find(
    (l) => l.name === ROTATION_LAYER || l.name.toLowerCase().includes("rotation"),
  );
  return (
    <PanelFrame id="capital_rotation">
      <PanelHeader title="Sermaye Rotasyonu" />
      {!layer ? (
        <div className="text-xs text-white/40 italic">veri yok</div>
      ) : (
        <div className="space-y-2">
          <div className={`text-xl font-display ${DIRECTION_COLOR[layer.direction]}`}>
            {layer.direction} · {layer.score.toFixed(0)}
          </div>
          <ul className="text-xs text-white/60 space-y-1">
            {(layer.evidence ?? []).slice(0, 6).map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}
    </PanelFrame>
  );
}
