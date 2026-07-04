"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useDiscovery } from "@/lib/queries/hooks";
import type { DiscoveryCandidate, DiscoveryView } from "@/types/generated/api";

// K-3 — Keşif Tarayıcısı ("analiz sabit, varlık değişken"). Geniş evren
// (yükselen sektör ETF'leri + kripto top-50) canlı analiz çekirdeğinden geçer
// ama işlem AÇILMAZ. Tablodaki hüküm ve karneler tamamen HİPOTETİK — hiçbiri
// gerçek pozisyon değil. Frontend hesap YAPMAZ; sayılar /learning/discovery'den.

const KIND_LABEL: Record<string, string> = {
  sector_etf: "Sektör ETF",
  crypto: "Kripto",
};

function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `%${Math.round(v * 100)}`;
}

function rMult(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}R`;
}

function CandidateRow({ c }: { c: DiscoveryCandidate }) {
  const isSignal = c.verdict === "WOULD_OPEN_LONG";
  return (
    <tr className="border-t border-white/5">
      <td className="py-0.5 pr-2">
        <span className="font-mono font-bold text-white/80">{c.symbol}</span>
        <span className="ml-1 text-[9px] text-white/35">{KIND_LABEL[c.kind] ?? c.kind}</span>
      </td>
      <td className="py-0.5 pr-2">
        {isSignal ? (
          <span className="rounded bg-signal-up/20 px-1 py-0.5 text-[9px] font-bold uppercase text-signal-up">
            açılırdı ↑
          </span>
        ) : (
          <span className="text-white/30">—</span>
        )}
      </td>
      <td className="py-0.5 pr-2 font-mono text-white/60">{c.entry_timeframe ?? "—"}</td>
      <td className="py-0.5 pr-2 text-right font-mono text-white/60">{pct(c.confidence)}</td>
      <td
        className={`py-0.5 pr-2 text-right font-mono ${
          c.expected_value === null || c.expected_value === undefined
            ? "text-white/40"
            : c.expected_value >= 0
              ? "text-signal-up/80"
              : "text-signal-down/80"
        }`}
      >
        {rMult(c.expected_value)}
      </td>
      {/* K-2 gölge karnesi (biriken hipotetik kanıt) */}
      <td className="py-0.5 pr-2 text-right font-mono text-white/60">
        {c.shadow_resolved}
        <span className="text-white/30">/{c.shadow_signals}</span>
      </td>
      <td className="py-0.5 pr-2 text-right font-mono text-white/70">{pct(c.cf_win_rate)}</td>
      <td
        className={`py-0.5 pr-2 text-right font-mono ${
          c.avg_r === null || c.avg_r === undefined
            ? "text-white/40"
            : c.avg_r >= 0
              ? "text-signal-up/80"
              : "text-signal-down/80"
        }`}
      >
        {rMult(c.avg_r)}
      </td>
      <td className="py-0.5 text-right font-mono text-white/40">
        {c.shadow_timeframes.length ? c.shadow_timeframes.join(" ") : "—"}
      </td>
    </tr>
  );
}

export function DiscoveryPanel() {
  const { data, isLoading } = useDiscovery();

  if (isLoading) {
    return (
      <PanelFrame id="discovery">
        <PanelHeader title="Keşif Tarayıcısı" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: DiscoveryView | undefined = data;

  if (!d || !d.enabled) {
    return (
      <PanelFrame id="discovery">
        <PanelHeader title="Keşif Tarayıcısı" subtitle="Yeni aday arayışı — hipotetik" />
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Keşif tarayıcısı kapalı (DISCOVERY_SCAN_ENABLED=0). Açıkken geniş evreni
          tarar ve "açılırdı" hükümlerinin gölge karnesini biriktirir — işlem açmadan.
        </div>
      </PanelFrame>
    );
  }

  const cands = d.candidates;

  return (
    <PanelFrame id="discovery">
      <PanelHeader
        title="Keşif Tarayıcısı"
        subtitle="Analiz sabit, varlık değişken — hangi yeni aday açılırdı"
        actions={
          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-mono text-white/60">
            {d.regime ?? "—"}
          </span>
        }
      />

      {/* Dürüstlük satırı — HER ZAMAN görünür */}
      <div className="mb-2 rounded border border-amber-400/20 bg-amber-400/[0.06] px-2 py-1 text-[10px] leading-4 text-amber-200/80">
        ⚠ {d.honesty}
      </div>

      {/* Evren + koşu özeti */}
      <div className="mb-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-white/50">
        <span>
          <span className="text-white/35">Yükselen sektör:</span>{" "}
          <span className="font-mono text-white/70">{d.universe.sectors.rising_n}</span>
        </span>
        <span>
          <span className="text-white/35">Kripto aday:</span>{" "}
          <span className="font-mono text-white/70">{d.universe.crypto.count}</span>
        </span>
        <span>
          <span className="text-white/35">Canlı sinyal:</span>{" "}
          <span className="font-mono text-signal-up/80">{d.scan.signals_n}</span>
        </span>
        <span>
          <span className="text-white/35">Aktif izleme:</span>{" "}
          <span className="font-mono text-white/70">{d.shadow.active_n}</span>
        </span>
        <span>
          <span className="text-white/35">Son koşu:</span>{" "}
          <span className="font-mono text-white/60">
            +{d.shadow.tracked_new} yeni · {d.shadow.resolved} çözüldü
          </span>
        </span>
      </div>

      {cands.length ? (
        <div className="overflow-x-auto">
          <table className="w-full text-[10px]">
            <thead>
              <tr className="text-left text-white/40">
                <th className="py-0.5 pr-2 font-medium">Sembol</th>
                <th className="py-0.5 pr-2 font-medium">Hüküm</th>
                <th className="py-0.5 pr-2 font-medium">TF</th>
                <th className="py-0.5 pr-2 text-right font-medium">Güven</th>
                <th className="py-0.5 pr-2 text-right font-medium">EV</th>
                <th className="py-0.5 pr-2 text-right font-medium">
                  Çözüm<span className="text-white/25">/sinyal</span>
                </th>
                <th className="py-0.5 pr-2 text-right font-medium">
                  İsabet <span className="text-white/30">(hip.)</span>
                </th>
                <th className="py-0.5 pr-2 text-right font-medium">Ort.R</th>
                <th className="py-0.5 text-right font-medium">TF karne</th>
              </tr>
            </thead>
            <tbody>
              {cands.map((c) => (
                <CandidateRow key={c.symbol} c={c} />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Henüz aday yok. Tarayıcı her koşuda evrenin bir dilimini tarar; sinyal
          bulur ya da gölge karnesi biriktikçe bu tablo dolar.
        </div>
      )}
    </PanelFrame>
  );
}
