"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useTfScoringShadow } from "@/lib/queries/hooks";
import type { TfScoringShadowSymbol, TfScoringShadowView } from "@/types/uncontracted";

// Teknik oyun CANLI kaynağı (2026-07-12 owner kararı): sembol başına hava
// (UP/DOWN + verimlilik), rejim-anahtarlı konuşan TF'te v4 owner formülü yönü
// (CANLI, rozet) ve touche_backup yedeğinin yönü (v4 çekimserse o konuşur).
// Frontend HESAP YAPMAZ; consensus._touche_shadow aynı artifact'ı okur.

const BIAS: Record<string, { label: string; cls: string }> = {
  BULLISH: { label: "YUKARI", cls: "bg-signal-up/20 text-signal-up" },
  BEARISH: { label: "AŞAĞI", cls: "bg-signal-down/20 text-signal-down" },
  NEUTRAL: { label: "NÖTR", cls: "bg-white/10 text-white/55" },
  NONE: { label: "KANIT YOK", cls: "bg-white/5 text-white/35" },
};

function fmtDir(v?: number | null): string {
  return v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}`;
}

function Row({ sym, r }: { sym: string; r: TfScoringShadowSymbol }) {
  const bias = BIAS[r.bias ?? "NONE"] ?? BIAS.NONE;
  const reg = r.regime;
  const speaker = r.speaker_tf ?? (reg?.regime === "DOWN" ? "4h" : "1d");
  const speaking = r.direction_v4 != null ? "v4" : r.direction_backup != null ? "yedek" : "—";
  return (
    <div
      className="flex items-center justify-between gap-2 rounded border border-white/10 bg-black/20 px-2 py-1"
      title={`konuşan TF: ${speaker} · v4: ${fmtDir(r.direction_v4)} · yedek: ${fmtDir(
        r.direction_backup,
      )} · oyu veren: ${speaking}`}
    >
      <span className="w-16 truncate font-mono text-[11px] text-white/80">{sym}</span>
      <span className="text-[10px] uppercase tracking-wide text-white/40">
        {reg ? `${reg.regime === "UP" ? "yükseliş" : "düşüş"} · verim ${reg.er.toFixed(2)}` : "hava ?"}
      </span>
      <span className="flex items-center gap-2">
        <span className="font-mono text-[10px] tabular-nums text-white/40" title="yedek (touche_backup)">
          ydk {fmtDir(r.direction_backup)}
        </span>
        <span className="font-mono text-[10px] tabular-nums text-white/60" title="v4 owner formülü (CANLI)">
          v4 {fmtDir(r.direction_v4)}
        </span>
        <span className={`rounded px-1 py-0.5 text-[9px] font-bold uppercase tracking-wide ${bias.cls}`}>
          {bias.label}
        </span>
      </span>
    </div>
  );
}

export function TfScoringShadowPanel() {
  const { data, isLoading } = useTfScoringShadow();

  if (isLoading) {
    return (
      <PanelFrame id="tf_scoring_shadow">
        <PanelHeader title="Teknik Oy Kaynağı" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: TfScoringShadowView | undefined = data;
  const perSym = d?.per_symbol ?? {};
  const hasData = d?.status === "OK" && Object.keys(perSym).length > 0;

  return (
    <PanelFrame id="tf_scoring_shadow">
      <PanelHeader
        title="Teknik Oy Kaynağı"
        subtitle="v4 owner formülü CANLI — çekimserse yedek konuşur"
        actions={
          d?.generated_at ? (
            <span className="text-[10px] uppercase tracking-wide text-white/35">
              {new Date(d.generated_at).toLocaleTimeString("tr-TR", {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          ) : undefined
        }
      />
      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] leading-5 text-white/55">
        Önce havaya bakar: <strong className="text-white/75">yükselişte günlük</strong> konuşur,
        {" "}<strong className="text-white/75">düşüşte 4 saatlik</strong>. O TF&apos;te canlı teknik
        oy <strong className="text-white/75">v4 owner formülünden</strong> gelir; v4 çekimserse
        {" "}<strong className="text-white/75">yedek motor</strong> (kanıtlı-sinyal yolu) devralır,
        o da yoksa zemin motor. Rozet konuşan yönü gösterir.
      </p>

      {hasData ? (
        <div className="flex flex-col gap-1">
          {Object.entries(perSym).map(([sym, r]) => (
            <Row key={sym} sym={sym} r={r} />
          ))}
        </div>
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Üretici çıktısı henüz yok{d?.enabled === false ? " (adım kapalı)" : ""}. Öğrenme motoru her
          döngüde üretir; ilk koşumdan sonra burada görünür.
        </div>
      )}
    </PanelFrame>
  );
}
