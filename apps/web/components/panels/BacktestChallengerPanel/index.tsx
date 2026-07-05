"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useBacktestChallenger } from "@/lib/queries/hooks";
import type {
  BacktestChallengerView,
  ChallengerQuantumRow,
  ChallengerWeightRow,
} from "@/types/generated/api";

// B serisi — Backtest Challenger kanıt paneli. Geçmiş backtest'ten türeyen
// quantum ayrım karnesi (hangi sinyal hangi rejimde işe yarıyor) + aday ağırlık
// önerileri + terfi (B-4) durumu. İZOLE/shadow — canlı ağırlık/paper/karara
// dokunmaz. Frontend HESAP YAPMAZ; sayılar /learning/backtest-challenger'dan.

const VERDICT_LABEL: Record<string, string> = {
  DISCRIMINATES: "ayırt ediyor",
  INVERSE: "ters çalışıyor",
  FLAT: "farketmiyor",
  NO_SPLIT: "tek yönlü",
  INSUFFICIENT: "veri az",
};

function verdictClass(v: string): string {
  if (v === "DISCRIMINATES") return "bg-signal-up/20 text-signal-up";
  if (v === "INVERSE") return "bg-signal-down/20 text-signal-down";
  return "bg-white/10 text-white/40";
}

function num(v: number | null | undefined, digits = 4): string {
  return v === null || v === undefined ? "—" : v.toFixed(digits);
}

function QuantumRow({ q }: { q: ChallengerQuantumRow }) {
  return (
    <tr className="border-t border-white/5">
      <td className="py-0.5 pr-2 font-mono font-bold text-white/80">{q.regime}</td>
      <td className="py-0.5 pr-2">
        <span
          className={`rounded px-1 py-0.5 text-[9px] font-bold uppercase ${verdictClass(q.verdict)}`}
        >
          {VERDICT_LABEL[q.verdict] ?? q.verdict}
        </span>
      </td>
      <td
        className={`py-0.5 pr-2 text-right font-mono ${
          q.separation === null || q.separation === undefined
            ? "text-white/40"
            : q.separation >= 0
              ? "text-signal-up/80"
              : "text-signal-down/80"
        }`}
      >
        {q.separation === null || q.separation === undefined
          ? "—"
          : `${q.separation >= 0 ? "+" : ""}${num(q.separation)}`}
      </td>
      <td className="py-0.5 pr-2 text-right font-mono text-white/60">{num(q.correlation)}</td>
      <td className="py-0.5 text-right font-mono text-white/50">{q.n ?? "—"}</td>
    </tr>
  );
}

function WeightRow({ w }: { w: ChallengerWeightRow }) {
  const proposed = w.status === "PROPOSED";
  return (
    <tr className="border-t border-white/5 align-top">
      <td className="py-0.5 pr-2 font-mono font-bold text-white/80">{w.regime}</td>
      <td className="py-0.5 pr-2">
        {proposed ? (
          <span className="rounded bg-signal-up/15 px-1 py-0.5 text-[9px] font-bold uppercase text-signal-up/90">
            öneri
          </span>
        ) : (
          <span className="text-[9px] uppercase text-white/35">veri az</span>
        )}
      </td>
      <td className="py-0.5 pr-2 text-right font-mono text-white/50">{w.records}</td>
      <td className="py-0.5 font-mono text-[9px] text-white/55">
        {proposed && w.deltas.length ? (
          w.deltas.map((d) => (
            <span key={d.module} className="mr-2 inline-block">
              {d.module}{" "}
              <span
                className={
                  (d.delta ?? 0) >= 0 ? "text-signal-up/80" : "text-signal-down/80"
                }
              >
                {(d.delta ?? 0) >= 0 ? "+" : ""}
                {num(d.delta, 3)}
              </span>
            </span>
          ))
        ) : (
          <span className="text-white/30">—</span>
        )}
      </td>
    </tr>
  );
}

