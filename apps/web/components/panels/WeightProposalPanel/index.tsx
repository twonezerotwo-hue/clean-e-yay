"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useRebalanceProposal } from "@/lib/queries/hooks";
import { qk } from "@/lib/queries/keys";
import { api } from "@/lib/api/client";
import {
  selectActiveVersion,
  selectPending,
  selectTopDeltas,
} from "@/lib/selectors/rebalance";
import { fmtNum, fmtRelative } from "@/lib/format";

type ActionKind = "propose" | "approve" | "reject";

function describeResult(
  res: Awaited<ReturnType<typeof api.rebalancePropose>>,
): string | null {
  const detail = res.detail ?? {};
  const reason = typeof detail.reason === "string" ? detail.reason : "";
  if (res.status === "NO_CHANGE" || reason === "no_weight_delta") {
    return "Yeni öneri yok: mevcut ağırlıklardan anlamlı fark çıkmadı.";
  }
  if (reason === "no_module_diversity") {
    return "Yeni öneri yok: öğrenme verisi tek modülde yoğunlaşıyor; ağırlık değiştirmek için en az 2 modül karşılaştırılmalı.";
  }
  if (reason === "below_min_total") {
    const min = typeof detail.min_required === "number" ? detail.min_required : 10;
    return `Yeni öneri yok: en az ${min} verified trade gerekiyor.`;
  }
  if (reason === "no_module_meets_min") {
    return "Yeni öneri yok: modül başına yeterli verified trade yok.";
  }
  if (res.status === "PENDING") return null;
  return res.status ? `Öneri üretilmedi: ${res.status}.` : null;
}

export function WeightProposalPanel() {
  const { data, isLoading } = useRebalanceProposal();
  const qc = useQueryClient();
  const [busy, setBusy] = useState<ActionKind | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const runAction = async (kind: ActionKind) => {
    setBusy(kind);
    setError(null);
    try {
      if (kind === "propose") {
        const res = await api.rebalancePropose("NEUTRAL");
        setInfo(describeResult(res));
      } else if (kind === "approve") {
        await api.rebalanceApprove("owner");
        setInfo(null);
      } else {
        await api.rebalanceReject("owner_reject");
        setInfo(null);
      }
      await qc.invalidateQueries({ queryKey: qk.rebalanceProposal });
      await qc.invalidateQueries({ queryKey: qk.learningSummary });
      await qc.invalidateQueries({ queryKey: qk.tfWeights });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Aksiyon tamamlanamadi.");
    } finally {
      setBusy(null);
    }
  };

  if (isLoading) {
    return (
      <PanelFrame id="weight_proposal">
        <PanelHeader title="Ağırlık Önerisi" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const active = selectActiveVersion(data);
  const p = selectPending(data);

  if (!p) {
    return (
      <PanelFrame id="weight_proposal">
        <PanelHeader
          title="Ağırlık Önerisi"
          subtitle={`aktif v${active}`}
          actions={
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => runAction("propose")}
              className="rounded border border-accent-cyan/35 bg-accent-cyan/8 px-2 py-0.5 text-[10px] uppercase tracking-wide text-accent-cyan hover:bg-accent-cyan/14 disabled:opacity-40"
            >
              {busy === "propose" ? "Üretiliyor..." : "Öneri üret"}
            </button>
          }
        />
        <EmptyState />
        <p className="mt-2 text-[11px] text-white/40">
          Bekleyen owner-onaylı ağırlık önerisi yok.
        </p>
        {info ? (
          <p className="mt-2 rounded border border-amber-400/25 bg-amber-400/8 px-2 py-1 text-[11px] text-amber-100/80">
            {info}
          </p>
        ) : null}
        {error ? (
          <p className="mt-2 rounded border border-signal-down/30 bg-signal-down/5 px-2 py-1 text-[11px] text-signal-down/90">
            {error}
          </p>
        ) : null}
      </PanelFrame>
    );
  }

  const deltas = selectTopDeltas(p.deltas, 6);

  return (
    <PanelFrame id="weight_proposal">
      <PanelHeader
        title="Ağırlık Önerisi"
        subtitle={`aktif v${active} -> öneri v${p.to_version} - ${p.regime}`}
        actions={
          <>
            <span className="rounded px-1.5 py-0.5 bg-amber-400/20 text-amber-400 text-[10px] uppercase tracking-widest">
              pending
            </span>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => runAction("approve")}
              className="rounded border border-signal-up/40 bg-signal-up/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-signal-up hover:bg-signal-up/20 disabled:opacity-40"
            >
              {busy === "approve" ? "..." : "Onayla"}
            </button>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => runAction("reject")}
              className="rounded border border-white/15 bg-white/[0.03] px-2 py-0.5 text-[10px] uppercase tracking-wide text-white/65 hover:bg-white/10 disabled:opacity-40"
            >
              {busy === "reject" ? "..." : "Reddet"}
            </button>
          </>
        }
      />

      <div className="text-[11px] text-white/50 mb-2">
        {p.dataset_size} verified trade - {p.rejected_records} kayıt atlandı -{" "}
        {fmtRelative(p.generated_at)}
      </div>

      <ul className="space-y-1 text-xs">
        {deltas.map((d) => {
          const positive = d.delta > 0;
          return (
            <li
              key={d.module}
              className="flex items-center justify-between border-b border-white/5 pb-1"
            >
              <span className="font-medium uppercase tracking-wide">{d.module}</span>
              <span className="flex items-center gap-3 tabular-nums">
                <span className="text-white/50">{fmtNum(d.old, 3)}</span>
                <span className="text-white/30">-&gt;</span>
                <span className="text-white/80">{fmtNum(d.new, 3)}</span>
                <span
                  className={
                    positive
                      ? "text-signal-up"
                      : d.delta < 0
                        ? "text-signal-down"
                        : "text-white/40"
                  }
                >
                  {positive ? "+" : ""}
                  {fmtNum(d.delta, 3)}
                </span>
              </span>
            </li>
          );
        })}
      </ul>

      <p className="mt-2 text-[11px] text-white/40">{p.audit_note}</p>
      {error ? (
        <p className="mt-2 rounded border border-signal-down/30 bg-signal-down/5 px-2 py-1 text-[11px] text-signal-down/90">
          {error}
        </p>
      ) : null}
    </PanelFrame>
  );
}
