"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useSubsignalScorecard } from "@/lib/queries/hooks";
import type { SubsignalRow, SubsignalScorecardView } from "@/types/uncontracted";

// D5 — Sinyal Karnesi (v2 sert cetvel). Hangi sinyal hangi zaman diliminde
// GERÇEKTEN kanıtlı: bindirmesiz örneklem + TF-adil oran + taban çizgisi +
// iki-yarı kararlılık. Frontend HESAP YAPMAZ; tüm sayılar worker artifact'ından
// (/learning/subsignal-scorecard). Bar arşivi büyüdükçe karne haftalık tazelenir.

const VERDICT: Record<string, { label: string; chip: string }> = {
  EDGE: { label: "KANITLI", chip: "bg-signal-up/20 text-signal-up" },
  INVERSE: { label: "TERS", chip: "bg-signal-down/20 text-signal-down" },
  FLAT: { label: "NÖTR", chip: "bg-white/10 text-white/55" },
  INSUFFICIENT: { label: "YETERSİZ", chip: "bg-white/5 text-white/35" },
};

// Sinyal adları — panelde düz dil (owner kuralı: jargon değil).
const SIGNAL_TR: Record<string, string> = {
  trend: "Trend (EMA)",
  rsi: "RSI eğimi",
  macd: "MACD",
  structure: "Tepe/dip yapısı",
  rsi_extreme: "RSI aşırılık dönüşü",
  vwap_fade: "VWAP sapması",
  bollinger_fade: "Bollinger dokunuşu",
  candle_rejection: "Mum formasyonu",
};

const TF_ORDER = ["15m", "1h", "4h", "1d"];

function SignalChip({ name, row }: { name: string; row: SubsignalRow }) {
  const v = VERDICT[row.verdict] ?? VERDICT.INSUFFICIENT;
  // Eski (v1) artifact'ta v2 alanları olmayabilir — panel çökmez, 0 gösterir;
  // worker bir sonraki koşuda v2 ile yeniden üretir (engine kontrolü).
  const ratio = row.edge_ratio ?? 0;
  return (
    <div
      className="flex items-center justify-between gap-2 rounded border border-white/10 bg-black/20 px-2 py-1"
      title={`n=${row.n} · edge %${row.edge_pct} · oran ${ratio} · isabet %${Math.round(
        (row.hit_rate ?? 0) * 100,
      )} · yarılar ${row.edge_first_half ?? "—"}/${row.edge_second_half ?? "—"} · ${
        row.stable ? "kararlı" : "kararsız"
      } · taban ${row.beats_baseline ? "geçildi" : "geçilemedi"}`}
    >
      <span className="truncate text-[11px] text-white/70">{SIGNAL_TR[name] ?? name}</span>
      <span className="flex items-center gap-1.5">
        <span className="font-mono text-[10px] tabular-nums text-white/45">
          {ratio > 0 ? "+" : ""}
          {ratio.toFixed(2)}
        </span>
        <span className={`rounded px-1 py-0.5 text-[9px] font-bold uppercase tracking-wide ${v.chip}`}>
          {v.label}
        </span>
      </span>
    </div>
  );
}

export function SubsignalScorecardPanel() {
  const { data, isLoading } = useSubsignalScorecard();

  if (isLoading) {
    return (
      <PanelFrame id="subsignal_scorecard">
        <PanelHeader title="Sinyal Karnesi" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: SubsignalScorecardView | undefined = data;
  const perTf = d?.per_timeframe ?? {};
  const hasData = d?.status === "OK" && Object.keys(perTf).length > 0;

  return (
    <PanelFrame id="subsignal_scorecard">
      <PanelHeader
        title="Sinyal Karnesi"
        subtitle="Hangi sinyal hangi zaman diliminde kanıtlı"
        actions={
          d?.generated_at ? (
            <span className="text-[10px] uppercase tracking-wide text-white/35">
              {new Date(d.generated_at).toLocaleDateString("tr-TR")}
            </span>
          ) : undefined
        }
      />
      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] leading-5 text-white/55">
        Her sinyal her zaman diliminde ayrı ölçülür. <strong className="text-white/75">KANITLI</strong> damgası üç
        şart ister: yeterli örnek + &quot;hep aynı yöne oyna&quot; taban çizgisini geçmek + iki ayrı dönemde tutarlılık.
        Veri arşivi büyüdükçe karne haftalık tazelenir.
      </p>

      {hasData ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {TF_ORDER.filter((tf) => perTf[tf]).map((tf) => {
            const block = perTf[tf];
            const rows = Object.entries(block.signals).sort(
              (a, b) => (b[1].edge_ratio ?? 0) - (a[1].edge_ratio ?? 0),
            );
            return (
              <div key={tf} className="rounded border border-white/10 bg-white/[0.02] p-2">
                <div className="mb-1.5 flex items-baseline justify-between">
                  <span className="font-mono text-xs font-semibold text-white/85">{tf}</span>
                  <span className="text-[10px] text-white/35">
                    {block.points} örnek · tipik hareket %{block.typical_move_pct}
                  </span>
                </div>
                <div className="flex flex-col gap-1">
                  {rows.map(([name, row]) => (
                    <SignalChip key={name} name={name} row={row} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Karne henüz üretilmedi{d?.enabled === false ? " (adım kapalı)" : ""}. Öğrenme motoru haftada bir üretir;
          ilk koşumdan sonra burada görünür.
        </div>
      )}
    </PanelFrame>
  );
}
