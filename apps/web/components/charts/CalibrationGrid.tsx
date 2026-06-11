import type { CalibrationBin } from "@/types/generated/api";

import { fmtPct } from "@/lib/format";

/**
 * Reliability diagram — tahmin edilen olasılık vs. gözlenen frekans.
 * Diyagonale yakın olursa kalibrasyon iyi demektir.
 */
export function CalibrationGrid({
  bins,
  size = 220,
}: {
  bins: CalibrationBin[];
  size?: number;
}) {
  if (!bins.length) {
    return <div className="text-xs text-white/40 italic">yeterli veri yok</div>;
  }
  const pad = 16;
  const w = size;
  const h = size;
  return (
    <div className="flex items-center gap-4">
      <svg width={w} height={h} className="block">
        {/* diagonal */}
        <line
          x1={pad}
          y1={h - pad}
          x2={w - pad}
          y2={pad}
          stroke="rgba(255,255,255,0.2)"
          strokeDasharray="3 3"
        />
        {bins.map((b, i) => {
          const cx = pad + b.predicted * (w - 2 * pad);
          const cy = h - pad - b.observed * (h - 2 * pad);
          const r = Math.max(2, Math.min(8, Math.sqrt(b.count)));
          return <circle key={i} cx={cx} cy={cy} r={r} fill="#22d3ee" fillOpacity={0.7} />;
        })}
      </svg>
      <ul className="text-xs space-y-1">
        {bins.map((b, i) => (
          <li key={i} className="flex justify-between gap-3 text-white/70">
            <span>{fmtPct(b.predicted, 0)} → {fmtPct(b.observed, 0)}</span>
            <span className="text-white/40">n={b.count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
