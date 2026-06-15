"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { SparkLine } from "@/components/charts/SparkLine";
import {
  usePaperTradingState,
  useRiskCorrelation,
  useRiskHalts,
} from "@/lib/queries/hooks";
import { selectFlaggedClusters, selectLimits } from "@/lib/selectors/correlation";
import { selectHaltLevel } from "@/lib/selectors/halts";
import { fmtUSD, fmtPct, fmtNum, fmtRelative } from "@/lib/format";
import type { Position, Trade } from "@/types/generated/api";

// Phase 3 — codex PaperTradingTicker'ın GÖRSEL dilini (mono ticker chip'leri +
// bölünmüş stat satırı + pozisyon kartları) korur. Veri YALNIZCA backend
// PaperTradingState ViewModel'inden gelir (usePaperTradingState hook → typed
// contract). Codex'in kirli kısmı (raw fetch, POST close/reset/repair, equityPct
// / RR / pnl_pct gibi frontend risk matematiği) KASITLI olarak taşınmadı:
//   - manuel/untyped fetch YOK — sadece typed hook'lar.
//   - order/close/reset UI YOK — read-only performans yüzeyi.
//   - frontend PnL/risk/regime hesabı YOK — tüm sayılar backend alanlarının
//     passthrough'u; `>= 0` yalnız renk/işaret içindir (biçim, karar değil).

// pozitif/negatif renk tonu — yalnız görsel işaret.
function pnlTone(v: number | null | undefined): string {
  if (v == null) return "text-white/70";
  return v >= 0 ? "text-signal-up" : "text-signal-down";
}

// imzalı USD gösterimi — pozitifte "+" öneki (biçimleme; fmtUSD negatifi zaten
// işaretler). Hesap yok.
function fmtSignedUSD(v: number | null | undefined): string {
  if (v == null) return "—";
  return v >= 0 ? `+${fmtUSD(v)}` : fmtUSD(v);
}

// Codex ticker chip'i — küçük uppercase etiket + mono değer, dikey ayraçlı.
function Chip({
  label,
  value,
  tone = "text-white/90",
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="px-3 first:pl-0">
      <div className="text-[8px] font-mono uppercase tracking-wider text-white/40">
        {label}
      </div>
      <div className={`font-mono text-sm font-bold leading-tight tabular-nums ${tone}`}>
        {value}
      </div>
    </div>
  );
}

