"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useAIReport } from "@/lib/queries/hooks";
import { DIRECTION_COLOR } from "@/lib/constants";
import {
  selectLLMBadge,
  selectLLMSubtitle,
  selectNoActionableDecision,
  selectPersonaSections,
  selectTimeframeSummaryLines,
} from "@/lib/selectors/ai";
import type { PersonaSection } from "@/types/generated/api";

function PersonaBlock({ p }: { p: PersonaSection }) {
  return (
    <div className="rounded-lg border border-ink-700/60 bg-ink-900/40 p-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-accent-cyan uppercase tracking-wider">
          {p.title}
        </span>
        <span className="text-[10px] text-white/40">
          {p.source === "llm" ? p.model ?? "llm" : "deterministic"}
        </span>
      </div>
      <p className="text-xs text-white/75 leading-relaxed">{p.summary}</p>
      {p.concerns?.length ? (
        <ul className="text-[11px] text-amber-300/80 list-disc list-inside space-y-0.5">
          {p.concerns.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      ) : null}
      {p.actionability ? (
        <p className="text-[11px] text-white/60">
          <span className="text-white/40">aksiyon: </span>
          {p.actionability}
        </p>
      ) : null}
      {p.what_would_change_my_mind ? (
        <p className="text-[11px] text-white/50 italic">
          fikrimi değiştirir: {p.what_would_change_my_mind}
        </p>
      ) : null}
      {p.missing_data?.length ? (
        <p className="text-[10px] text-white/40">
          eksik veri: {p.missing_data.slice(0, 3).join("; ")}
        </p>
      ) : null}
    </div>
  );
}

export function AIReportPanel() {
  const { data, isLoading } = useAIReport();
  const personas = selectPersonaSections(data);
  const noAction = selectNoActionableDecision(data);
  const tfLines = selectTimeframeSummaryLines(data);
  const badge = selectLLMBadge(data?.llm);
  return (
    <PanelFrame id="ai_report">
      <PanelHeader title="AI Analist Raporu" subtitle={selectLLMSubtitle(data)} />
      {isLoading ? (
        <LoadingState />
      ) : !data ? (
        <EmptyState />
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div
              className={`text-sm font-medium ${DIRECTION_COLOR[data.verdict] ?? "text-white"}`}
            >
              verdict: {data.verdict}
            </div>
            <span
              className={`text-[10px] px-2 py-0.5 rounded-full border ${
                badge.live
                  ? "border-accent-cyan/50 text-accent-cyan"
                  : "border-white/20 text-white/50"
              }`}
            >
              {badge.label}
            </span>
          </div>
          {noAction ? (
            <div className="rounded-md border border-signal-down/50 bg-signal-down/10 px-3 py-2 text-xs text-signal-down">
              NO ACTIONABLE DECISION — DQS BLOCKED veya risk gate kısıtlayıcı;
              rapor sadece durumu açıklar.
            </div>
          ) : null}
          <p className="text-sm text-white/70 leading-relaxed whitespace-pre-line">
            {data.narrative}
          </p>
          {personas.length ? (
            <div className="space-y-2">
              {personas.map((p) => (
                <PersonaBlock key={p.persona} p={p} />
              ))}
            </div>
          ) : null}
          {tfLines.length ? (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-white/40 mb-1">
                Timeframe özeti
              </div>
              <ul className="text-xs text-white/60 space-y-0.5">
                {tfLines.slice(0, 6).map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {data.key_signals?.length ? (
            <ul className="text-xs text-white/60 list-disc list-inside space-y-1">
              {data.key_signals.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </PanelFrame>
  );
}
