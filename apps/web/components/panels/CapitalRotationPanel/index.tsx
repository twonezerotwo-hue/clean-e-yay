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
  const evidence = layer?.evidence ?? [];
  // P0 — rotation artık gerçek 1d OHLCV momentum/oran motorundan gelir; veri
  // yetersizse evidence boş + nötr 50 (UNAVAILABLE → consensus redistribute).
  const unavailable = !layer || (evidence.length === 0 && layer.score === 50);
  return (
    <PanelFrame id="capital_rotation">
      <PanelHeader
        title="Sermaye Rotasyonu"
        subtitle="gerçek 30g momentum + çapraz oran"
      />
      {!layer ? (
        <div className="text-xs text-white/40 italic">veri yok</div>
      ) : (
        <div className="space-y-2">
          <div className="flex items-baseline gap-3">
            <div className={`text-xl font-display ${DIRECTION_COLOR[layer.direction]}`}>
              {layer.direction} · {layer.score.toFixed(0)}
            </div>
            {unavailable ? (
              <span className="rounded border border-amber-400/40 bg-amber-400/10 px-1.5 py-px text-[9px] uppercase tracking-wider text-amber-300">
                veri yetersiz · nötr
              </span>
            ) : null}
          </div>
          {unavailable ? (
            <p className="text-xs text-white/40 leading-snug">
              Rotasyon serileri yetersiz — consensus quantum modülü düşürülüp
              ağırlık yeniden dağıtıldı (mock skor üretilmez).
            </p>
          ) : (
            <ul className="text-xs text-white/65 space-y-1">
              {evidence.slice(0, 6).map((e, i) => (
                <li key={i} className="leading-snug">
                  {e}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </PanelFrame>
  );
}
