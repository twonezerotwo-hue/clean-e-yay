"use client";

import { useState } from "react";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useTfTargets } from "@/lib/queries/hooks";
import { qk } from "@/lib/queries/keys";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { TfTargetParams, TfTargetsView } from "@/types/generated/api";

// Faz B — TF-aware SL/TP öğrenmesi (packages/learning/tf_target_*.py).
// Backend her trainer döngüsünde TF başına nudge önerir; ±15% bant içi otomatik
// uygulanır, dışı owner onayına düşer. Frontend hesap YAPMAZ; tüm değerler
// /api/v1/learning/tf-targets ViewModel'inden gelir (DASHBOARD_RULES).

const TFS = ["15m", "1h", "4h", "1d"] as const;
const PARAM_LABEL: Record<string, string> = {
  sl_atr_mult: "SL × ATR",
  rr: "R:R",
  sl_pct_floor: "SL %taban",
  sl_pct_cap: "SL %tavan",
};

function formatParam(key: string, value: number): string {
  if (key === "sl_pct_floor" || key === "sl_pct_cap") {
    return `${(value * 100).toFixed(2)}%`;
  }
  return value.toFixed(2);
}

function ParamRow({ tf, params }: { tf: string; params: TfTargetParams | undefined }) {
  if (!params) return null;
  return (
    <tr className="border-t border-white/5">
      <td className="p-1 font-medium uppercase tracking-wide text-[11px]">{tf}</td>
      <td className="p-1 text-center tabular-nums">{formatParam("sl_atr_mult", params.sl_atr_mult)}</td>
      <td className="p-1 text-center tabular-nums">{formatParam("rr", params.rr)}</td>
      <td className="p-1 text-center tabular-nums">{formatParam("sl_pct_floor", params.sl_pct_floor)}</td>
      <td className="p-1 text-center tabular-nums">{formatParam("sl_pct_cap", params.sl_pct_cap)}</td>
    </tr>
  );
}

export function TfTargetsPanel() {
  const { data, isLoading } = useTfTargets();
  const qc = useQueryClient();
  const [busy, setBusy] = useState<"approve" | "reject" | "retrain" | null>(null);

  if (isLoading) {
    return (
      <PanelFrame id="tf_targets">
        <PanelHeader title="Kâr/Zarar Hedefi Öğrenmesi" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const d: TfTargetsView | undefined = data;
  const enabled = !!d?.enabled;
  const bandPct = Math.round((d?.auto_apply_band_pct ?? 0) * 100);
  const pendingRec = d?.pending as
    | { decisions?: Record<string, string>; pending_changes?: Record<string, TfTargetParams>; nudges?: Array<Record<string, unknown>> }
    | null
    | undefined;
  const pendingTfs = pendingRec?.pending_changes ? Object.keys(pendingRec.pending_changes) : [];

  const runAction = async (kind: "approve" | "reject" | "retrain") => {
    setBusy(kind);
    try {
      if (kind === "approve") await api.tfTargetsApprove();
      else if (kind === "reject") await api.tfTargetsReject();
      else await api.tfTargetsRetrain();
      await qc.invalidateQueries({ queryKey: qk.tfTargets });
    } finally {
      setBusy(null);
    }
  };

  return (
    <PanelFrame id="tf_targets">
      <PanelHeader
        title="Kâr/Zarar Hedefi Öğrenmesi"
        subtitle="Stop ve hedef seviyelerini geçmiş işlemlerden öğrenir"
        actions={
          <span
            className={`rounded px-1.5 py-0.5 uppercase tracking-wide text-[10px] ${
              enabled
                ? "bg-signal-up/20 text-signal-up"
                : "bg-white/10 text-white/55"
            }`}
          >
            {enabled ? "AKTİF" : "SHADOW"}
          </span>
        }
      />
      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] text-white/55">
        {enabled
          ? "Live açılışlar bu geometriyle SL/TP koyuyor."
          : "Faz A — shadow mode: motor hesaplıyor, log birikiyor; canlı SL/TP hâlâ sabit-%. Aktivasyon ayrı onayla."}{" "}
        Trainer ±{bandPct}% bant içi nudge'u otomatik uygular; dışı owner onayı bekler.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[20rem] border-collapse text-xs">
          <thead>
            <tr className="text-[10px] uppercase tracking-widest text-white/40">
              <th className="p-1 text-left font-normal">TF</th>
              <th className="p-1 font-normal">{PARAM_LABEL.sl_atr_mult}</th>
              <th className="p-1 font-normal">{PARAM_LABEL.rr}</th>
              <th className="p-1 font-normal">{PARAM_LABEL.sl_pct_floor}</th>
              <th className="p-1 font-normal">{PARAM_LABEL.sl_pct_cap}</th>
            </tr>
          </thead>
          <tbody>
            {TFS.map((tf) => (
              <ParamRow key={tf} tf={tf} params={d?.effective[tf]} />
            ))}
          </tbody>
        </table>
      </div>

      {pendingTfs.length ? (
        <div className="mt-3 rounded border border-amber-400/30 bg-amber-400/5 px-2 py-1.5">
          <div className="mb-1 text-[10px] uppercase tracking-widest text-amber-300/80">
            Bekleyen değişiklik (owner onayı)
          </div>
          <ul className="space-y-0.5 text-[11px] tabular-nums text-white/70">
            {pendingTfs.map((tf) => (
              <li key={tf}>
                <span className="uppercase">{tf}</span>:{" "}
                <span className="text-white/55">
                  {Object.entries(pendingRec?.pending_changes?.[tf] ?? {})
                    .map(([k, v]) => `${PARAM_LABEL[k] ?? k}=${formatParam(k, v)}`)
                    .join(" · ")}
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => runAction("approve")}
              className="rounded border border-signal-up/40 bg-signal-up/10 px-2 py-0.5 text-[11px] text-signal-up hover:bg-signal-up/20 disabled:opacity-40"
            >
              Onayla
            </button>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => runAction("reject")}
              className="rounded border border-white/15 bg-white/[0.03] px-2 py-0.5 text-[11px] text-white/70 hover:bg-white/10 disabled:opacity-40"
            >
              Reddet
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-3 text-[10px] text-white/40">
          Bekleyen değişiklik yok — trainer ±{bandPct}% içi nudge'ları otomatik uyguluyor.
        </div>
      )}

      <div className="mt-3 flex items-center justify-between text-[10px] text-white/35">
        <span>
          Mutlak güvenlik: SL × ATR ∈ [{d?.guardrail.sl_atr_mult?.min}, {d?.guardrail.sl_atr_mult?.max}], R:R ∈ [
          {d?.guardrail.rr?.min}, {d?.guardrail.rr?.max}]
        </span>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => runAction("retrain")}
          className="rounded border border-white/15 bg-white/[0.03] px-1.5 py-0.5 text-[10px] text-white/60 hover:bg-white/10 disabled:opacity-40"
        >
          {busy === "retrain" ? "Çalışıyor…" : "Manuel öğret"}
        </button>
      </div>
    </PanelFrame>
  );
}
