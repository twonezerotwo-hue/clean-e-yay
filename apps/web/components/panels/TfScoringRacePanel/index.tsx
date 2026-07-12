"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useTfScoringRace } from "@/lib/queries/hooks";
import type { TfScoringRaceDesign, TfScoringRaceView } from "@/types/uncontracted";

// Doğrulama karnesi (2026-07-12 owner kararı): v4 CANLI teknik oy — kanıtı
// backtest-only olduğu için her yön çağrısı gerçekleşen ileri-getiriyle
// puanlanır ve yedek motor + taban (al-tut) ile yan yana kıyaslanır.
// V4_BEHIND görülürse geri-alma owner kararı (touche_v4=false, tek satır).
// Frontend HESAP YAPMAZ; otomatik aksiyon YOK.

const DESIGN_LABEL: Record<string, string> = {
  v4: "v4 (CANLI oy)",
  backup: "Yedek motor",
  baseline: "Taban (al-tut)",
};
const DESIGN_ORDER = ["v4", "backup", "baseline"];

const VERDICT: Record<string, { label: string; cls: string }> = {
  COLLECTING: { label: "kanıt biriktiriyor", cls: "bg-white/5 text-white/40" },
  V4_AHEAD: { label: "v4 önde", cls: "bg-signal-up/20 text-signal-up" },
  V4_BEHIND: { label: "v4 GERİDE — geri-alma?", cls: "bg-signal-down/20 text-signal-down" },
};

function fmtPct(v?: number | null): string {
  if (v == null) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function fmtRate(v?: number | null): string {
  return v == null ? "—" : `%${Math.round(v * 100)}`;
}

function DesignRow({ name, d, best }: { name: string; d: TfScoringRaceDesign; best: boolean }) {
  return (
    <div
      className={`flex items-center justify-between gap-2 rounded border px-2 py-1 ${
        best ? "border-signal-up/40 bg-signal-up/10" : "border-white/10 bg-black/20"
      }`}
    >
      <span className="w-28 truncate text-[11px] text-white/80">
        {DESIGN_LABEL[name] ?? name}
        {name === "v4" ? <span className="ml-1 text-signal-up/70">★</span> : null}
      </span>
      <span className="text-[10px] uppercase tracking-wide text-white/40">n={d.decisive}</span>
      <span className="flex items-center gap-2">
        <span className="font-mono text-[10px] tabular-nums text-white/55">
          isabet {fmtRate(d.hit_rate)}
        </span>
        <span
          className={`w-16 text-right font-mono text-[11px] tabular-nums ${
            (d.avg_return_pct ?? 0) > 0
              ? "text-signal-up"
              : (d.avg_return_pct ?? 0) < 0
                ? "text-signal-down"
                : "text-white/45"
          }`}
        >
          {fmtPct(d.avg_return_pct)}
        </span>
      </span>
    </div>
  );
}

export function TfScoringRacePanel() {
  const { data, isLoading } = useTfScoringRace();

  if (isLoading) {
    return (
      <PanelFrame id="tf_scoring_race">
        <PanelHeader title="v4 Doğrulama Karnesi" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: TfScoringRaceView | undefined = data;
  const designs = d?.designs ?? {};
  const hasData = d?.status === "OK" && (d?.resolved ?? 0) > 0;
  const verdict = VERDICT[d?.race_status ?? "COLLECTING"] ?? VERDICT.COLLECTING;
  const v4Avg = designs.v4?.avg_return_pct ?? null;
  const bestName =
    Object.entries(designs).reduce<[string, number]>(
      (best, [k, v]) => ((v.avg_return_pct ?? -Infinity) > best[1] ? [k, v.avg_return_pct ?? -Infinity] : best),
      ["", -Infinity],
    )[0];

  const flag = (v?: boolean | null) => (v == null ? "?" : v ? "geçiyor" : "GEÇEMİYOR");

  return (
    <PanelFrame id="tf_scoring_race">
      <PanelHeader
        title="v4 Doğrulama Karnesi"
        subtitle="canlı oy sınavda — puanlar, karar owner'ın"
        actions={
          <span
            className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${verdict.cls}`}
          >
            {verdict.label}
          </span>
        }
      />
      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] leading-5 text-white/55">
        <strong className="text-white/75">v4 artık canlı teknik oy</strong> ama kanıtı backtest
        kaynaklı; her yön çağrısı fiyatla deftere yazılır, ufuk dolunca gerçekleşen hareketle
        puanlanır. v4 yeterli örneklemde <strong className="text-white/75">yedeğin veya tabanın
        gerisine düşerse</strong> geri-alma tek satır: <code>touche_v4: false</code>.
      </p>

      {hasData ? (
        <>
          <div className="mb-2 flex items-center justify-between gap-2 text-[10px] uppercase tracking-wide text-white/40">
            <span>çözülen: {d?.resolved}</span>
            <span>
              yedeği:{" "}
              <span className={d?.beats_backup ? "text-signal-up" : "text-white/45"}>{flag(d?.beats_backup)}</span>
            </span>
            <span>
              tabanı:{" "}
              <span className={d?.beats_baseline ? "text-signal-up" : "text-white/45"}>
                {flag(d?.beats_baseline)}
              </span>
            </span>
          </div>
          <div className="flex flex-col gap-1">
            {DESIGN_ORDER.map((name) =>
              designs[name] ? (
                <DesignRow key={name} name={name} d={designs[name]} best={name === bestName} />
              ) : null,
            )}
          </div>
          <p className="mt-2 text-[10px] leading-4 text-white/35">
            v4 ortalama yön-getirisi {fmtPct(v4Avg)} · isabetin şans olmadığı Wilson %95 alt
            sınırıyla izlenir · otomatik aksiyon yok, karar owner&apos;ın.
          </p>
        </>
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Henüz çözülmüş çağrı yok{d?.enabled === false ? " (adım kapalı)" : ""}. Defter her döngüde
          büyür; konuşan barın ufku dolunca sonuç burada puanlanır.
        </div>
      )}
    </PanelFrame>
  );
}
