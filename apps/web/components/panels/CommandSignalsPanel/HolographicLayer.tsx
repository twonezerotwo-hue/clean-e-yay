"use client";

/**
 * Holographic Command Signals — kurumsal seviye görsel.
 *
 * Veri: parent'tan gelen HoloSignal[] (holo-adapter.ts).
 * Kart carousel + detay paneli (per-TF teknik tablosu) + destek göstergeleri.
 * Karar üretmez. PAPER_SAFE / NO_EXECUTION.
 */
import { useEffect, useState } from "react";

import type { Timeframe } from "@/types/generated/api";

import type { HoloSignal } from "./holo-adapter";

// ── Config ────────────────────────────────────────────────────────────────────

const PRIMARY: Array<{ code: string; icon: string; name: string }> = [
  { code: "BTCUSD", icon: "₿",  name: "Bitcoin" },
  { code: "ETHUSD", icon: "Ξ",  name: "Ethereum" },
  { code: "XAUUSD", icon: "◆",  name: "Altın" },
  { code: "XAGUSD", icon: "Ag", name: "Gümüş" },
];

const SUPPORT_CODES = ["DXY", "VIX", "SP500", "QQQ", "HYG", "REAL_YIELD", "BRENT"];

const DETAIL_TFS: Timeframe[] = ["15m", "1h", "4h", "1d"];

type Tone = "approved" | "waiting" | "neutral" | "risk";

// Kurumsal palet — toned-down, gaming-neon değil.
const TONE: Record<Tone, {
  ring: string; accent: string; border: string; badge: string; text: string; label: string;
}> = {
  approved: {
    ring:   "#10b981",
    accent: "rgba(16,185,129,0.35)",
    border: "border-emerald-600/40",
    badge:  "bg-emerald-950/40 border-emerald-600/40 text-emerald-200",
    text:   "text-emerald-300",
    label:  "Onaylı",
  },
  waiting: {
    ring:   "#d97706",
    accent: "rgba(217,119,6,0.30)",
    border: "border-amber-600/40",
    badge:  "bg-amber-950/40 border-amber-600/40 text-amber-200",
    text:   "text-amber-200",
    label:  "Bekliyor",
  },
  neutral: {
    ring:   "#64748b",
    accent: "rgba(100,116,139,0.25)",
    border: "border-slate-600/40",
    badge:  "bg-slate-900/50 border-slate-600/40 text-slate-300",
    text:   "text-slate-300",
    label:  "Nötr",
  },
  risk: {
    ring:   "#dc2626",
    accent: "rgba(220,38,38,0.30)",
    border: "border-red-600/40",
    badge:  "bg-red-950/40 border-red-600/40 text-red-200",
    text:   "text-red-300",
    label:  "Blokeli",
  },
};

function toneOf(s: HoloSignal): Tone {
  if (s.status === "BLOCKING") return "risk";
  if (s.status === "CONFIRMED") return "approved";
  if (s.status === "PENDING") return "waiting";
  return "neutral";
}

function dirOf(s: HoloSignal): { label: string; cls: string } {
  const a = s.asset_action;
  if (a === "LONG")        return { label: "Long",          cls: "bg-emerald-700/30 text-emerald-200 border-emerald-600/40" };
  if (a === "LONG_AWAIT")  return { label: "Long Setup",    cls: "bg-emerald-900/30 text-emerald-300/80 border-emerald-700/30" };
  if (a === "SHORT")       return { label: "Short",         cls: "bg-red-700/30 text-red-200 border-red-600/40" };
  if (a === "SHORT_AWAIT") return { label: "Short Setup",   cls: "bg-red-900/30 text-red-300/80 border-red-700/30" };
  if (a === "AVOID")       return { label: "Kaçın",         cls: "bg-red-950/40 text-red-300/90 border-red-700/30" };
  return { label: "Gözlem", cls: "bg-slate-800/40 text-slate-300 border-slate-600/40" };
}

