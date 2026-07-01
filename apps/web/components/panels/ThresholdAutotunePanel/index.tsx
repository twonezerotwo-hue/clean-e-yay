"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useThresholdAutotune } from "@/lib/queries/hooks";
import type { ThresholdAutotuneView } from "@/types/generated/api";

// CP4 (final) — otonom eşik trainer paneli. Allowlist eşiklerini (tp_rr_ratio,
// bias_cuts, adx_trend_min) backtest-doğrulamalı + edge-gate'li + rollback'li
// dar-bantta OTOMATİK ayarlar. Flag THRESHOLD_AUTOTUNE OFF iken bayt-aynı (hiçbir
// eşik uygulanmaz). Frontend hesap YAPMAZ; tüm durum /learning/threshold-autotune'dan.

export function ThresholdAutotunePanel() {
  const { data, isLoading } = useThresholdAutotune();

  if (isLoading) {
    return (
      <PanelFrame id="threshold_autotune">
        <PanelHeader title="Eşik Otomatik Ayarı" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: ThresholdAutotuneView | undefined = data;
  const enabled = !!d?.enabled;
  const safe = !!d?.safe_to_autotune;
  const overrides = Object.entries(d?.active_overrides ?? {});
  const mon = d?.monitor;
  const history = d?.history ?? [];

  // Durum: flag kapalı → KAPALI; açık ama edge stabil değil → KİLİTLİ; açık+güvenli → AKTİF.
  const status = !enabled
    ? { label: "KAPALI", chip: "bg-white/10 text-white/55" }
    : safe
      ? { label: "AKTİF", chip: "bg-signal-up/20 text-signal-up" }
      : { label: "EDGE KİLİTLİ", chip: "bg-amber-400/15 text-amber-300/90" };

  return (
    <PanelFrame id="threshold_autotune">
      <PanelHeader
        title="Eşik Otomatik Ayarı"
        subtitle="Sinyal/geometri eşiklerini geçmiş işlemlerden öğrenip otomatik ayarlar"
        actions={
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${status.chip}`}>
            {status.label}
          </span>
        }
      />
      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] leading-5 text-white/55">
        İzin verilen eşikleri (tp_rr_ratio, bias_cuts, adx) <strong className="text-white/75">backtest ile
        doğrular</strong>, edge stabilse dar-bantta otomatik uygular, sonuç kötüleşirse geri alır (rollback).
        Flag kapalıyken hiçbir eşik değişmez.
      </p>

      {/* İki kapı: flag (owner) + edge (güvenlik) */}
      <div className="mb-2 flex gap-1.5">
        <div className={`flex-1 rounded border px-2 py-1 text-[10px] ${
          enabled ? "border-signal-up/25 bg-signal-up/5 text-signal-up" : "border-white/10 bg-white/[0.02] text-white/45"
        }`}>
          Flag: <span className="font-semibold">{enabled ? "AÇIK" : "KAPALI"}</span>
          <div className="text-[9px] text-white/35">THRESHOLD_AUTOTUNE</div>
        </div>
        <div className={`flex-1 rounded border px-2 py-1 text-[10px] ${
          safe ? "border-signal-up/25 bg-signal-up/5 text-signal-up" : "border-amber-400/25 bg-amber-400/5 text-amber-300/90"
        }`}>
          Edge kapısı: <span className="font-semibold">{safe ? "GÜVENLİ" : "KİLİTLİ"}</span>
          <div className="text-[9px] text-white/35">safe_to_autotune</div>
        </div>
      </div>

      {/* Ayarlanabilir eşikler (allowlist) */}
      <div className="mb-2">
        <div className="mb-1 text-[10px] uppercase tracking-wide text-white/35">
          Ayarlanabilir eşikler ({d?.tunable?.length ?? 0})
        </div>
        <div className="flex flex-wrap gap-1">
          {(d?.tunable ?? []).map((p) => {
            const ov = d?.active_overrides?.[p];
            return (
              <span
                key={p}
                className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${
                  ov ? "border-signal-up/30 bg-signal-up/10 text-signal-up" : "border-white/10 bg-black/20 text-white/55"
                }`}
                title={ov ? `override: ${ov.prev} → ${ov.value}` : "override yok"}
              >
                {p}
                {ov ? ` → ${ov.value}` : ""}
              </span>
            );
          })}
        </div>
      </div>

      {/* İzlenen aktif apply (rollback bekliyor) */}
      {mon ? (
        <div className="mb-2 rounded border border-signal-up/25 bg-signal-up/5 px-2 py-1 text-[11px]">
          <div className="flex justify-between">
            <span className="font-mono text-white/80">{mon.path}</span>
            <span className="text-[10px] uppercase tracking-wide text-signal-up">{mon.status ?? "MONITORING"}</span>
          </div>
          <div className="mt-0.5 text-[10px] text-white/50">
            {mon.from} → {mon.to}
            {mon.backtest_gain != null ? ` · backtest kazanç +${mon.backtest_gain}` : ""}
            {mon.baseline_expectancy != null ? ` · baseline beklenti ${mon.baseline_expectancy}` : ""}
          </div>
        </div>
      ) : (
        <div className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[10px] text-white/45">
          İzlenen aktif eşik-uygulaması yok.
          {overrides.length === 0 ? " Aktif override de yok — tüm eşikler config-varsayılanında." : ""}
        </div>
      )}

      {/* Geçmiş (son uygula/rollback) */}
      {history.length ? (
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wide text-white/35">Geçmiş</div>
          <div className="flex flex-col gap-1">
            {history.slice(0, 5).map((h, i) => {
              const rolled = h.event === "ROLLED_BACK" || h.status === "ROLLED_BACK";
              return (
                <div key={i} className="flex items-center justify-between rounded border border-white/10 bg-black/20 px-2 py-1 text-[10px]">
                  <span className="font-mono text-white/70">{h.path}</span>
                  <span className="text-white/45">{h.from} → {h.to}</span>
                  <span className={`uppercase tracking-wide ${rolled ? "text-signal-down" : "text-signal-up"}`}>
                    {h.event ?? h.status ?? "—"}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </PanelFrame>
  );
}
