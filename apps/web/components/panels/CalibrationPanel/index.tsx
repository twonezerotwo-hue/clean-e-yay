"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { CalibrationGrid } from "@/components/charts/CalibrationGrid";
import { useCalibration } from "@/lib/queries/hooks";
import { qk } from "@/lib/queries/keys";
import { api } from "@/lib/api/client";
import { fmtNum, fmtRelative } from "@/lib/format";

const STATUS_TONE: Record<string, string> = {
  fitted: "bg-signal-up/20 text-signal-up",
  insufficient: "bg-amber-400/20 text-amber-400",
  identity: "bg-white/10 text-white/50",
};

/**
 * G6 — Confidence calibration paneli. Platt scaling (a, b) + reliability
 * bins. Owner-approval gerekmez; sadece bilgi/sizing. RiskGate bypass YOK.
 */
export function CalibrationPanel() {
  const { data, isLoading } = useCalibration();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);

  const retrain = async () => {
    setBusy(true);
    try {
      await api.calibrationRetrain();
      await qc.invalidateQueries({ queryKey: qk.calibration });
      await qc.invalidateQueries({ queryKey: qk.learningSummary });
    } finally {
      setBusy(false);
    }
  };

  if (isLoading) {
    return (
      <PanelFrame id="calibration">
        <PanelHeader title="Calibration" />
        <LoadingState />
      </PanelFrame>
    );
  }
  if (!data) {
    return (
      <PanelFrame id="calibration">
        <PanelHeader title="Calibration" />
        <EmptyState />
      </PanelFrame>
    );
  }
  const { params, min_required, samples_in_state, bins } = data;
  const enoughSamples = samples_in_state >= min_required;
  return (
    <PanelFrame id="calibration">
      <PanelHeader
        title="Calibration"
        subtitle={`Platt scaling · ${samples_in_state}/${min_required} örnek`}
        actions={
          <>
            <span
              className={`rounded px-1.5 py-0.5 uppercase tracking-widest text-[10px] ${
                STATUS_TONE[params.status] ?? STATUS_TONE.identity
              }`}
            >
              {params.status}
            </span>
            <button
              type="button"
              disabled={busy}
              onClick={retrain}
              className="rounded border border-white/15 bg-white/[0.03] px-2 py-0.5 text-[10px] uppercase tracking-wide text-white/65 hover:bg-white/10 disabled:opacity-40"
            >
              {busy ? "Fit..." : "Manuel fit"}
            </button>
          </>
        }
      />
      <div className="grid grid-cols-3 gap-2 text-xs mb-3">
        <div>
          <div className="text-white/40">a</div>
          <div className="tabular-nums">{fmtNum(params.a, 3)}</div>
        </div>
        <div>
          <div className="text-white/40">b</div>
          <div className="tabular-nums">{fmtNum(params.b, 3)}</div>
        </div>
        <div>
          <div className="text-white/40">son fit</div>
          <div>{fmtRelative(params.fitted_at)}</div>
        </div>
      </div>
      {enoughSamples && bins.length ? (
        <CalibrationGrid bins={bins} size={180} />
      ) : (
        <p className="text-[11px] text-white/50">
          Yetersiz veri — identity (a=1, b=0) kullanılıyor; ham confidence
          değişmiyor. RiskGate ve DQS politikası geçerli.
        </p>
      )}
    </PanelFrame>
  );
}
