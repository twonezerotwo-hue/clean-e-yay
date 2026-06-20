"use client";

import { useMemo, useState } from "react";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useTradeTickets } from "@/lib/queries/hooks";
import type { TradeTicket, TradeTicketSummary } from "@/types/generated/api";

// ── helpers ───────────────────────────────────────────────────────────────────

function fmtUSD(n: number | undefined): string {
  if (n === undefined || n === null || isNaN(n)) return "—";
  if (Math.abs(n) >= 1000)
    return `$${n.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
  return `$${n.toFixed(2)}`;
}

function fmtPx(n: number | undefined): string {
  if (n === undefined || n === null || isNaN(n)) return "—";
  return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function fmtPct(n: number | undefined, digits = 2): string {
  if (n === undefined || n === null || isNaN(n)) return "—";
  return `${n.toFixed(digits)}%`;
}

function sideEmoji(side: string): string {
  return side === "long" ? "🟢" : side === "short" ? "🔴" : "⚪";
}

function sideLabel(side: string): string {
  return side === "long" ? "AL" : side === "short" ? "SAT" : "BEKLE";
}

function confidenceColor(p: number): string {
  if (p >= 0.70) return "bg-emerald-500";
  if (p >= 0.60) return "bg-emerald-400";
  if (p >= 0.50) return "bg-amber-400";
  return "bg-orange-400";
}

function confidenceWidthPct(p: number): number {
  return Math.max(2, Math.min(100, p * 100));
}

// SL/TP yüzde + dolar — entry'e göre.
function priceMetrics(side: string, entry: number, sl: number, tp: number, sizeUsd: number) {
  if (!entry) return { slPct: 0, tpPct: 0, slUsd: 0, tpUsd: 0 };
  const slDist = side === "long" ? entry - sl : sl - entry;
  const tpDist = side === "long" ? tp - entry : entry - tp;
  const slPct = (slDist / entry) * 100;
  const tpPct = (tpDist / entry) * 100;
  const slUsd = (slPct / 100) * sizeUsd;
  const tpUsd = (tpPct / 100) * sizeUsd;
  return { slPct: -Math.abs(slPct), tpPct: Math.abs(tpPct), slUsd: -Math.abs(slUsd), tpUsd: Math.abs(tpUsd) };
}

// ── safety lines ──────────────────────────────────────────────────────────────

function SafetyLine({ level, text }: { level: string; text: string }) {
  const icon = level === "ok" ? "✓" : level === "warn" ? "⚠" : "✗";
  const cls =
    level === "ok"
      ? "text-emerald-300"
      : level === "warn"
        ? "text-amber-300"
        : "text-red-300";
  return (
    <div className={`flex items-start gap-2 text-xs ${cls}`}>
      <span className="font-mono shrink-0">{icon}</span>
      <span className="leading-snug">{text}</span>
    </div>
  );
}

// ── technical detail (collapsed) ──────────────────────────────────────────────

function DetailRow({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="flex items-baseline gap-3 py-0.5">
      <span className="text-[10px] font-mono text-white/40 w-28 shrink-0">{label}</span>
      <span className="text-xs text-white/85 font-mono">{value}</span>
      {hint ? <span className="text-[10px] text-white/35 italic">{hint}</span> : null}
    </div>
  );
}

function DetailSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-4 first:mt-0">
      <h4 className="text-[11px] font-mono uppercase tracking-widest text-accent-cyan/80 mb-1 pb-1 border-b border-white/10">
        {title}
      </h4>
      <div className="space-y-0">{children}</div>
    </section>
  );
}

function TechnicalDetail({ t }: { t: TradeTicket }) {
  const td = (t.technical_detail ?? {}) as Record<string, any>;
  const cons = (td.consensus ?? {}) as Record<string, any>;
  const market = (td.market_state ?? {}) as Record<string, any>;
  const sizing = (td.position_sizing ?? {}) as Record<string, any>;
  const calib = (td.calibration ?? {}) as Record<string, any>;
  const safety = (td.safety_checks ?? {}) as Record<string, any>;
  const fp = (td.fingerprint_history ?? {}) as Record<string, any>;
  const audit = (td.audit ?? {}) as Record<string, any>;
  const modules: any[] = Array.isArray(cons.modules) ? cons.modules : [];

  return (
    <div className="mt-3 rounded-lg border border-white/10 bg-black/30 p-3">
      <DetailSection title="1. Sinyal nasıl oluştu">
        <DetailRow label="Final puan" value={`${(cons.final_score ?? 0).toFixed(1)} / 100`} hint={`yön: ${cons.direction ?? "?"}`} />
        <DetailRow label="Uyum" value={cons.confluence_aligned ? "✓ 3+ modül aynı yönde" : "henüz uyum yok"} />
        <DetailRow label="Dominant" value={cons.dominant_module || "—"} />
        {modules.length > 0 && (
          <div className="mt-2">
            <div className="text-[10px] font-mono text-white/40 mb-1">Modül katkıları</div>
            <table className="w-full text-[10px] font-mono">
              <thead className="text-white/40">
                <tr>
                  <th className="text-left">Modül</th>
                  <th className="text-right">Skor</th>
                  <th className="text-right">Ağırlık</th>
                  <th className="text-right">Katkı</th>
                </tr>
              </thead>
              <tbody>
                {modules.map((m) => (
                  <tr key={m.name} className="border-t border-white/5">
                    <td className="text-white/70">{m.label ?? m.name}</td>
                    <td className="text-right">{Number(m.score).toFixed(1)}</td>
                    <td className="text-right">{Number(m.weight).toFixed(3)}</td>
                    <td className="text-right">{Number(m.contribution).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DetailSection>

      <DetailSection title="2. Şu an piyasada">
        <DetailRow label="Sembol/TF" value={`${market.symbol ?? t.symbol} · ${(market.timeframe ?? t.timeframe).toUpperCase()}`} />
        <DetailRow label="RSI" value={market.rsi !== null && market.rsi !== undefined ? Number(market.rsi).toFixed(2) : "—"} hint="50 nötr · 70+ alım fazlası · 30- satım fazlası" />
        <DetailRow label="MACD" value={market.macd !== null && market.macd !== undefined ? Number(market.macd).toFixed(3) : "—"} hint="histogram normalize" />
        <DetailRow label="ATR" value={market.atr !== null && market.atr !== undefined ? fmtPx(Number(market.atr)) : "—"} hint="ortalama bar hareketi" />
        <DetailRow label="EMA stack" value={market.ema_stack ?? "—"} />
        <DetailRow label="Teknik skor" value={market.technical_score !== null && market.technical_score !== undefined ? Number(market.technical_score).toFixed(1) : "—"} hint={`durum: ${market.technical_status ?? "?"}`} />
        {market.support !== null && market.support !== undefined && (
          <DetailRow label="Destek" value={fmtPx(Number(market.support))} />
        )}
        {market.resistance !== null && market.resistance !== undefined && (
          <DetailRow label="Direnç" value={fmtPx(Number(market.resistance))} />
        )}
        <DetailRow label="DQS" value={market.dqs_score !== null && market.dqs_score !== undefined ? `${Number(market.dqs_score).toFixed(0)} / 100` : "—"} />
      </DetailSection>

      <DetailSection title="3. Bu sinyal geçmişte ne yaptı">
        <DetailRow label="Fingerprint" value={<code className="text-[10px]">{fp.fingerprint ?? "—"}</code>} />
        <DetailRow label="Mistake verdict" value={JSON.stringify(fp.mistake_verdict ?? {}) || "—"} />
      </DetailSection>

      <DetailSection title="4. Güvenlik kontrolleri">
        <DetailRow label="RiskGate" value={safety.risk_action ?? "—"} hint={safety.risk_reason ?? undefined} />
        <DetailRow label="Equity" value={fmtUSD(Number(safety.equity_usd))} />
        <DetailRow label="Peak equity" value={fmtUSD(Number(safety.peak_equity_usd))} />
        <DetailRow label="Daily PnL" value={fmtUSD(Number(safety.daily_pnl_usd))} />
        <DetailRow label="Açık pozisyon" value={`${safety.open_position_count ?? 0}`} />
        {Array.isArray(safety.blocked_by) && safety.blocked_by.length > 0 && (
          <DetailRow label="Blocked by" value={safety.blocked_by.join(", ")} />
        )}
      </DetailSection>

      <DetailSection title="5. Pozisyon sizing">
        <DetailRow label="Size multiplier" value={Number(sizing.size_multiplier ?? 0).toFixed(3)} />
        <DetailRow label="SL basis" value={`${sizing.sl_basis ?? "—"} (mesafe ${fmtPx(Number(sizing.sl_distance ?? 0))})`} />
        <DetailRow label="TP basis" value={String(sizing.tp_basis ?? "—")} hint={`R/R 1:${Number(sizing.rr ?? 0).toFixed(2)}`} />
        <DetailRow label="R/R floor" value={sizing.rr_floor_met ? "✓ sağlandı" : "✗ yetersiz"} />
        {Array.isArray(sizing.notes) && sizing.notes.length > 0 && (
          <div className="mt-1 text-[10px] text-white/40 italic leading-snug">
            {sizing.notes.join(" · ")}
          </div>
        )}
      </DetailSection>

      <DetailSection title="6. Kalibrasyon">
        <DetailRow label="Raw" value={`${(Number(calib.raw_confidence ?? 0) * 100).toFixed(1)}%`} hint="ham (kalibre öncesi)" />
        <DetailRow label="Calibrated" value={`${(Number(calib.calibrated_confidence ?? 0) * 100).toFixed(1)}%`} hint={`source: ${calib.source ?? "?"}`} />
      </DetailSection>

      <DetailSection title="7. Denetim izi">
        <DetailRow label="Ticket ID" value={<code className="text-[10px]">{t.id}</code>} />
        <DetailRow label="Snapshot ID" value={<code className="text-[10px]">{audit.snapshot_id ?? "—"}</code>} />
        <DetailRow label="Fingerprint" value={<code className="text-[10px]">{audit.fingerprint ?? "—"}</code>} />
        <DetailRow label="Action" value={`${audit.candidate_action ?? "?"} → ${audit.final_action ?? "?"}`} />
        <DetailRow label="Expires at" value={t.expires_at} />
      </DetailSection>
    </div>
  );
}

// ── single ticket card ────────────────────────────────────────────────────────

function TicketCard({ t }: { t: TradeTicket }) {
  const [showDetail, setShowDetail] = useState(false);
  const s = t.summary as TradeTicketSummary;
  const metrics = useMemo(
    () => priceMetrics(t.side, s.entry_price, s.stop_loss, s.take_profit, s.size_usd),
    [t.side, s.entry_price, s.stop_loss, s.take_profit, s.size_usd],
  );
  const confidence = s.confidence_calibrated ?? 0;

  return (
    <div className="rounded-xl border border-white/10 bg-ink-800/60 p-4 space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-base font-semibold tracking-tight">
            {sideEmoji(t.side)} {t.symbol} {sideLabel(t.side)} ·{" "}
            <span className="text-white/60">{t.timeframe.toUpperCase()} Timeframe Sinyal</span>
          </div>
          <div className="text-[11px] text-white/40 mt-0.5">{t.display?.expiry_text ?? ""}</div>
        </div>
      </div>

      {/* Prices */}
      <div className="grid grid-cols-3 gap-3 text-xs">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-white/40">Şu fiyattan gir</div>
          <div className="text-white/90 font-mono text-base mt-0.5">{fmtPx(s.entry_price)} $</div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-widest text-white/40">Zarar kes (durduk)</div>
          <div className="text-red-300 font-mono text-base mt-0.5">{fmtPx(s.stop_loss)} $</div>
          <div className="text-[10px] text-white/50 mt-0.5">
            {fmtPct(metrics.slPct)} · {fmtUSD(metrics.slUsd)}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-widest text-white/40">Kâr al (çık)</div>
          <div className="text-emerald-300 font-mono text-base mt-0.5">{fmtPx(s.take_profit)} $</div>
          <div className="text-[10px] text-white/50 mt-0.5">
            +{fmtPct(metrics.tpPct)} · +{fmtUSD(metrics.tpUsd)}
          </div>
        </div>
      </div>

      {/* R/R */}
      <div className="text-xs">
        <div className="text-[10px] uppercase tracking-widest text-white/40">Risk / Kazanç</div>
        <div className="text-white/85 mt-0.5">{t.display?.rr_text ?? `1:${s.rr_ratio.toFixed(1)}`}</div>
        {t.display?.rr_note ? (
          <div className="text-[10px] text-white/40 italic mt-0.5">{t.display.rr_note}</div>
        ) : null}
      </div>

      <div className="h-px bg-white/10" />

      {/* Size */}
      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-white/40">Pozisyon büyüklüğü</div>
          <div className="text-white/90 font-mono text-base mt-0.5">{fmtUSD(s.size_usd)}</div>
          <div className="text-[10px] text-white/50 mt-0.5">
            hesabının {fmtPct(s.size_pct_equity, 2)}'i
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-widest text-white/40">Yanılırsam kaybım</div>
          <div className="text-white/90 font-mono text-base mt-0.5">{fmtUSD(s.risk_usd)}</div>
          <div className="text-[10px] text-white/50 mt-0.5">
            toplamın {fmtPct(s.risk_pct_equity, 3)}'ü
          </div>
        </div>
      </div>

      <div className="h-px bg-white/10" />

      {/* Confidence */}
      <div className="text-xs">
        <div className="text-[10px] uppercase tracking-widest text-white/40 mb-1">Bu sinyale güven</div>
        <div className="flex items-center gap-3">
          <div className="flex-1 h-2 rounded-full bg-white/10 overflow-hidden">
            <div
              className={`h-full ${confidenceColor(confidence)}`}
              style={{ width: `${confidenceWidthPct(confidence)}%` }}
            />
          </div>
          <span className="text-white/85 font-mono text-sm shrink-0">{t.display?.confidence_text ?? `${(confidence * 100).toFixed(0)}%`}</span>
        </div>
      </div>

      {/* Safety */}
      {Array.isArray(t.display?.safety_lines) && t.display.safety_lines.length > 0 && (
        <>
          <div className="h-px bg-white/10" />
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-widest text-white/40">Tüm güvenlik kontrolleri</div>
            {t.display.safety_lines.map((l, i) => (
              <SafetyLine key={i} level={l.level} text={l.text} />
            ))}
          </div>
        </>
      )}

      {/* Why */}
      {Array.isArray(t.display?.why_bullets) && t.display.why_bullets.length > 0 && (
        <>
          <div className="h-px bg-white/10" />
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-widest text-white/40">Neden bu sinyal?</div>
            <ul className="text-xs text-white/75 space-y-1 pl-1">
              {t.display.why_bullets.map((b, i) => (
                <li key={i}>• {b}</li>
              ))}
            </ul>
          </div>
        </>
      )}

      {/* Technical detail toggle */}
      <button
        type="button"
        onClick={() => setShowDetail((v) => !v)}
        className="text-[11px] font-mono text-accent-cyan/80 hover:text-accent-cyan"
      >
        {showDetail ? "▴ Teknik detayı gizle" : "▾ Teknik detay (tüm ham veriler)"}
      </button>
      {showDetail ? <TechnicalDetail t={t} /> : null}

      {/* Footer hint */}
      <div className="mt-2 rounded-md border border-white/10 bg-black/20 px-3 py-2 text-[11px] text-white/60">
        Broker'a girmeden önce kontrol et: şu anki fiyat hâlâ tetikte mi?
      </div>
    </div>
  );
}

// ── panel ─────────────────────────────────────────────────────────────────────

export function TradeTicketPanel() {
  const { data, isLoading } = useTradeTickets();
  if (isLoading) {
    return (
      <PanelFrame id="trade_ticket">
        <PanelHeader title="Trade Ticket" subtitle="broker'a manuel girmeden tek-bakış kart" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const tickets = data?.tickets ?? [];
  if (tickets.length === 0) {
    return (
      <PanelFrame id="trade_ticket">
        <PanelHeader title="Trade Ticket" subtitle="broker'a manuel girmeden tek-bakış kart" />
        <EmptyState message="Aktif Trade Ticket yok. Sinyaller bloklanmış ya da consensus eşiği aşılmadı." />
      </PanelFrame>
    );
  }
  return (
    <PanelFrame id="trade_ticket">
      <PanelHeader title="Trade Ticket" subtitle={`${tickets.length} aktif sinyal · broker handoff`} />
      <div className="space-y-3">
        {tickets.map((t) => (
          <TicketCard key={t.id} t={t} />
        ))}
      </div>
    </PanelFrame>
  );
}
