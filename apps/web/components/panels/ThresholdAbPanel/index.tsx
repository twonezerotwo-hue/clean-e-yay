"use client";

import { useEffect, useState } from "react";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { useThresholdAb, useThresholdAutotune } from "@/lib/queries/hooks";
import type { ThresholdAbRun, ThresholdAbView } from "@/types/generated/api";

// CP4 — eşik A/B kâşifi (interaktif). Bir eşiğin farklı değerlerini MEVCUT backtest
// motoruyla geçmiş barlarda dener + baseline ile karşılaştırır (threshold_ab.sweep).
// Observe-only: override yalnız backtest scope'unda enjekte edilir; canlı config +
// karar zinciri DEĞİŞMEZ. Otonom trainer'ın (ThresholdAutotunePanel) elle çalıştırılan
// hâli — "bu eşik tarihsel olarak daha iyi mi" sorusunu güvenle yanıtlar.

const SYMBOLS = ["BTCUSD", "ETHUSD", "XAUUSD", "XAGUSD", "BRENT"];
const TIMEFRAMES = ["15m", "1h", "4h", "1d"];
const DEFAULT_VALUES = "1.5,2.0,2.5,3.0";

function pct(v: number | null | undefined): string {
  return v == null ? "—" : `%${(v * 100).toFixed(2)}`;
}

export function ThresholdAbPanel() {
  const { data: autotune } = useThresholdAutotune();
  const tunable = autotune?.tunable ?? [];

  const [paramPath, setParamPath] = useState("");
  const [values, setValues] = useState(DEFAULT_VALUES);
  const [symbol, setSymbol] = useState("BTCUSD");
  const [timeframe, setTimeframe] = useState("1d");
  const [submitted, setSubmitted] = useState(false);

  // İlk tunable geldiğinde seçili param'ı doldur (henüz seçilmemişse).
  useEffect(() => {
    if (!paramPath && tunable.length) setParamPath(tunable[0]);
  }, [tunable, paramPath]);

  const { data, isFetching, isError } = useThresholdAb(
    paramPath,
    values,
    symbol,
    timeframe,
    submitted,
  );
  const d: ThresholdAbView | undefined = data;
  const recValue = d?.recommendation?.value;

  return (
    <PanelFrame id="threshold_ab">
      <PanelHeader
        title="Eşik A/B Kâşifi"
        subtitle="Bir eşiğin farklı değerlerini geçmiş işlemlerde dener, en iyisini önerir"
        actions={
          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white/55">
            on-demand
          </span>
        }
      />
      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] leading-5 text-white/55">
        Eşik değeri backtest scope'unda denenir — <strong className="text-white/75">canlı config değişmez</strong>.
        Otonom trainer'ın elle çalıştırılan hâli.
      </p>

      {/* Form */}
      <div className="mb-2 grid grid-cols-2 gap-1.5">
        <label className="col-span-2 flex flex-col gap-0.5 text-[10px] uppercase tracking-wide text-white/35">
          Eşik
          <select
            value={paramPath}
            onChange={(e) => setParamPath(e.target.value)}
            className="rounded border border-white/10 bg-black/30 px-1.5 py-1 font-mono text-[11px] text-white/80"
          >
            {tunable.length === 0 ? <option value="">yükleniyor…</option> : null}
            {tunable.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label className="col-span-2 flex flex-col gap-0.5 text-[10px] uppercase tracking-wide text-white/35">
          Değerler (virgülle)
          <input
            value={values}
            onChange={(e) => setValues(e.target.value)}
            placeholder="1.5,2.0,2.5"
            className="rounded border border-white/10 bg-black/30 px-1.5 py-1 font-mono text-[11px] text-white/80"
          />
        </label>
        <label className="flex flex-col gap-0.5 text-[10px] uppercase tracking-wide text-white/35">
          Sembol
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="rounded border border-white/10 bg-black/30 px-1.5 py-1 text-[11px] text-white/80"
          >
            {SYMBOLS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-0.5 text-[10px] uppercase tracking-wide text-white/35">
          Zaman dilimi
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="rounded border border-white/10 bg-black/30 px-1.5 py-1 text-[11px] text-white/80"
          >
            {TIMEFRAMES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
      </div>
      <button
        type="button"
        onClick={() => setSubmitted(true)}
        disabled={!paramPath || !values.trim() || isFetching}
        className="mb-2 w-full rounded border border-white/15 bg-white/5 px-2 py-1 text-[11px] font-medium text-white/80 transition hover:bg-white/10 disabled:opacity-40"
      >
        {isFetching ? "Backtest çalışıyor…" : "Çalıştır"}
      </button>

      {/* Sonuçlar */}
      {isError ? (
        <div className="rounded border border-signal-down/25 bg-signal-down/5 px-2 py-1 text-[11px] text-signal-down">
          Backtest çalıştırılamadı — parametreleri kontrol et.
        </div>
      ) : d?.error ? (
        <div className="rounded border border-amber-400/25 bg-amber-400/5 px-2 py-1 text-[11px] text-amber-300/90">
          {d.error}
        </div>
      ) : d ? (
        <div>
          <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wide text-white/35">
            <span>{d.symbol ?? d.symbols?.join("+")} · {d.timeframe}</span>
            {recValue != null ? (
              <span className="text-signal-up">öneri: {recValue}</span>
            ) : (
              <span className="text-white/40">baseline en iyi</span>
            )}
          </div>
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-[9px] uppercase tracking-wide text-white/35">
                <th className="py-0.5 text-left font-medium">Değer</th>
                <th className="py-0.5 text-right font-medium">İşlem</th>
                <th className="py-0.5 text-right font-medium">Win</th>
                <th className="py-0.5 text-right font-medium">Ort. getiri</th>
                <th className="py-0.5 text-right font-medium">PF</th>
              </tr>
            </thead>
            <tbody>
              <Row
                label={`${d.baseline_value ?? "?"} (baseline)`}
                m={d.baseline}
                muted
              />
              {(d.runs ?? []).map((r) => (
                <Row
                  key={r.value}
                  label={String(r.value)}
                  m={r}
                  highlight={r.value === recValue}
                />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/45">
          Bir eşik + değerler seç, <strong className="text-white/70">Çalıştır</strong>'a bas.
        </div>
      )}
    </PanelFrame>
  );
}

function Row({
  label,
  m,
  muted,
  highlight,
}: {
  label: string;
  m: ThresholdAbRun | ThresholdAbView["baseline"];
  muted?: boolean;
  highlight?: boolean;
}) {
  return (
    <tr
      className={`border-t border-white/5 ${
        highlight ? "bg-signal-up/10" : ""
      } ${muted ? "text-white/45" : "text-white/75"}`}
    >
      <td className="py-0.5 font-mono">{label}</td>
      <td className="py-0.5 text-right tabular-nums">{m.total_trades ?? "—"}</td>
      <td className="py-0.5 text-right tabular-nums">
        {m.win_rate == null ? "—" : `%${Math.round(m.win_rate * 100)}`}
      </td>
      <td className={`py-0.5 text-right tabular-nums ${
        (m.avg_return_pct ?? 0) > 0 ? "text-signal-up" : (m.avg_return_pct ?? 0) < 0 ? "text-signal-down" : ""
      }`}>
        {pct(m.avg_return_pct)}
      </td>
      <td className="py-0.5 text-right tabular-nums">{m.profit_factor ?? "—"}</td>
    </tr>
  );
}
