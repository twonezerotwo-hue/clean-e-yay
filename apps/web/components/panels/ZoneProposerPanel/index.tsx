"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { api, API_BASE } from "@/lib/api/client";
import { qk } from "@/lib/queries/keys";
import { useZoneProposer } from "@/lib/queries/hooks";
import type { ZoneProposerAsset, ZoneProposerZone } from "@/types/uncontracted";

// Aday bölge önericisi — owner'ın kesişim yöntemi mekanik geometriyle her asset'te:
// haftalık pivot → LOG trend çizgisi → log-fib kümesi → kesişim → confluence skoru.
// İşaretli grafik + bölge tablosu. OWNER KARARI: bölgeler owner İPTAL EDENE KADAR
// onaylı; iptal edilen bölge canlı SL/TP yerleşimine (zone_influence) girmez.
// Makine bölge SEÇMEZ; panel HESAP YAPMAZ. /learning/zone-proposer.

function fmtPrice(v: number): string {
  if (v >= 1000) return v.toLocaleString("tr-TR", { maximumFractionDigits: 0 });
  if (v >= 10) return v.toFixed(2);
  return v.toFixed(4);
}

function ZoneRow({
  symbol,
  z,
  busy,
  onVerdict,
}: {
  symbol: string;
  z: ZoneProposerZone;
  busy: boolean;
  onVerdict: (z: ZoneProposerZone, action: "iptal" | "onay") => void;
}) {
  const approved = z.verdict === "onayli";
  return (
    <tr className="border-t border-white/5">
      <td className="py-0.5 pr-2 font-mono font-bold text-fuchsia-300/90">★{z.confluence}</td>
      <td className="py-0.5 pr-2 font-mono text-white/70">
        {fmtPrice(z.low)}–{fmtPrice(z.high)}
      </td>
      <td className="py-0.5 pr-2 text-white/45">{z.sources.join(", ")}</td>
      <td className="py-0.5 pr-2 text-right font-mono text-white/60">
        %{z.dist_pct} {z.side}
      </td>
      <td className="py-0.5 pr-2 font-mono text-white/45">{z.at ?? "—"}</td>
      <td className="py-0.5 pr-2">
        {approved ? (
          <span className="rounded bg-signal-up/15 px-1 text-[9px] font-bold text-signal-up/90">
            ONAYLI
          </span>
        ) : (
          <span className="rounded bg-signal-down/15 px-1 text-[9px] font-bold text-signal-down/90">
            İPTAL
          </span>
        )}
      </td>
      <td className="py-0.5 text-right">
        <button
          type="button"
          disabled={busy}
          onClick={() => onVerdict(z, approved ? "iptal" : "onay")}
          className={`rounded border px-1.5 py-0.5 text-[10px] disabled:opacity-40 ${
            approved
              ? "border-signal-down/40 text-signal-down/90 hover:bg-signal-down/10"
              : "border-signal-up/40 text-signal-up/90 hover:bg-signal-up/10"
          }`}
        >
          {approved ? "İptal et" : "Tekrar onayla"}
        </button>
      </td>
    </tr>
  );
}

function AssetBlock({ a }: { a: ZoneProposerAsset }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);

  const onVerdict = async (z: ZoneProposerZone, action: "iptal" | "onay") => {
    setBusy(true);
    try {
      await api.zoneProposerVerdict({
        symbol: a.symbol,
        low: z.low,
        high: z.high,
        action,
      });
      await qc.invalidateQueries({ queryKey: qk.zoneProposer });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      {/* İşaretli grafik: API'nin SVG'si — panel yeniden çizmez, öneriyi AYNEN gösterir */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={`${API_BASE}/api/v1/learning/zone-proposer/chart/${encodeURIComponent(a.symbol)}`}
        alt={`${a.symbol} işaretli haftalık grafik`}
        className="w-full rounded border border-white/10"
      />
      <div className="mt-1 overflow-x-auto">
        <table className="w-full text-[10px]">
          <thead>
            <tr className="text-left text-white/40">
              <th className="py-0.5 pr-2 font-medium">araç</th>
              <th className="py-0.5 pr-2 font-medium">bölge</th>
              <th className="py-0.5 pr-2 font-medium">kaynaklar</th>
              <th className="py-0.5 pr-2 text-right font-medium">uzaklık</th>
              <th className="py-0.5 pr-2 font-medium">tarih</th>
              <th className="py-0.5 pr-2 font-medium">durum</th>
              <th className="py-0.5 text-right font-medium">karar</th>
            </tr>
          </thead>
          <tbody>
            {a.zones.map((z) => (
              <ZoneRow
                key={`${z.low}-${z.high}`}
                symbol={a.symbol}
                z={z}
                busy={busy}
                onVerdict={onVerdict}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ZoneProposerPanel() {
  const { data, isLoading } = useZoneProposer();
  const [selected, setSelected] = useState<string | null>(null);

  if (isLoading) {
    return (
      <PanelFrame id="zone_proposer">
        <PanelHeader title="Bölge Önerileri (Kesişim)" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const assets = data?.assets ?? [];
  const active =
    assets.find((a) => a.symbol === selected) ?? assets[0] ?? null;

  return (
    <PanelFrame id="zone_proposer">
      <PanelHeader
        title="Bölge Önerileri (Kesişim)"
        subtitle="Owner yöntemi mekanik geometriyle: pivot → LOG çizgi → fib kümesi → kesişim"
        actions={
          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white/60">
            iptal edilmedikçe onaylı
          </span>
        }
      />

      {data && data.status === "OK" && active ? (
        <>
          <div className="mb-2 flex flex-wrap gap-1">
            {assets.map((a) => (
              <button
                key={a.symbol}
                type="button"
                onClick={() => setSelected(a.symbol)}
                className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${
                  a.symbol === active.symbol
                    ? "border-fuchsia-400/50 bg-fuchsia-400/10 text-fuchsia-200"
                    : "border-white/10 text-white/55 hover:bg-white/5"
                }`}
              >
                {a.symbol} ★{a.top_confluence}
              </button>
            ))}
          </div>

          <AssetBlock key={active.symbol} a={active} />

          <div className="mt-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[10px] leading-4 text-white/45">
            Makine ADAY önerir, bölge SEÇMEZ. İptal edilmedikçe onaylı (owner
            kararı). Onaylı bölgelerin canlı SL/TP yerleşimine etkisi
            <span className="font-mono"> zone_influence.enabled</span> flag&apos;ine
            bağlı — default KAPALI; 5y kanıt + owner onayı olmadan canlıya etki yok.
            Her iptal/onay kalibrasyon verisi olarak birikir.
          </div>
        </>
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Öneri artifact&apos;ı henüz üretilmedi. Öğrenme döngüsü (günlük)
          çalışınca kesişim bölgeleri ve işaretli grafikler burada görünecek.
        </div>
      )}
    </PanelFrame>
  );
}
