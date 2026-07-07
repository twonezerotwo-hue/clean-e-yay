"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useDatasetHealth } from "@/lib/queries/hooks";
import type { DatasetHealthView } from "@/types/generated/api";

// CP1 — öğrenme veri-hazırlık paneli. "Biriktirdiğimiz veri her öğrenici için
// yeterli mi" sorusunu gösterir. Frontend hesap YAPMAZ; tüm sayım/oran
// /api/v1/learning/dataset-health ViewModel'inden gelir (observe-only).

const LEARNER_LABEL: Record<string, string> = {
  calibration: "Kalibrasyon",
  weights_metrics: "Ağırlık & metrik",
};

// Y-2 — üçlü-bariyer kalite etiketleri (exit_forensics.barrier_label; şanslı
// artı ile hakiki kazanç ayrımı). Frontend hesap YAPMAZ, yalnız adlandırır.
const QUALITY_LABEL: Record<string, string> = {
  clean_win: "hakiki kazanç",
  lucky_win: "şanslı artı",
  partial_capture: "kısmi yakalama",
  roundtrip_loss: "korunamayan kâr",
  clean_loss: "temiz kayıp",
  timeout_loss: "süre doldu −",
  never_worked: "hiç işlemedi",
  gray: "atıfsız",
  excluded: "manuel",
  unknown: "bilinmez",
};

const QUALITY_TONE: Record<string, string> = {
  clean_win: "bg-signal-up/20 text-signal-up",
  lucky_win: "bg-amber-400/20 text-amber-300",
  partial_capture: "bg-amber-400/20 text-amber-300",
  roundtrip_loss: "bg-signal-down/20 text-signal-down",
  clean_loss: "bg-white/10 text-white/60",
  timeout_loss: "bg-white/10 text-white/60",
  never_worked: "bg-white/10 text-white/50",
};

function CoverageBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div>
      <div className="flex justify-between text-[10px] uppercase tracking-wide text-white/45">
        <span>{label}</span>
        <span className="tabular-nums text-white/70">%{pct}</span>
      </div>
      <div className="mt-0.5 h-1.5 rounded-full bg-white/10">
        <div
          className={`h-1.5 rounded-full ${pct >= 80 ? "bg-signal-up" : pct >= 50 ? "bg-amber-400" : "bg-signal-down"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function DatasetHealthPanel() {
  const { data, isLoading } = useDatasetHealth();

  if (isLoading) {
    return (
      <PanelFrame id="dataset_health">
        <PanelHeader title="Veri Sağlığı" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: DatasetHealthView | undefined = data;
  const learners = d?.learners ?? [];
  const cov = d?.coverage;

  return (
    <PanelFrame id="dataset_health">
      <PanelHeader
        title="Veri Sağlığı"
        subtitle="Öğrenmek için yeterli ve temiz veri var mı"
        actions={
          <span
            className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
              d?.all_ready ? "bg-signal-up/20 text-signal-up" : "bg-amber-400/20 text-amber-300"
            }`}
          >
            {d?.all_ready ? "HAZIR" : "BİRİKİYOR"}
          </span>
        }
      />
      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] leading-5 text-white/55">
        Biriken kapanmış işlemlerin ne kadarı öğrenmeye <strong className="text-white/75">elverişli</strong>
        {" "}(doğrulanmış + güven damgalı) ve her öğrenici için yeterli örnek var mı.
      </p>

      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2">
          <div className="text-lg font-semibold tabular-nums text-white/85">{d?.total ?? 0}</div>
          <div className="text-[10px] uppercase tracking-wide text-white/45">Toplam</div>
        </div>
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2">
          <div className="text-lg font-semibold tabular-nums text-white/85">{d?.verified ?? 0}</div>
          <div className="text-[10px] uppercase tracking-wide text-white/45">Doğrulanmış</div>
        </div>
        <div className="rounded border border-accent-cyan/25 bg-accent-cyan/5 px-2 py-2">
          <div className="text-lg font-semibold tabular-nums text-accent-cyan">{d?.trainable ?? 0}</div>
          <div className="text-[10px] uppercase tracking-wide text-white/45">Eğitilebilir</div>
        </div>
      </div>

      {cov ? (
        <div className="mt-3 space-y-2">
          <CoverageBar label="Doğrulanmış" value={cov.verified_pct} />
          <CoverageBar label="Güven damgalı" value={cov.confidence_pct} />
          <CoverageBar label="MAE/MFE'li" value={cov.excursion_pct} />
          <CoverageBar label="$ boyutlu (çıkış tahmini)" value={cov.size_usd_pct} />
        </div>
      ) : null}

      {d?.barrier_labels && Object.keys(d.barrier_labels.by_quality).length ? (
        <div className="mt-3">
          <div className="mb-1 text-[10px] uppercase tracking-wide text-white/45">
            Bariyer etiketi (kapanışın kalitesi)
          </div>
          <div className="flex flex-wrap gap-1">
            {Object.entries(d.barrier_labels.by_quality).map(([q, n]) => (
              <span
                key={q}
                className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${QUALITY_TONE[q] ?? "bg-white/10 text-white/50"}`}
              >
                {QUALITY_LABEL[q] ?? q} <span className="tabular-nums">{n}</span>
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {learners.length ? (
        <div className="mt-3 space-y-1">
          {learners.map((l) => (
            <div
              key={l.name}
              className="flex items-center justify-between rounded border border-white/10 bg-black/20 px-2 py-1.5 text-[11px]"
            >
              <span className="text-white/70">{LEARNER_LABEL[l.name] ?? l.name}</span>
              <span className="flex items-center gap-2">
                <span className="tabular-nums text-white/50">
                  {l.have}/{l.need}
                </span>
                <span
                  className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase ${
                    l.ready ? "bg-signal-up/20 text-signal-up" : "bg-white/10 text-white/50"
                  }`}
                >
                  {l.ready ? "hazır" : "bekliyor"}
                </span>
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </PanelFrame>
  );
}