export function BacktestChallengerPanel() {
  const { data, isLoading } = useBacktestChallenger();

  if (isLoading) {
    return (
      <PanelFrame id="backtest_challenger">
        <PanelHeader title="Backtest Challenger" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: BacktestChallengerView | undefined = data;

  if (!d || !d.enabled) {
    return (
      <PanelFrame id="backtest_challenger">
        <PanelHeader title="Backtest Challenger" subtitle="Geçmiş-prova kanıtı — hipotetik" />
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Backtest challenger kapalı (BACKTEST_CHALLENGER_ENABLED=0). Açıkken geçmişi
          yeniden oynatıp hangi sinyalin hangi piyasada işe yaradığını ölçer — canlı
          ayara dokunmadan.
        </div>
      </PanelFrame>
    );
  }

  const noData = d.status !== "OK";

  return (
    <PanelFrame id="backtest_challenger">
      <PanelHeader
        title="Backtest Challenger"
        subtitle="Hangi sinyal hangi piyasada işe yarıyor — geçmiş-prova"
        actions={
          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-mono text-white/60">
            {d.source_records ?? 0} kayıt
          </span>
        }
      />

      {/* Dürüstlük satırı — HER ZAMAN görünür */}
      <div className="mb-2 rounded border border-amber-400/20 bg-amber-400/[0.06] px-2 py-1 text-[10px] leading-4 text-amber-200/80">
        ⚠ {d.honesty}
      </div>

      {noData ? (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Veri birikiyor. Motor açık; geçmiş-prova kayıtları biriktikçe (günlük
          koşum) quantum ayrım karnesi ve aday ağırlıklar burada dolar.
        </div>
      ) : (
        <div className="space-y-3">
          {/* Quantum ayrım karnesi */}
          <div>
            <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-white/40">
              Quantum ayrım karnesi (rejim başına)
            </div>
            <table className="w-full text-[10px]">
              <thead>
                <tr className="text-left text-white/40">
                  <th className="py-0.5 pr-2 font-medium">Piyasa</th>
                  <th className="py-0.5 pr-2 font-medium">Hüküm</th>
                  <th className="py-0.5 pr-2 text-right font-medium">Ayrım</th>
                  <th className="py-0.5 pr-2 text-right font-medium">Korelasyon</th>
                  <th className="py-0.5 text-right font-medium">n</th>
                </tr>
              </thead>
              <tbody>
                {d.quantum.map((q) => (
                  <QuantumRow key={q.regime} q={q} />
                ))}
              </tbody>
            </table>
            {d.quantum_summary ? (
              <div className="mt-1 text-[10px] italic text-white/45">{d.quantum_summary}</div>
            ) : null}
          </div>

          {/* Aday ağırlık önerileri */}
          <div>
            <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-white/40">
              Aday ağırlık (champion'a göre fark)
            </div>
            <table className="w-full text-[10px]">
              <thead>
                <tr className="text-left text-white/40">
                  <th className="py-0.5 pr-2 font-medium">Piyasa</th>
                  <th className="py-0.5 pr-2 font-medium">Durum</th>
                  <th className="py-0.5 pr-2 text-right font-medium">Kayıt</th>
                  <th className="py-0.5 font-medium">En büyük değişim</th>
                </tr>
              </thead>
              <tbody>
                {d.weights.map((w) => (
                  <WeightRow key={w.regime} w={w} />
                ))}
              </tbody>
            </table>
          </div>

          {/* Terfi (B-4) durumu */}
          <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-1.5 text-[10px] text-white/60">
            <span className="text-white/35">Terfi (aday, champion'ı geçti mi?):</span>{" "}
            <span
              className={`font-mono font-bold ${
                d.promotion.status === "READY" ? "text-signal-up" : "text-white/70"
              }`}
            >
              {d.promotion.status === "READY" ? "HAZIR" : "hazır değil"}
            </span>
            <span className="ml-2 text-white/45">
              {d.promotion.matched ?? 0} eşleşme · {d.promotion.resolved ?? 0} ayrışma ·
              alt sınır {num(d.promotion.wilson_low, 2)} (gerek &gt; 0.5)
            </span>
          </div>
        </div>
      )}
    </PanelFrame>
  );
}
