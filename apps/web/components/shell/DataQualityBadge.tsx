import { fmtRelative } from "@/lib/format";

export function DataQualityBadge({
  dqs,
  generatedAt,
  fallback,
}: {
  dqs?: number;
  generatedAt?: string;
  fallback?: boolean;
}) {
  const score = dqs ?? null;
  const color =
    score == null
      ? "bg-white/10 text-white/50"
      : score >= 75
      ? "bg-signal-up/20 text-signal-up"
      : score >= 55
      ? "bg-amber-400/20 text-amber-400"
      : "bg-signal-down/20 text-signal-down";

  return (
    <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest">
      <span className={`rounded px-1.5 py-0.5 ${color}`}>
        DQS {score == null ? "—" : Math.round(score)}
      </span>
      {fallback ? (
        <span className="rounded px-1.5 py-0.5 bg-signal-down/20 text-signal-down">
          fallback
        </span>
      ) : null}
      {generatedAt ? (
        <span className="text-white/40 normal-case">
          {fmtRelative(generatedAt)}
        </span>
      ) : null}
    </div>
  );
}
