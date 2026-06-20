"use client";

/**
 * Multi-TF Matrix — semboller × timeframe grid.
 *
 * Her hücre seçili sembol & TF için bias (B/N/A) renkli kutu. Sağda global
 * karar; altta tek cümle yorum. Backend dokunulmadan technicals_by_tf
 * score'undan türetir (score≥60 bullish, score≤40 bearish).
 */
import type { Timeframe } from "@/types/generated/api";

import type { HoloSignal } from "./holo-adapter";

const TFS: Timeframe[] = ["15m", "1h", "4h", "1d", "1w"];

type Bias = "bullish" | "bearish" | "neutral" | "missing";

function biasFromScore(score: number | undefined): Bias {
  if (score === undefined || score === null) return "missing";
  if (score >= 60) return "bullish";
  if (score <= 40) return "bearish";
  return "neutral";
}

function biasGlyph(b: Bias): string {
  if (b === "bullish") return "▲";
  if (b === "bearish") return "▼";
  if (b === "neutral") return "N";
  return "—";
}

function biasCellCls(b: Bias): string {
  if (b === "bullish") return "bg-emerald-900/30 text-emerald-300 border-emerald-700/40";
  if (b === "bearish") return "bg-red-900/30 text-red-300 border-red-700/40";
  if (b === "neutral") return "bg-slate-800/30 text-slate-400 border-slate-700/40";
  return "bg-black/30 text-slate-600 border-slate-800/40";
}

function actionLabel(a: string): string {
  if (a === "LONG")        return "Long";
  if (a === "LONG_AWAIT")  return "Long Setup";
  if (a === "SHORT")       return "Short";
  if (a === "SHORT_AWAIT") return "Short Setup";
  if (a === "AVOID")       return "Kaçın";
  return "Bekle";
}

function actionTone(a: string): string {
  if (a === "LONG")        return "text-emerald-300";
  if (a === "SHORT")       return "text-red-300";
  if (a === "AVOID")       return "text-red-400";
  if (a === "LONG_AWAIT" || a === "SHORT_AWAIT") return "text-amber-300";
  return "text-slate-400";
}

interface Props {
  signals: HoloSignal[];
}

export default function MultiTfMatrix({ signals }: Props) {
  // Sıralı: ana 4 sembol önce
  const order = ["BTCUSD", "ETHUSD", "XAUUSD", "XAGUSD"];
  const ordered = order
    .map((c) => signals.find((s) => s.asset_code === c))
    .filter((s): s is HoloSignal => !!s);
  if (ordered.length === 0) return null;

  // Yorum: tüm semboller tüm TF'lerde nötr mü? En güçlü aday?
  let totalNonNeutral = 0;
  let topSignal: HoloSignal | null = null;
  let topScore = -1;
  for (const s of ordered) {
    if (s.consensus_score > topScore) {
      topScore = s.consensus_score;
      topSignal = s;
    }
    for (const tf of TFS) {
      const b = biasFromScore(s.technicals[tf]?.score);
      if (b === "bullish" || b === "bearish") totalNonNeutral++;
    }
  }
  const interpretation =
    totalNonNeutral === 0
      ? `Tüm semboller tüm timeframe'lerde nötr — net yön sinyali yok.${
          topSignal ? ` En güçlü aday: ${topSignal.asset_code} (consensus ${topSignal.consensus_score.toFixed(0)}/100).` : ""
        }`
      : `${totalNonNeutral} hücrede yön baskınlığı var — yeşil/kırmızı bölgelere bak.${
          topSignal ? ` En güçlü aday: ${topSignal.asset_code} (consensus ${topSignal.consensus_score.toFixed(0)}/100).` : ""
        }`;

  return (
    <div className="px-4 py-3 bg-slate-900/20">
      <div className="flex items-baseline justify-between mb-2">
        <p className="text-[10px] font-medium uppercase tracking-[0.18em] text-slate-400">
          Timeframe Matrisi
        </p>
        <p className="text-[9px] text-slate-500">
          {ordered.length} sembol × {TFS.length} TF · skordan türetildi
        </p>
      </div>

      <div className="rounded-md border border-slate-700/40 bg-black/30 overflow-hidden">
        <table className="w-full text-[11px]">
          <thead className="bg-white/[0.02] text-slate-500">
            <tr>
              <th className="text-left px-3 py-1.5 font-medium">Sembol</th>
              {TFS.map((tf) => (
                <th key={tf} className="text-center px-2 py-1.5 font-medium font-mono">
                  {tf}
                </th>
              ))}
              <th className="text-right px-3 py-1.5 font-medium">Karar</th>
            </tr>
          </thead>
          <tbody>
            {ordered.map((s) => {
              const actionRaw = s.asset_action ?? "";
              return (
                <tr key={s.asset_code} className="border-t border-white/5">
                  <td className="px-3 py-1.5 font-medium text-slate-200">
                    {s.asset_code}
                  </td>
                  {TFS.map((tf) => {
                    const b = biasFromScore(s.technicals[tf]?.score);
                    return (
                      <td key={tf} className="px-2 py-1.5">
                        <span
                          className={`inline-flex items-center justify-center w-7 h-6 rounded border text-[11px] font-mono font-semibold ${biasCellCls(b)}`}
                          title={`${tf}: ${b}`}
                        >
                          {biasGlyph(b)}
                        </span>
                      </td>
                    );
                  })}
                  <td className={`px-3 py-1.5 text-right font-medium ${actionTone(actionRaw)}`}>
                    {actionLabel(actionRaw)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-2 flex items-baseline justify-between text-[10px]">
        <span className="text-slate-500">
          <span className="inline-block w-2 h-2 rounded-sm bg-emerald-700/60 mr-1" />Bullish ·
          <span className="inline-block w-2 h-2 rounded-sm bg-red-700/60 mx-1" />Bearish ·
          <span className="inline-block w-2 h-2 rounded-sm bg-slate-700/60 mx-1" />Nötr
        </span>
      </div>

      <p className="mt-2 text-[11px] text-slate-300 leading-snug">
        → {interpretation}
      </p>
    </div>
  );
}
