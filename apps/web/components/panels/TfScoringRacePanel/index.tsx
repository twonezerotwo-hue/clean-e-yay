"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useTfScoringRace } from "@/lib/queries/hooks";
import type { TfScoringRaceDesign, TfScoringRaceView } from "@/types/uncontracted";

// R5 — "Yarış raporu" paneli. Gölge yönlerini (yeni beyin) gerçekleşen ileri-getiriyle
// puanlar ve eski harman (kontrol) + taban (buy-hold) ile yan yana kıyaslar. Kriter
// tutarsa owner onay paketi çıkar — terfi OTOMATİK DEĞİL (KIRMIZI ÇİZGİ).
// Frontend HESAP YAPMAZ; canlı karara dokunmaz.

const DESIGN_LABEL: Record<string, string> = {
  new_brain: "Yeni beyin",
  legacy: "Eski harman",
  baseline: "Taban (al-tut)",
  v3: "v3 (makro-kararlılık)",
  v4: "v4 (owner formülü)",
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
      <span className="w-24 truncate text-[11px] text-white/80">
        {DESIGN_LABEL[name] ?? name}
        {name === "new_brain" ? <span className="ml-1 text-signal-up/70">★</span> : null}
      </span>
      <span className="text-[10px] uppercase tracking-wide text-white/40">
        n={d.decisive}
      </span>
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
        <PanelHeader title="Yarış Raporu" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: TfScoringRaceView | undefined = data;
  const designs = d?.designs ?? {};
  const hasData = d?.status === "OK" && (d?.resolved ?? 0) > 0;
  const ready = d?.checks
    ? Boolean(
        d.checks.resolved_decisive?.pass &&
          d.checks.ci_disjoint?.pass &&
          d.checks.beats_baseline?.pass,
      )
    : false;
  const newAvg = designs.new_brain?.avg_return_pct ?? null;
  const bestName =
    Object.entries(designs).reduce<[string, number]>(
      (best, [k, v]) => ((v.avg_return_pct ?? -Infinity) > best[1] ? [k, v.avg_return_pct ?? -Infinity] : best),
      ["", -Infinity],
    )[0];

  return (
    <PanelFrame id="tf_scoring_race">
      <PanelHeader
        title="Yarış Raporu"
        subtitle="Yeni beyin eskiyi/tabanı geçiyor mu — puanlar, terfi ETMEZ"
        actions={
          <span
            className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${
              ready ? "bg-amber-400/20 text-amber-200" : "bg-white/5 text-white/40"
            }`}
          >
            {ready ? "owner paketi hazır" : "kanıt biriktiriyor"}
          </span>
        }
      />
      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] leading-5 text-white/55">
        Gölgenin her yön çağrısı fiyatla deftere yazılır; ufuk dolunca gerçekleşen hareketle
        puanlanır. <strong className="text-white/75">Yeni beyin</strong> eski harmanı ve
        {" "}<strong className="text-white/75">al-tut tabanını</strong> geçerse owner&apos;a onay
        paketi çıkar — terfi otomatik <strong className="text-white/75">değildir</strong>.
      </p>

      {hasData ? (
        <>
          <div className="mb-2 flex items-center justify-between gap-2 text-[10px] uppercase tracking-wide text-white/40">
            <span>çözülen çağrı: {d?.resolved}</span>
            <span>defter: {d?.ledger_rows} satır</span>
            <span>
              taban:{" "}
              <span className={d?.beats_baseline ? "text-signal-up" : "text-white/45"}>
                {d?.beats_baseline == null ? "?" : d?.beats_baseline ? "geçti" : "geçemedi"}
              </span>
            </span>
          </div>
          <div className="flex flex-col gap-1">
            {["new_brain", "v4", "v3", "legacy", "baseline"].map((name) =>
              designs[name] ? (
                <DesignRow key={name} name={name} d={designs[name]} best={name === bestName} />
              ) : null,
            )}
          </div>
          <p className="mt-2 text-[10px] leading-4 text-white/35">
            Yeni beyin ortalama yön-getirisi {fmtPct(newAvg)} · isabetin şans olmadığı Wilson
            {" "}%95 alt sınırıyla, tabanı geçiş ortalama getiriyle sınanır.
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