function fmtVal(v: number | null, unit: string): string {
  if (v == null) return "—";
  const s = v >= 1000
    ? v.toLocaleString("en-US", { maximumFractionDigits: 0 })
    : v.toLocaleString("en-US", { maximumFractionDigits: 2 });
  return unit === "USD" || unit === "$" ? `$${s}` : s;
}

function fmtNum(v: number | null | undefined, digits = 1): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return v.toLocaleString("en-US", { maximumFractionDigits: digits });
}

// ── Score ring ────────────────────────────────────────────────────────────────

function ScoreRing({ score, color, size }: { score: number | null; color: string; size: number }) {
  const r = size / 2 - 4;
  const c = 2 * Math.PI * r;
  const pct = score == null ? 0 : Math.max(0, Math.min(100, score));
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(148,163,184,0.20)" strokeWidth="2.5" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="2.5"
        strokeLinecap="round" strokeDasharray={`${(pct / 100) * c} ${c}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: "stroke-dasharray 0.6s ease" }} />
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle"
        fontSize={size * 0.32} fontFamily="ui-sans-serif, system-ui" fontWeight={600} fill="rgba(226,232,240,0.95)">
        {score == null ? "—" : Math.round(pct)}
      </text>
    </svg>
  );
}

// ── Holo card ─────────────────────────────────────────────────────────────────

function HoloCard({
  signal, icon, selected, animate, onClick,
}: {
  signal: HoloSignal; icon: string; name: string;
  selected: boolean; animate: boolean; onClick: () => void;
}) {
  const tone = TONE[toneOf(signal)];
  const dir  = dirOf(signal);
  const delta = signal.delta_7d_pct;
  return (
    <div className="relative" style={{ perspective: "1200px" }}>
      <button
        type="button"
        onClick={onClick}
        data-testid={`cs-card-${signal.asset_code}`}
        className={`relative w-full text-left rounded-lg border backdrop-blur-md px-3 py-2.5 transition-all duration-500 min-h-[136px] ${tone.border} ${
          selected ? "z-20" : "opacity-90 hover:opacity-100"
        }`}
        style={{
          background: selected
            ? "linear-gradient(160deg, rgba(15,23,42,0.94), rgba(2,6,23,0.96))"
            : "linear-gradient(165deg, rgba(15,23,42,0.78), rgba(2,6,23,0.92))",
          boxShadow: selected
            ? `0 12px 28px -10px ${tone.accent}, inset 0 1px 0 rgba(255,255,255,0.05)`
            : "0 4px 12px rgba(0,0,0,0.30), inset 0 1px 0 rgba(255,255,255,0.03)",
          transform: selected
            ? "translateY(-3px) scale(1.03)"
            : "translateZ(0) scale(0.97)",
          transformStyle: "preserve-3d",
        }}
      >
        {/* Subtle top accent */}
        <div aria-hidden="true" className="absolute inset-x-0 top-0 h-px"
             style={{ background: `linear-gradient(90deg, transparent, ${tone.ring}, transparent)`, opacity: selected ? 1 : 0.45 }} />

        {/* Header: icon + code + status dot */}
        <div className="flex items-center gap-2 mb-2">
          <span className="text-base leading-none text-slate-200">{icon}</span>
          <p className="text-[12px] font-semibold text-slate-100 tracking-wide leading-none">
            {signal.asset_code}
          </p>
          <span aria-hidden="true" className="ml-auto w-1.5 h-1.5 rounded-full shrink-0"
                style={{ background: tone.ring }} />
        </div>

        {/* Price */}
        <p className="text-[16px] font-semibold leading-tight tracking-tight text-slate-100">
          {fmtVal(signal.value, signal.unit)}
        </p>

        {/* Delta + status label */}
        <div className="flex items-center justify-between mt-1.5">
          {delta != null ? (
            <p className={`text-[10px] font-mono ${delta >= 0 ? "text-emerald-300" : "text-red-300"}`}>
              {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}%
            </p>
          ) : <span className="text-[10px] text-slate-500">—</span>}
          <span className={`rounded px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider border ${tone.badge}`}>
            {tone.label}
          </span>
        </div>

        {/* Confidence ring + dir badge */}
        <div className="flex items-center justify-between mt-2.5 pt-2 border-t border-white/5">
          <ScoreRing score={signal.consensus_score} color={tone.ring} size={selected ? 38 : 34} />
          <span className={`rounded px-2 py-0.5 text-[10px] font-medium border ${dir.cls}`}>
            {dir.label}
          </span>
        </div>
      </button>
    </div>
  );
}

// ── Per-TF detail table ───────────────────────────────────────────────────────

function emaTone(stack: string | null | undefined): string {
  if (stack === "bullish") return "text-emerald-300";
  if (stack === "bearish") return "text-red-300";
  return "text-slate-400";
}

function tfRowTone(score: number): string {
  if (score >= 60) return "text-emerald-300";
  if (score <= 40) return "text-red-300";
  return "text-slate-300";
}

function TfTable({ signal }: { signal: HoloSignal }) {
  return (
    <div className="space-y-1.5">
      <p className="text-[9px] font-medium uppercase tracking-[0.18em] text-slate-400">
        Timeframe Detayı
      </p>
      <div className="rounded-md border border-slate-700/40 bg-black/30 overflow-hidden">
        <table className="w-full text-[10px]">
          <thead className="bg-white/[0.02]">
            <tr className="text-slate-500">
              <th className="text-left px-2 py-1 font-medium">TF</th>
              <th className="text-right px-2 py-1 font-medium">RSI</th>
              <th className="text-right px-2 py-1 font-medium">MACD</th>
              <th className="text-right px-2 py-1 font-medium">ATR</th>
              <th className="text-right px-2 py-1 font-medium">EMA</th>
              <th className="text-right px-2 py-1 font-medium">Skor</th>
            </tr>
          </thead>
          <tbody>
            {DETAIL_TFS.map((tf) => {
              const t = signal.technicals[tf];
              if (!t) {
                return (
                  <tr key={tf} className="border-t border-white/5">
                    <td className="px-2 py-1 text-slate-400 font-mono">{tf}</td>
                    <td colSpan={5} className="px-2 py-1 text-right text-slate-600 italic">
                      veri yok
                    </td>
                  </tr>
                );
              }
              const score = t.score ?? 0;
              return (
                <tr key={tf} className="border-t border-white/5">
                  <td className="px-2 py-1 font-mono text-slate-300">{tf}</td>
                  <td className="px-2 py-1 text-right font-mono text-slate-200">{fmtNum(t.rsi, 0)}</td>
                  <td className="px-2 py-1 text-right font-mono text-slate-200">{fmtNum(t.macd, 2)}</td>
                  <td className="px-2 py-1 text-right font-mono text-slate-200">{fmtNum(t.atr, 2)}</td>
                  <td className={`px-2 py-1 text-right font-mono ${emaTone(t.ema_stack)}`}>
                    {t.ema_stack ?? "—"}
                  </td>
                  <td className={`px-2 py-1 text-right font-mono font-semibold ${tfRowTone(score)}`}>
                    {score.toFixed(0)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Detail panel ──────────────────────────────────────────────────────────────

function DetailPanel({ signal }: { signal: HoloSignal }) {
  const tone = TONE[toneOf(signal)];
  const dir  = dirOf(signal);
  return (
    <div className="rounded-lg border border-slate-700/40 bg-black/30 p-3 space-y-3" data-testid="cs-detail-panel">
      {/* Asset header */}
      <div className="flex items-center justify-between">
        <p className="text-[12px] font-semibold tracking-wide text-slate-100">{signal.asset_code}</p>
        <span className={`rounded px-2 py-0.5 text-[10px] font-medium border ${dir.cls}`}>
          {dir.label}
        </span>
      </div>

      {/* Price + reason */}
      <div className="space-y-1">
        <p className={`text-lg font-semibold tracking-tight ${tone.text}`}>
          {fmtVal(signal.value, signal.unit)}
        </p>
        <p className="text-[10px] text-slate-400 leading-snug">{signal.reason}</p>
      </div>

      {/* Per-TF table */}
      <TfTable signal={signal} />

      {/* Action trigger / plan if present */}
      {signal.action_trigger && (
        <p className="text-[10px] text-cyan-300/80 border border-cyan-800/30 bg-cyan-950/20 rounded px-2 py-1.5">
          ▶ {signal.action_trigger}
        </p>
      )}
      {signal.recommended_timeframe && (
        <p className="text-[10px] text-slate-400">
          Plan: {signal.recommended_timeframe.toUpperCase()}
          {signal.recheck_interval_minutes ? ` · kontrol ${signal.recheck_interval_minutes}dk` : ""}
        </p>
      )}
    </div>
  );
}

// ── Support strip ─────────────────────────────────────────────────────────────

function SupportBar({ s }: { s: HoloSignal }) {
  const tone = TONE[toneOf(s)];
  const delta = s.delta_7d_pct;
  return (
    <div className={`rounded border px-2 py-1 bg-black/30 shrink-0 flex items-center gap-2 ${tone.border}`}>
      <span aria-hidden="true" className="w-1 h-1 rounded-full" style={{ background: tone.ring }} />
      <p className="text-[10px] font-medium text-slate-300">{s.asset_code}</p>
      <p className="text-[10px] font-mono text-slate-100">{fmtVal(s.value, s.unit)}</p>
      {delta != null && (
        <p className={`text-[9px] font-mono ${delta >= 0 ? "text-emerald-300" : "text-red-300"}`}>
          {delta >= 0 ? "▲" : "▼"}{Math.abs(delta).toFixed(1)}%
        </p>
      )}
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

interface Props {
  signals: HoloSignal[];
}

export default function HolographicLayer({ signals }: Props) {
  const [selected, setSelected] = useState(0);
  const [animate,  setAnimate]  = useState(false);
  const [isMobile, setMobile]   = useState(false);
  const [paused,   setPaused]   = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setAnimate(!mq.matches);
    const onMQ = () => setAnimate(!mq.matches);
    mq.addEventListener?.("change", onMQ);
    setMobile(window.innerWidth < 640);
    const onResize = () => setMobile(window.innerWidth < 640);
    window.addEventListener("resize", onResize);
    return () => {
      mq.removeEventListener?.("change", onMQ);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  const byCode   = Object.fromEntries(signals.map((s) => [s.asset_code, s]));
  const primary  = PRIMARY.filter((p) => byCode[p.code] != null);
  const supports = SUPPORT_CODES.map((c) => byCode[c]).filter((s): s is HoloSignal => s != null);

  useEffect(() => {
    if (!animate || isMobile || paused || primary.length <= 1) return;
    const t = setInterval(() => {
      setSelected((s) => (s + 1) % primary.length);
    }, 5500);
    return () => clearInterval(t);
  }, [animate, isMobile, paused, primary.length]);

  if (primary.length === 0) {
    return (
      <div className="rounded-lg border border-slate-700/40 bg-slate-900/40 p-5" data-testid="cs-cards-layer">
        <p className="text-xs text-slate-500 italic">Komut sinyali kaydı yok.</p>
      </div>
    );
  }

  const safeSel = Math.min(selected, primary.length - 1);
  const selCode = primary[safeSel].code;
  const selSig  = byCode[selCode];

  return (
    <div
      className="w-full max-w-full min-w-0 rounded-lg border border-slate-700/50 bg-[#070d18] overflow-hidden"
      data-testid="cs-cards-layer"
    >
      {/* Header — minimalist kurumsal */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-700/40 bg-slate-900/40">
        <div className="flex items-center gap-2.5">
          <span className="w-1 h-3 rounded-full bg-cyan-500/60" aria-hidden="true" />
          <div>
            <p className="text-[11px] font-semibold text-slate-100 tracking-wide">
              Command Signals
            </p>
            <p className="text-[9px] text-slate-500 mt-0.5">
              {primary.length} ana asset · {supports.length} destek göstergesi
            </p>
          </div>
        </div>
        <span className="rounded border border-slate-600/40 bg-slate-800/40 px-1.5 py-0.5 text-[9px] font-medium text-slate-400 uppercase tracking-widest">
          paper · no execution
        </span>
      </div>

      <div
        className={isMobile ? "p-3 space-y-3" : "grid grid-cols-[minmax(0,1fr)_280px] gap-0"}
        style={isMobile ? undefined : { minHeight: "320px" }}
      >
        {/* Sol: kartlar sahnesi */}
        <div className="relative px-4 py-4 overflow-hidden bg-gradient-to-b from-slate-900/20 to-black/30">
          {/* Subtle dot grid */}
          <div aria-hidden="true" className="absolute inset-0 pointer-events-none opacity-25"
               style={{
                 backgroundImage: "radial-gradient(circle, rgba(148,163,184,0.18) 1px, transparent 1px)",
                 backgroundSize: "24px 24px",
                 maskImage: "radial-gradient(ellipse at 50% 60%, black 30%, transparent 80%)",
                 WebkitMaskImage: "radial-gradient(ellipse at 50% 60%, black 30%, transparent 80%)",
               }}
          />

          {/* Kartlar */}
          {!isMobile ? (
            <div
              className="relative z-10 h-[260px] overflow-hidden"
              style={{ perspective: "1800px", perspectiveOrigin: "50% 45%" }}
              onMouseEnter={() => setPaused(true)}
              onMouseLeave={() => setPaused(false)}
              onFocusCapture={() => setPaused(true)}
              onBlurCapture={() => setPaused(false)}
            >
              {primary.map((p, i) => {
                const n = primary.length;
                let offset = i - safeSel;
                if (offset > n / 2) offset -= n;
                if (offset < -n / 2) offset += n;
                const abs = Math.abs(offset);
                // Daha geniş aralık, daha az aşırı rotasyon — kurumsal his.
                const tx  = abs === 0 ? 0 : (abs === 1 ? 220 : 380) * (offset > 0 ? 1 : -1);
                const tz  = -abs * 30;
                const ry  = offset * -4;
                const sc  = abs === 0 ? 1.03 : abs === 1 ? 0.90 : 0.80;
                const op  = abs === 0 ? 1    : abs === 1 ? 0.75 : 0.45;
                const blur = abs === 2 ? "blur(0.5px)" : "none";
                return (
                  <div
                    key={p.code}
                    className="absolute top-2 left-1/2 transition-all duration-700 ease-out"
                    style={{
                      width: "200px",
                      marginLeft: "-100px",
                      transform: `translateX(${tx}px) translateZ(${tz}px) rotateY(${ry}deg) scale(${sc})`,
                      opacity: op,
                      zIndex: 100 - abs,
                      transformStyle: "preserve-3d",
                      pointerEvents: abs > 2 ? "none" : "auto",
                      filter: blur,
                    }}
                  >
                    <HoloCard
                      signal={byCode[p.code]}
                      icon={p.icon}
                      name={p.name}
                      selected={i === safeSel}
                      animate={animate}
                      onClick={() => setSelected(i)}
                    />
                  </div>
                );
              })}
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-2 px-1">
                <button
                  type="button"
                  onClick={() => setSelected((safeSel - 1 + primary.length) % primary.length)}
                  className="rounded border border-slate-600/40 bg-slate-800/40 px-2 py-0.5 text-slate-300 text-[11px]"
                  aria-label="Önceki"
                >‹</button>
                <span className="text-[10px] font-mono text-slate-400">
                  {safeSel + 1}/{primary.length}
                </span>
                <button
                  type="button"
                  onClick={() => setSelected((safeSel + 1) % primary.length)}
                  className="rounded border border-slate-600/40 bg-slate-800/40 px-2 py-0.5 text-slate-300 text-[11px]"
                  aria-label="Sonraki"
                >›</button>
              </div>
              <div className="flex gap-3 overflow-x-auto pb-3 -mx-1 px-1 relative z-10 snap-x snap-mandatory">
                {primary.map((p, i) => (
                  <div key={p.code} className="w-[180px] shrink-0 snap-center">
                    <HoloCard
                      signal={byCode[p.code]}
                      icon={p.icon}
                      name={p.name}
                      selected={i === safeSel}
                      animate={false}
                      onClick={() => setSelected(i)}
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Tab indicators (selected position) */}
          {!isMobile && (
            <div className="flex justify-center gap-1.5 mt-2 relative z-10">
              {primary.map((p, i) => (
                <button
                  key={p.code}
                  type="button"
                  onClick={() => setSelected(i)}
                  aria-label={p.code}
                  className={`h-1 rounded-full transition-all ${
                    i === safeSel ? "w-8 bg-cyan-400/80" : "w-2 bg-slate-600/60 hover:bg-slate-500"
                  }`}
                />
              ))}
            </div>
          )}
        </div>

        {/* Sağ: detay paneli — per-TF tablo */}
        <div className={isMobile
          ? ""
          : "relative border-l border-slate-700/40 p-3 bg-slate-950/40 min-h-0 h-full overflow-hidden flex flex-col"
        }>
          <p className="text-[9px] font-medium text-slate-500 uppercase tracking-[0.18em] mb-2 shrink-0">
            Sinyal Detayı
          </p>
          <div className={isMobile ? "" : "flex-1 min-h-0 overflow-y-auto pr-1 -mr-1"}>
            <DetailPanel signal={selSig} />
          </div>
        </div>
      </div>

      {/* Destek göstergeleri — ticker */}
      {supports.length > 0 && (
        <div className="px-4 py-2.5 border-t border-slate-700/40 bg-slate-900/30">
          <p className="text-[9px] font-medium text-slate-500 uppercase tracking-[0.18em] mb-1.5">
            Piyasa Göstergeleri
          </p>
          {animate ? (
            <div className="relative overflow-hidden"
                 style={{
                   maskImage: "linear-gradient(90deg, transparent, black 6%, black 94%, transparent)",
                   WebkitMaskImage: "linear-gradient(90deg, transparent, black 6%, black 94%, transparent)",
                 }}>
              <div className="flex gap-2 w-max will-change-transform"
                   style={{
                     animation: `cs-ticker ${Math.max(20, supports.length * 5)}s linear infinite`,
                     animationPlayState: paused ? "paused" : "running",
                   }}
                   onMouseEnter={() => setPaused(true)}
                   onMouseLeave={() => setPaused(false)}>
                {[...supports, ...supports].map((s, i) => (
                  <SupportBar key={`${s.asset_code}-${i}`} s={s} />
                ))}
              </div>
              <style>{`
                @keyframes cs-ticker { from { transform: translateX(0) } to { transform: translateX(-50%) } }
              `}</style>
            </div>
          ) : (
            <div className="flex gap-2 flex-wrap">
              {supports.map((s) => <SupportBar key={s.asset_code} s={s} />)}
            </div>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="px-4 py-2 border-t border-slate-700/40 bg-slate-900/40">
        <p className="text-[9px] text-slate-500 text-center">
          Yalnız görselleştirme · karar üretmez · final karar deterministik engine + RiskGate
        </p>
      </div>
    </div>
  );
}