// Açık pozisyon satırı — TF rozeti + side + (passthrough) unrealized PnL +
// time-stop. Hiçbir alan hesaplanmaz; unrealized_pnl_usd backend'den gelir.
function OpenPositions({ positions }: { positions: Position[] }) {
  if (!positions.length) {
    return (
      <p className="mt-2 text-[10px] font-mono italic text-white/40">
        açık pozisyon yok
      </p>
    );
  }
  return (
    <ul className="mt-3 space-y-1 text-[11px]">
      {positions.map((p) => (
        <li
          key={p.id}
          className="flex items-center justify-between border-b border-white/5 pb-0.5"
        >
          <span className="flex items-center gap-1.5">
            <span className="font-medium">{p.symbol}</span>
            <span className="rounded border border-accent-cyan/40 px-1 py-px text-[9px] uppercase text-accent-cyan">
              {p.timeframe ?? "1d"}
            </span>
            <span className={p.side === "long" ? "text-signal-up" : "text-signal-down"}>
              {p.side}
            </span>
            {p.unrealized_pnl_usd != null && (
              <span className={`tabular-nums ${pnlTone(p.unrealized_pnl_usd)}`}>
                {fmtSignedUSD(p.unrealized_pnl_usd)}
              </span>
            )}
          </span>
          {/* UX1 — time-stop durumu backend'de; negatif/yanıltıcı geri sayım YOK. */}
          <span className="tabular-nums">
            {(p.time_stop_status ?? (p.valid_until ? "ACTIVE" : "NONE")) === "EXPIRED" ? (
              <span className="text-amber-400">TIME_STOP_EXPIRED</span>
            ) : p.valid_until ? (
              <span className="text-white/45">time-stop {fmtRelative(p.valid_until)}</span>
            ) : (
              <span className="text-white/45">time-stop yok</span>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}

// Son kapanan işlemler şeridi — symbol/side/close_reason/PnL, hepsi passthrough.
function RecentTrades({ trades }: { trades: Trade[] }) {
  if (!trades.length) return null;
  return (
    <div className="mt-3">
      <div className="text-[10px] uppercase tracking-widest text-white/40 mb-1">
        Son kapanan işlemler
      </div>
      <ul className="space-y-0.5 text-[11px]">
        {trades.slice(0, 4).map((t) => (
          <li key={t.id} className="flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <span className="font-medium">{t.symbol}</span>
              <span className={t.side === "long" ? "text-signal-up" : "text-signal-down"}>
                {t.side}
              </span>
              <span className="rounded border border-white/10 px-1 text-[8px] uppercase tracking-wide text-white/45">
                {t.close_reason}
              </span>
            </span>
            <span className={`tabular-nums ${pnlTone(t.pnl_usd)}`}>
              {fmtSignedUSD(t.pnl_usd)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function TradingPanel() {
  const { data, isLoading } = usePaperTradingState();
  const { data: corr } = useRiskCorrelation();
  const { data: halts } = useRiskHalts();
  const haltLevel = selectHaltLevel(halts);
  if (isLoading) {
    return (
      <PanelFrame id="trading">
        <PanelHeader title="Paper Trading" />
        <LoadingState />
      </PanelFrame>
    );
  }
  if (!data) {
    return (
      <PanelFrame id="trading">
        <PanelHeader title="Paper Trading" />
        <EmptyState />
      </PanelFrame>
    );
  }
  // Pure passthrough: backend recent_trades[].pnl_usd dizisi — kümülatif
  // equity reconstruction YOK (eski `equity - realized` heuristiği kaldırıldı).
  const recentPnl = (data.recent_trades ?? []).map((t) => t.pnl_usd);
  return (
    <PanelFrame id="trading">
      <PanelHeader
        title="Paper Trading"
        subtitle={`${data.open_positions.length} açık · ${data.recent_trades.length} kapanmış`}
        actions={
          haltLevel ? (
            <span
              className={`rounded px-1.5 py-0.5 uppercase tracking-wide text-[10px] ${
                haltLevel === "KILL_SWITCH"
                  ? "bg-signal-down/20 text-signal-down"
                  : "bg-amber-400/20 text-amber-400"
              }`}
            >
              RISK FREEZE · {haltLevel}
            </span>
          ) : undefined
        }
      />
      {/* Codex ticker chip satırı — bölünmüş mono stat'ler. */}
      <div className="flex items-stretch divide-x divide-white/10 border-b border-white/5 pb-3">
        <Chip label="Equity" value={fmtUSD(data.equity_usd)} tone="text-accent-cyan" />
        <Chip
          label="Realized"
          value={fmtSignedUSD(data.realized_pnl_usd)}
          tone={pnlTone(data.realized_pnl_usd)}
        />
        {data.unrealized_pnl_usd != null && (
          <Chip
            label="Unrealized"
            value={fmtSignedUSD(data.unrealized_pnl_usd)}
            tone={pnlTone(data.unrealized_pnl_usd)}
          />
        )}
        <Chip label="Açık" value={String(data.open_positions.length)} tone="text-white/90" />
      </div>

      {recentPnl.length > 1 && (
        <div className={`mt-3 ${pnlTone(data.realized_pnl_usd)}`}>
          <div className="text-[8px] font-mono uppercase tracking-wider text-white/40 mb-0.5">
            Son işlem PnL'leri
          </div>
          <SparkLine data={recentPnl} width={320} height={48} />
        </div>
      )}

      <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
        <Stat label="Max Drawdown" value={fmtPct(data.max_drawdown_pct)} />
        <Stat label="Sharpe 30g" value={fmtNum(data.sharpe_30d)} />
      </div>

      <OpenPositions positions={data.open_positions} />
      <RecentTrades trades={data.recent_trades} />
      <ClusterExposure corr={corr} />
    </PanelFrame>
  );
}

/** G4 — aynı yönlü korelasyonlu cluster exposure (backend hesaplar). */
function ClusterExposure({
  corr,
}: {
  corr: Parameters<typeof selectFlaggedClusters>[0];
}) {
  const flagged = selectFlaggedClusters(corr);
  if (!flagged.length) return null;
  const { maxClusterPct } = selectLimits(corr);
  return (
    <div className="mt-2 space-y-1 text-[11px]">
      {flagged.map((c) => (
        <div
          key={c.symbols.join("|")}
          className={c.status === "BREACH" ? "text-signal-down" : "text-amber-400"}
        >
          cluster {c.symbols.join("+")} · {fmtPct(c.cluster_pct, 1)} /{" "}
          {fmtPct(maxClusterPct, 0)} · {c.status}
        </div>
      ))}
    </div>
  );
}

function Stat({
  label,
  value,
  className = "",
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-white/40">{label}</div>
      <div className={`text-sm tabular-nums ${className || "text-white/90"}`}>{value}</div>
    </div>
  );
}
