"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useCalibrationJumps } from "@/lib/queries/hooks";
import type { CalibrationJumpsView, CalibrationJumpRow } from "@/types/generated/api";

// Calibration jump ledger (packages/learning/calibration_audit.py).
// Platt kalibrasyonunun ham consensus güvenini ne kadar şişirdiğini (raw→fitted)
// ve sürükleyen faktörleri (score/dominant/regime/tier/size) gösterir. Frontend
// hesap YAPMAZ; tüm değerler /api/v1/learning/calibration-jumps ViewModel'inden.
// "guardrail" otomatik kısma flag'i (calibration_guardrail.enabled).

function fmtPct(v: number | null | undefined): string {
  return v == null ? "—" : Math.round(v * 100).toString();
}

function deltaTone(v: number | null | undefined): string {
  if (v == null) return "text-white/55";
  if (v >= 0.30) return "text-signal-down"; // büyük şişme = dikkat
  if (v >= 0.15) return "text-amber-300";
  if (v < 0) return "text-signal-up"; // kalibrasyon kıstı
  return "text-white/70";
}

export function CalibrationJumpsPanel() {
  const { data, isLoading } = useCalibrationJumps();

  if (isLoading) {
    return (
      <PanelFrame id="calibration_jumps">
        <PanelHeader title="Güven Şişme Denetimi" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: CalibrationJumpsView | undefined = data;
  const guardOn = !!d?.guardrail?.enabled;
  const maxDelta = d?.guardrail?.max_inflation_delta ?? 0.25;
  const tiers = d?.by_tier ? Object.entries(d.by_tier) : [];
  const top: CalibrationJumpRow[] = d?.top_jumps ?? [];

  return (
    <PanelFrame id="calibration_jumps">
      <PanelHeader
        title="Güven Şişme Denetimi"
        subtitle="Güven ayarı tahmini ne kadar şişiriyor"
        actions={
          <span
            className={`rounded px-1.5 py-0.5 uppercase tracking-wide text-[10px] ${
              guardOn
                ? "bg-signal-up/20 text-signal-up"
                : "bg-white/10 text-white/55"
            }`}
          >
            {guardOn ? `AUTO-KIS ≤${Math.round(maxDelta * 100)}` : "GUARDRAIL KAPALI"}
          </span>
        }
      />
      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] text-white/55">
        {guardOn
          ? `Otomatik kısma açık: fitted - raw > ${Math.round(maxDelta * 100)}p ise kıstırılır (zayıf sinyal STRONG'a sıçrayamaz).`
          : "Gözlem modu. calibration_guardrail.enabled=true ile zayıf sinyalin aşırı şişmesi otomatik kısılır."}
      </p>

      <div className="grid grid-cols-4 gap-2 text-center">
        <div className="rounded border border-white/10 bg-white/[0.02] px-1 py-2">
          <div className="text-base font-semibold tabular-nums text-white/80">{d?.count ?? 0}</div>
          <div className="text-[9px] uppercase tracking-wide text-white/40">Kayıt</div>
        </div>
        <div className="rounded border border-white/10 bg-white/[0.02] px-1 py-2">
          <div className="text-base font-semibold tabular-nums text-white/80">{d?.fitted_count ?? 0}</div>
          <div className="text-[9px] uppercase tracking-wide text-white/40">Fitted</div>
        </div>
        <div className="rounded border border-amber-300/20 bg-amber-300/5 px-1 py-2">
          <div className={`text-base font-semibold tabular-nums ${deltaTone(d?.avg_inflation_delta)}`}>
            {d?.avg_inflation_delta != null ? `+${fmtPct(d.avg_inflation_delta)}` : "—"}
          </div>
          <div className="text-[9px] uppercase tracking-wide text-white/40">Ort. şişme</div>
        </div>
        <div className="rounded border border-signal-down/20 bg-signal-down/5 px-1 py-2">
          <div className={`text-base font-semibold tabular-nums ${deltaTone(d?.max_inflation_delta)}`}>
            {d?.max_inflation_delta != null ? `+${fmtPct(d.max_inflation_delta)}` : "—"}
          </div>
          <div className="text-[9px] uppercase tracking-wide text-white/40">Max şişme</div>
        </div>
      </div>

      {tiers.length ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {tiers.map(([tier, n]) => (
            <span
              key={tier}
              className="rounded border border-white/10 bg-white/[0.03] px-1.5 py-0.5 text-[10px] tabular-nums text-white/60"
            >
              {tier}: <span className="text-white/85">{n}</span>
            </span>
          ))}
          {d?.capped_count ? (
            <span className="rounded border border-signal-up/25 bg-signal-up/10 px-1.5 py-0.5 text-[10px] tabular-nums text-signal-up">
              kısılan: {d.capped_count}
            </span>
          ) : null}
        </div>
      ) : null}

      <div className="mt-3 text-[10px] uppercase tracking-widest text-white/35">
        En büyük şişmeler
      </div>
      {top.length ? (
        <div className="mt-1 overflow-x-auto">
          <table className="w-full min-w-[20rem] border-collapse text-xs">
            <thead>
              <tr className="text-[10px] uppercase tracking-widest text-white/40">
                <th className="p-1 text-left font-normal">Sembol</th>
                <th className="p-1 font-normal">Ham→Fit</th>
                <th className="p-1 font-normal">Şişme</th>
                <th className="p-1 text-left font-normal">Baskın</th>
                <th className="p-1 font-normal">Kademe</th>
                <th className="p-1 font-normal text-right">Boyut</th>
              </tr>
            </thead>
            <tbody>
              {top.map((r, i) => (
                <tr key={`${r.position_id ?? r.symbol}-${i}`} className="border-t border-white/5">
                  <td className="p-1">
                    <span className="font-medium">{r.symbol ?? "—"}</span>{" "}
                    <span className="text-white/40">{r.timeframe ?? ""}</span>
                  </td>
                  <td className="p-1 text-center tabular-nums text-white/65">
                    {fmtPct(r.raw_confidence)}→{fmtPct(r.fitted_confidence)}
                  </td>
                  <td className={`p-1 text-center tabular-nums font-semibold ${deltaTone(r.inflation_delta)}`}>
                    {r.inflation_delta != null ? `+${fmtPct(r.inflation_delta)}` : "—"}
                  </td>
                  <td className="p-1 text-left text-white/55">{r.dominant_module ?? "—"}</td>
                  <td className="p-1 text-center text-[10px] uppercase tracking-wide text-white/60">
                    {r.tier ?? "—"}
                  </td>
                  <td className="p-1 text-right tabular-nums text-white/65">
                    {r.size_usd != null ? `$${Math.round(r.size_usd).toLocaleString()}` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="mt-1 text-[11px] text-white/35">
          Henüz kayıt yok — yeni bir pozisyon açıldığında sıçrama buraya işlenir.
        </div>
      )}
    </PanelFrame>
  );
}
