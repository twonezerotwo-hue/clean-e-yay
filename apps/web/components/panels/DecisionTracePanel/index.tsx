"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useCockpitBrief } from "@/lib/queries/hooks";
import { selectDecisionTrace } from "@/lib/selectors/cockpit";

// UX1 — karar izi: agent ne yapmak istedi (candidate), neye düştü (final),
// hangi kapı kesti (blocked_by / restrictive_gates), kanıt referansları.
// Yalnızca state'i açıklar; karar üretmez (backend ViewModel).

type Final = {
  symbol?: string;
  timeframe?: string;
  action?: string;
  candidate_action?: string;
  actionable?: boolean;
  status?: string;
  blocked_by?: string[];
};

export function DecisionTracePanel() {
  const { data, isLoading } = useCockpitBrief();
  if (isLoading) {
    return (
      <PanelFrame id="decision_trace">
        <PanelHeader title="Decision Trace" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const trace = selectDecisionTrace(data);
  const candidates = (trace?.candidate_decisions ?? []) as Final[];
  const finals = (trace?.final_decisions ?? []) as Final[];
  if (!finals.length) {
    return (
      <PanelFrame id="decision_trace">
        <PanelHeader title="Decision Trace" />
        <EmptyState />
      </PanelFrame>
    );
  }
  // candidate'i (symbol,tf) ile eşle → tek satırda candidate → final.
  const candMap = new Map(
    candidates.map((c) => [`${c.symbol}|${c.timeframe}`, c.candidate_action]),
  );
  const rows = finals
    .map((f) => ({
      ...f,
      candidate_action: candMap.get(`${f.symbol}|${f.timeframe}`) ?? f.candidate_action,
    }))
    // candidate ile final ayrışan ya da bloklananları öne al (en bilgilendirici).
    .sort((a, b) => Number(differs(b)) - Number(differs(a)))
    .slice(0, 10);
  const gates = trace?.restrictive_gates ?? [];

  return (
    <PanelFrame id="decision_trace">
      <PanelHeader
        title="Decision Trace"
        subtitle="candidate → final · neden değişti"
        actions={
          trace?.risk_gate?.action ? (
            <span className="rounded px-1.5 py-0.5 bg-white/5 text-[10px] uppercase tracking-wide text-white/60 ring-1 ring-white/10">
              RiskGate {trace.risk_gate.action}
            </span>
          ) : undefined
        }
      />
      {gates.length ? (
        <p className="mb-2 text-[11px] text-accent-magenta/90">
          Kısıtlayıcı kapılar: {gates.join(" · ")}
        </p>
      ) : null}
      <ul className="space-y-1 text-[11px]">
        {rows.map((f, i) => (
          <li
            key={i}
            className="flex items-center justify-between gap-2 border-b border-white/5 pb-0.5"
          >
            <span className="flex items-center gap-1.5">
              <span className="font-medium text-white/80">{f.symbol}</span>
              <span className="rounded border border-white/15 px-1 text-[9px] uppercase text-white/50">
                {f.timeframe}
              </span>
            </span>
            <span className="flex items-center gap-1.5">
              {differs(f) ? (
                <>
                  <span className="line-through text-white/35">{f.candidate_action}</span>
                  <span className="text-white/30">→</span>
                </>
              ) : null}
              <span
                className={
                  f.actionable
                    ? "text-signal-up"
                    : f.status === "SUSPENDED"
                      ? "text-signal-down/80"
                      : "text-white/55"
                }
              >
                {f.action}
              </span>
              {f.blocked_by?.length ? (
                <span
                  className="text-[9px] uppercase tracking-wide text-accent-magenta/80 truncate max-w-[9rem]"
                  title={f.blocked_by.join(", ")}
                >
                  {f.blocked_by[0]}
                </span>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
      {trace?.evidence_refs?.length ? (
        <p className="mt-2 text-[10px] text-white/35 break-all">
          kanıt: {trace.evidence_refs.slice(0, 4).join(" · ")}
        </p>
      ) : null}
    </PanelFrame>
  );
}

function differs(f: Final): boolean {
  return Boolean(
    f.candidate_action && f.action && f.candidate_action !== f.action,
  );
}
