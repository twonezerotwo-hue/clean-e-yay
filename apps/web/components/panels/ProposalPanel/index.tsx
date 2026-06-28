"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import {
  useApproveGovernorProposal,
  useGovernorProposals,
  useRejectGovernorProposal,
} from "@/lib/queries/hooks";
import type { GovernorProposalsView } from "@/types/generated/api";

// Öneri Defteri (packages/governor/proposals.py). Her tipte owner-onaylı öneri,
// kanıtıyla. DEĞİŞMEZ: approve/reject yalnızca DEFTER kaydını günceller; canlı
// config (weights/thresholds/risk/mode) değişmez — uygulama owner-gated ayrı
// yollardan yapılır. Frontend hesap YAPMAZ. PAPER_SAFE / NO_EXECUTION.

export function ProposalPanel() {
  const { data, isLoading } = useGovernorProposals();
  const approve = useApproveGovernorProposal();
  const reject = useRejectGovernorProposal();

  if (isLoading) {
    return (
      <PanelFrame id="governor_proposals">
        <PanelHeader title="Öneri Defteri" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: GovernorProposalsView | undefined = data;
  const pending = d?.pending ?? [];
  const history = d?.history ?? [];
  const busy = approve.isPending || reject.isPending;

  return (
    <PanelFrame id="governor_proposals">
      <PanelHeader
        title="Öneri Defteri"
        subtitle="Owner onayı bekleyen öneriler"
        actions={
          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-white/55">
            {pending.length} bekliyor
          </span>
        }
      />

      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] text-white/55">
        Onay yalnızca defter kaydını günceller; canlı ayar otomatik değişmez.
      </p>

      {pending.length ? (
        <ul className="space-y-2">
          {pending.map((p) => (
            <li
              key={p.proposal_id}
              className="rounded border border-amber-400/20 bg-amber-400/[0.04] px-2 py-2"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-[10px] uppercase tracking-wide text-amber-300/80">
                    {p.proposal_type}
                  </div>
                  <div className="text-xs font-medium text-white/85">{p.title}</div>
                  {p.summary ? (
                    <div className="mt-0.5 text-[11px] text-white/55">{p.summary}</div>
                  ) : null}
                </div>
                <div className="flex shrink-0 gap-1">
                  <button
                    type="button"
                    onClick={() => approve.mutate(p.proposal_id)}
                    disabled={busy}
                    className="rounded border border-signal-up/30 bg-signal-up/10 px-2 py-0.5 text-[11px] text-signal-up hover:bg-signal-up/20 disabled:opacity-50"
                  >
                    Onayla
                  </button>
                  <button
                    type="button"
                    onClick={() => reject.mutate({ proposalId: p.proposal_id })}
                    disabled={busy}
                    className="rounded border border-signal-down/30 bg-signal-down/10 px-2 py-0.5 text-[11px] text-signal-down hover:bg-signal-down/20 disabled:opacity-50"
                  >
                    Reddet
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="text-[11px] text-white/35">Bekleyen öneri yok.</div>
      )}

      {history.length ? (
        <details className="mt-3">
          <summary className="cursor-pointer text-[10px] uppercase tracking-widest text-white/35">
            Geçmiş ({history.length})
          </summary>
          <ul className="mt-1 space-y-0.5 text-[11px] text-white/55">
            {history.slice(0, 8).map((p) => (
              <li key={p.proposal_id} className="flex justify-between gap-2">
                <span className="truncate">{p.title}</span>
                <span
                  className={
                    p.status === "APPROVED"
                      ? "text-signal-up"
                      : p.status === "REJECTED"
                        ? "text-signal-down"
                        : "text-white/40"
                  }
                >
                  {p.status}
                </span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </PanelFrame>
  );
}
