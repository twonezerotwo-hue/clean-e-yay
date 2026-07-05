"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useEvidenceBus } from "@/lib/queries/hooks";
import type { EvidenceBusView, EvidenceRecord } from "@/types/uncontracted";

// I6 — Öğrenme Beyni. I1 Kanıt Otobüsü + I2 Olgunluk Kapısı'nı TEK panelde
// gösterir: sistemin bildiği her öğrenme kanıtı, hangi kaynaktan (canlı/gölge/
// prova) ve hangi olgunluk basamağında (az örnek → gözlemde → öneri → oto-hazır).
// Salt-gözlem: frontend HESAP YAPMAZ; sayılar /learning/evidence-bus'tan.

const MATURITY: Record<string, { label: string; cls: string; order: number }> = {
  ACTIONABLE: { label: "oto-hazır", cls: "bg-signal-up/20 text-signal-up", order: 3 },
  PROPOSABLE: { label: "öneri seviyesi", cls: "bg-amber-400/20 text-amber-200", order: 2 },
  OBSERVED: { label: "gözlemde", cls: "bg-white/10 text-white/50", order: 1 },
  INSUFFICIENT: { label: "az örnek", cls: "bg-white/[0.04] text-white/35", order: 0 },
};

const SOURCE: Record<string, { label: string; cls: string }> = {
  live: { label: "canlı", cls: "bg-signal-up/15 text-signal-up/90" },
  backtest: { label: "prova", cls: "bg-accent-cyan/15 text-accent-cyan" },
  shadow: { label: "gölge", cls: "bg-white/10 text-white/50" },
};

const TOPIC_LABEL: Record<string, string> = {
  signal_quality: "sinyal kalitesi",
  quantum_discrimination: "quantum ayrımı",
  edge_stability: "edge stabilitesi",
  discovery_candidate: "keşif adayı",
  tf_calibration: "TF kalibrasyonu",
};

// Olgunluk özeti — hep bu sırayla (en olgun solda), her zaman görünür.
const MATURITY_ORDER = ["ACTIONABLE", "PROPOSABLE", "OBSERVED", "INSUFFICIENT"] as const;

function maturityOrder(rec: EvidenceRecord): number {
  const m = rec.maturity?.maturity;
  return m && MATURITY[m] ? MATURITY[m].order : -1;
}

function Badge({ map, k }: { map: Record<string, { label: string; cls: string }>; k: string }) {
  const it = map[k];
  return (
    <span
      className={`rounded px-1 py-0.5 text-[9px] font-bold uppercase ${it ? it.cls : "bg-white/10 text-white/40"}`}
    >
      {it ? it.label : k}
    </span>
  );
}

function EvidenceRow({ r }: { r: EvidenceRecord }) {
  const m = r.maturity?.maturity ?? "";
  return (
    <tr className="border-t border-white/5 align-top">
      <td className="py-0.5 pr-2">
        <div className="font-mono text-white/80">{r.subject}</div>
        <div className="text-[9px] text-white/35">{TOPIC_LABEL[r.topic] ?? r.topic}</div>
      </td>
      <td className="py-0.5 pr-2">
        <Badge map={SOURCE} k={r.source} />
      </td>
      <td className="py-0.5 pr-2">
        <Badge map={MATURITY} k={m} />
      </td>
      <td className="py-0.5 pr-2 font-mono text-[9px] text-white/45">{r.verdict ?? "—"}</td>
      <td className="py-0.5 text-right font-mono text-white/50">{r.n_samples ?? "—"}</td>
    </tr>
  );
}

export function LearningBrainPanel() {
  const { data, isLoading } = useEvidenceBus();

  if (isLoading) {
    return (
      <PanelFrame id="learning_brain">
        <PanelHeader title="Öğrenme Beyni" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: EvidenceBusView | undefined = data;

  if (!d || d.total === 0) {
    return (
      <PanelFrame id="learning_brain">
        <PanelHeader title="Öğrenme Beyni" subtitle="Sistem şu an neyi biliyor — tüm kanıt tek yerde" />
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Henüz kanıt birikmedi. Öğrenme katmanı ölçüm ürettikçe (sinyal kalitesi,
          edge, quantum karnesi, keşif gölgesi, TF kalibrasyon) burada tek listede
          toplanır — hangi kaynaktan, hangi olgunlukta.
        </div>
      </PanelFrame>
    );
  }

  const records = [...d.records].sort(
    (a, b) => maturityOrder(b) - maturityOrder(a) || (b.n_samples ?? 0) - (a.n_samples ?? 0),
  );

  return (
    <PanelFrame id="learning_brain">
      <PanelHeader
        title="Öğrenme Beyni"
        subtitle="Sistem şu an neyi biliyor — tüm kanıt tek yerde"
        actions={
          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-mono text-white/60">
            {d.total} kanıt
          </span>
        }
      />

      {/* Olgunluk özeti — en olgun solda */}
      <div className="mb-2 flex flex-wrap gap-1.5">
        {MATURITY_ORDER.map((key) => {
          const n = d.by_maturity[key] ?? 0;
          const meta = MATURITY[key];
          return (
            <span
              key={key}
              className={`rounded px-1.5 py-0.5 text-[10px] ${n ? meta.cls : "bg-white/[0.03] text-white/25"}`}
            >
              {meta.label} <span className="font-mono font-bold">{n}</span>
            </span>
          );
        })}
      </div>

      {/* Kaynak dağılımı */}
      <div className="mb-2 flex flex-wrap gap-3 text-[10px] text-white/45">
        {(["live", "shadow", "backtest"] as const).map((s) =>
          d.by_source[s] ? (
            <span key={s}>
              {SOURCE[s].label}: <span className="font-mono text-white/70">{d.by_source[s]}</span>
            </span>
          ) : null,
        )}
      </div>

      {/* Kanıt tablosu — en olgun üstte */}
      <table className="w-full text-[10px]">
        <thead>
          <tr className="text-left text-white/40">
            <th className="py-0.5 pr-2 font-medium">Kanıt</th>
            <th className="py-0.5 pr-2 font-medium">Kaynak</th>
            <th className="py-0.5 pr-2 font-medium">Olgunluk</th>
            <th className="py-0.5 pr-2 font-medium">Hüküm</th>
            <th className="py-0.5 text-right font-medium">n</th>
          </tr>
        </thead>
        <tbody>
          {records.map((r) => (
            <EvidenceRow key={`${r.topic}:${r.subject}`} r={r} />
          ))}
        </tbody>
      </table>

      <div className="mt-2 text-[9px] leading-4 text-white/35">
        Basamaklar: az örnek → gözlemde → öneri seviyesi → oto-hazır. Salt-gözlem —
        bu panel hiçbir karara dokunmaz; terfi/yön owner onayına bağlıdır.
      </div>
    </PanelFrame>
  );
}
