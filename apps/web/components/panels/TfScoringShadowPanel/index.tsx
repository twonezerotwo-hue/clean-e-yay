"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useTfScoringShadow } from "@/lib/queries/hooks";
import type { TfScoringShadowSymbol, TfScoringShadowView } from "@/types/uncontracted";

// R4 — "Yeni beyin ne diyor" paneli. tf_scoring_v2 GÖLGE çıktısı: sembol başına
// hava (UP/DOWN + verimlilik), rejim-anahtarlı BİRİNCİL yön (UP→1d konuşur,
// DOWN→4h konuşur; yalnız kanıtlı sinyaller) ve KONTROL eski-harman yönü.
// Frontend HESAP YAPMAZ; canlı karara dokunmaz — izleme/yarış verisi (D7).

const BIAS: Record<string, { label: string; cls: string }> = {
  BULLISH: { label: "YUKARI", cls: "bg-signal-up/20 text-signal-up" },
  BEARISH: { label: "AŞAĞI", cls: "bg-signal-down/20 text-signal-down" },
  NEUTRAL: { label: "NÖTR", cls: "bg-white/10 text-white/55" },
  NONE: { label: "KANIT YOK", cls: "bg-white/5 text-white/35" },
};

function Row({ sym, r }: { sym: string; r: TfScoringShadowSymbol }) {
  const bias = BIAS[r.bias ?? "NONE"] ?? BIAS.NONE;
  const reg = r.regime;
  const speaker = reg?.regime === "DOWN" ? "4h" : "1d";
  const drivers = r.drivers?.[speaker] ?? {};
  const driverTxt = Object.entries(drivers)
    .map(([n, d]) => `${n} ${d.lean > 0 ? "+" : ""}${d.lean.toFixed(2)}`)
    .join(" · ");
  return (
    <div
      className="flex items-center justify-between gap-2 rounded border border-white/10 bg-black/20 px-2 py-1"
      title={`konuşan TF: ${speaker} · sürücüler: ${driverTxt || "—"} · eski harman: ${
        r.direction_blend_legacy ?? "—"
      }`}
    >
      <span className="w-16 truncate font-mono text-[11px] text-white/80">{sym}</span>
      <span className="text-[10px] uppercase tracking-wide text-white/40">
        {reg ? `${reg.regime === "UP" ? "yükseliş" : "düşüş"} · verim ${reg.er.toFixed(2)}` : "hava ?"}
      </span>
      <span className="flex items-center gap-1.5">
        <span className="font-mono text-[10px] tabular-nums text-white/45">
          {r.direction != null ? `${r.direction > 0 ? "+" : ""}${r.direction.toFixed(2)}` : "—"}
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
        <PanelHeader title="Yeni Beyin (Gölge)" />
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
        title="Yeni Beyin (Gölge)"
        subtitle="Rejim-anahtarlı v2 yönü — izler, karar VERMEZ"
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
        Önce havaya bakar: <strong className="text-white/75">yükselişte günlük trend</strong> konuşur,
        {" "}<strong className="text-white/75">düşüşte 4 saatlik yapı</strong>. Yalnız kanıtlı sinyaller
        yön verebilir. Satıra gelince eski-harman kıyası ve sürücü sinyaller görünür.
      </p>

      {hasData ? (
        <div className="flex flex-col gap-1">
          {Object.entries(perSym).map(([sym, r]) => (
            <Row key={sym} sym={sym} r={r} />
          ))}
        </div>
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Gölge çıktısı henüz yok{d?.enabled === false ? " (adım kapalı)" : ""}. Öğrenme motoru her
          döngüde üretir; ilk koşumdan sonra burada görünür.
        </div>
      )}
    </PanelFrame>
  );
}
