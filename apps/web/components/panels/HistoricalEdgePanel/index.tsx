"use client";

import { useEffect, useMemo, useState } from "react";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useHistoricalEdge, useMistakes } from "@/lib/queries/hooks";
import { fmtNum, fmtPct, fmtRelative } from "@/lib/format";

function confidenceTone(value?: string) {
  if (value === "strong" || value === "usable") return "bg-signal-up/20 text-signal-up";
  if (value === "weak") return "bg-amber-400/20 text-amber-300";
  return "bg-white/10 text-white/55";
}

function uniqueFingerprints(data: ReturnType<typeof useMistakes>["data"]) {
  const set = new Set<string>();
  for (const verdict of data?.verdicts ?? []) {
    if (verdict.action !== "NEUTRAL") set.add(verdict.fingerprint);
  }
  for (const record of data?.records ?? []) {
    set.add(record.fingerprint);
  }
  return Array.from(set).slice(0, 40);
}

export function HistoricalEdgePanel() {
  const mistakes = useMistakes();
  const suggestions = useMemo(
    () => uniqueFingerprints(mistakes.data),
    [mistakes.data],
  );
  const [fingerprint, setFingerprint] = useState("");
  const [defaultSelected, setDefaultSelected] = useState(false);
  const selected = fingerprint.trim();
  const edge = useHistoricalEdge(selected);

  useEffect(() => {
    if (!defaultSelected && !fingerprint && suggestions[0]) {
      setFingerprint(suggestions[0]);
      setDefaultSelected(true);
    }
  }, [defaultSelected, fingerprint, suggestions]);

  const result = edge.data?.result;

  return (
    <PanelFrame id="historical_edge">
      <PanelHeader
        title="Geçmiş Benzer İşlemler"
        subtitle="Benzer kurulumlar geçmişte nasıl sonuçlandı"
        actions={
          result ? (
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] uppercase tracking-widest ${confidenceTone(
                result.edge_confidence,
              )}`}
            >
              {result.edge_confidence}
            </span>
          ) : undefined
        }
      />

      <div className="mb-3 grid gap-2 sm:grid-cols-[1fr_auto]">
        <input
          value={fingerprint}
          onChange={(event) => setFingerprint(event.target.value)}
          placeholder="fingerprint gir"
          className="min-w-0 rounded border border-white/12 bg-black/30 px-2 py-1.5 font-mono text-xs text-white/80 outline-none focus:border-accent-cyan/45"
        />
        {suggestions.length ? (
          <select
            value={suggestions.includes(selected) ? selected : ""}
            onChange={(event) => setFingerprint(event.target.value)}
            className="rounded border border-white/12 bg-black/30 px-2 py-1.5 text-xs text-white/70 outline-none focus:border-accent-cyan/45"
          >
            <option value="">Sec</option>
            {suggestions.map((item) => (
              <option key={item} value={item}>
                {item.length > 38 ? `${item.slice(0, 38)}...` : item}
              </option>
            ))}
          </select>
        ) : null}
      </div>

      {mistakes.isLoading || edge.isLoading ? (
        <LoadingState />
      ) : !selected ? (
        <EmptyState message="Fingerprint sec veya gir." />
      ) : edge.error ? (
        <div className="rounded border border-signal-down/30 bg-signal-down/5 px-2 py-2 text-xs text-signal-down/90">
          {edge.error instanceof Error ? edge.error.message : "Historical edge okunamadi."}
        </div>
      ) : !result ? (
        <EmptyState message="Historical edge sonucu yok." />
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <Metric label="Sample" value={String(result.sample_count)} />
            <Metric label="Strong" value={String(result.strong_sample_count)} />
            <Metric label="Win" value={fmtPct(result.win_rate, 0)} />
            <Metric label="Avg PnL" value={fmtNum(result.avg_pnl, 0)} />
          </div>

          <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2">
            <div className="mb-1 flex items-center justify-between gap-2 text-[10px] uppercase tracking-widest text-white/38">
              <span>Similarity weights</span>
              <span>min {fmtPct(result.similarity_threshold, 0)}</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(edge.data?.similarity_weights ?? {}).map(([key, value]) => (
                <span
                  key={key}
                  className="rounded border border-white/10 bg-black/24 px-1.5 py-0.5 text-[10px] text-white/58"
                >
                  {key} {fmtPct(value, 0)}
                </span>
              ))}
            </div>
          </div>

          <div className="text-[10px] uppercase tracking-widest text-white/35">
            Matched trades ({result.matched_trade_ids.length})
          </div>
          {result.matched_trade_ids.length ? (
            <div className="flex flex-wrap gap-1.5">
              {result.matched_trade_ids.slice(0, 10).map((id) => (
                <span
                  key={id}
                  title={id}
                  className="max-w-[10rem] truncate rounded border border-white/10 bg-white/[0.025] px-1.5 py-0.5 font-mono text-[10px] text-white/55"
                >
                  {id}
                </span>
              ))}
            </div>
          ) : (
            <div className="text-xs text-white/35">
              Benzer kapanmis trade bulunmadi. Son mistake kaydi:{" "}
              {fmtRelative(mistakes.data?.records?.[0]?.last_seen_at)}
            </div>
          )}
        </div>
      )}
    </PanelFrame>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-white/10 bg-white/[0.025] px-2 py-2">
      <div className="text-[10px] uppercase tracking-widest text-white/38">{label}</div>
      <div className="mt-1 font-display text-lg leading-none tabular-nums text-white/86">
        {value}
      </div>
    </div>
  );
}
