"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { QuantumPanelField, getQuantumPanelStyle } from "@/components/shell/QuantumPanelField";
import { MobileFlipCard } from "@/components/cockpit/MobileFlipCard";
import {
  useDataSnapshot,
  useDecisionMatrix,
  useRegimeReport,
  useTradeTickets,
} from "@/lib/queries/hooks";
import type {
  AgentBrief,
  AgentBriefCandidate,
  AssetSignal,
  LivePrice,
  TechnicalTf,
  Timeframe,
  TimeframeDecision,
  TradeTicket,
} from "@/types/generated/api";

// ── Config ────────────────────────────────────────────────────────────────────

const PRIMARY: Array<{ code: string; icon: string; name: string; unit: string }> = [
  { code: "BTCUSD", icon: "₿",  name: "Bitcoin",  unit: "usd" },
  { code: "ETHUSD", icon: "Ξ",  name: "Ethereum", unit: "usd" },
  { code: "XAUUSD", icon: "◆",  name: "Altın",    unit: "usd/oz" },
  { code: "XAGUSD", icon: "Ag", name: "Gümüş",    unit: "usd/oz" },
  { code: "BRENT",  icon: "●",  name: "Brent",    unit: "usd/bbl" },
];

const TF_ORDER: Timeframe[] = ["15m", "1h", "4h", "1d", "1w"];

// ── Helpers ───────────────────────────────────────────────────────────────────

function round(n: number | null | undefined): number {
  return Math.round(n ?? 0);
}

function scoreTone(value: number): string {
  if (value >= 75) return "text-emerald-300";
  if (value >= 55) return "text-teal-300";
  if (value >= 35) return "text-amber-300";
  return "text-slate-400";
}

function fmtPx(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  if (n >= 1000) return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (n >= 100)  return n.toLocaleString("en-US", { maximumFractionDigits: 1 });
  return n.toLocaleString("en-US", { maximumFractionDigits: 3 });
}

function tfIndex(tf?: Timeframe | string | null): number {
  if (!tf) return TF_ORDER.length;
  const i = TF_ORDER.indexOf(tf as Timeframe);
  return i === -1 ? TF_ORDER.length : i;
}

type Direction = "bullish" | "bearish" | "neutral";

type SignalCell = {
  symbol?: string;
  timeframe?: Timeframe;
  direction?: Direction;
  score?: number;
  candidate_action?: string;
  final_action?: string;
  action?: TimeframeDecision["action"];
  actionable?: boolean;
  status?: AgentBriefCandidate["status"] | TimeframeDecision["status"];
};

type DeckRow = {
  symbol: string;
  icon: string;
  name: string;
  unit: string;
  best: SignalCell;
  perTf: AgentBriefCandidate[];   // tüm TF adayları
  price: number | null;
};

function pickDeckRows(
  candidates: AgentBriefCandidate[],
  prices: LivePrice[] | undefined,
  matrixCells: TimeframeDecision[] | undefined,
): DeckRow[] {
  const priceBy = new Map<string, number>();
  for (const p of prices ?? []) {
    if (p.price != null && Number.isFinite(p.price)) priceBy.set(p.symbol, p.price);
  }
  // Sembol → tüm adaylar
  const groups = new Map<string, AgentBriefCandidate[]>();
  for (const c of candidates) {
    const sym = c.symbol ?? "";
    if (!sym) continue;
    const list = groups.get(sym) ?? [];
    list.push(c);
    groups.set(sym, list);
  }

  const bestByScore = (items: AgentBriefCandidate[]): AgentBriefCandidate =>
    items.reduce((a, b) => ((b.score ?? 0) > (a.score ?? 0) ? b : a));
  const sortByTf = (items: AgentBriefCandidate[]): AgentBriefCandidate[] =>
    [...items].sort((a, b) => tfIndex(a.timeframe) - tfIndex(b.timeframe));

  const matrixGroups = new Map<string, AgentBriefCandidate[]>();
  for (const cell of matrixCells ?? []) {
    const sym = cell.symbol ?? "";
    if (!sym) continue;
    const list = matrixGroups.get(sym) ?? [];
    list.push({
      symbol: cell.symbol,
      timeframe: cell.timeframe,
      direction: cell.direction,
      score: cell.score,
      candidate_action: cell.candidate_action ?? cell.action,
      final_action: cell.action,
      actionable: cell.actionable,
      status: cell.status,
    });
    matrixGroups.set(sym, list);
  }

  const rows: DeckRow[] = [];
  // PRIMARY sırası tercihi
  for (const p of PRIMARY) {
    const candidateRows = groups.get(p.code) ?? [];
    const matrixRows = matrixGroups.get(p.code) ?? [];
    const all = matrixRows.length ? sortByTf(matrixRows) : sortByTf(candidateRows);
    if (!all.length && !candidateRows.length) continue;
    const best = candidateRows.length ? bestByScore(candidateRows) : bestByScore(all);
    rows.push({
      symbol: p.code,
      icon: p.icon,
      name: p.name,
      unit: p.unit,
      best,
      perTf: all,
      price: priceBy.get(p.code) ?? null,
    });
    groups.delete(p.code);
    matrixGroups.delete(p.code);
  }
  // Geriye kalan semboller (skor sırasıyla)
  const remainingSymbols = new Set<string>([
    ...groups.keys(),
    ...matrixGroups.keys(),
  ]);
  const remaining = [...remainingSymbols].flatMap((symbol) => {
    const candidateRows = groups.get(symbol) ?? [];
    const matrixRows = matrixGroups.get(symbol) ?? [];
    const all = matrixRows.length ? sortByTf(matrixRows) : sortByTf(candidateRows);
    if (!all.length && !candidateRows.length) return [];
    const best = candidateRows.length ? bestByScore(candidateRows) : bestByScore(all);
    return {
      symbol,
      icon: "◇",
      name: symbol,
      unit: "usd",
      best,
      perTf: all,
      price: priceBy.get(symbol) ?? null,
    };
  });
  remaining.sort((a, b) => (b.best.score ?? 0) - (a.best.score ?? 0));
  return [...rows, ...remaining].slice(0, 6);
}

function pickSupports(assets: AssetSignal[] | undefined, prices: LivePrice[] | undefined): {
  symbol: string;
  unit: string;
  price: number | null;
  direction: Direction;
}[] {
  const primaryCodes = new Set(PRIMARY.map((p) => p.code));
  const priceBy = new Map<string, number>();
  for (const p of prices ?? []) {
    if (p.price != null && Number.isFinite(p.price)) priceBy.set(p.symbol, p.price);
  }
  const out: { symbol: string; unit: string; price: number | null; direction: Direction }[] = [];
  for (const a of assets ?? []) {
    if (primaryCodes.has(a.symbol)) continue;
    out.push({
      symbol: a.symbol,
      unit: "idx",
      price: priceBy.get(a.symbol) ?? null,
      direction: (a.direction ?? "neutral") as Direction,
    });
  }
  return out;
}

// ── Score ring (animated) ────────────────────────────────────────────────────

function ScoreRing({
  score,
  size = 56,
  active = false,
}: {
  score: number;
  size?: number;
  active?: boolean;
}) {
  const r = size / 2 - 5;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score));
  const tone =
    pct >= 75 ? "#22c55e" : pct >= 55 ? "#14b8a6" : pct >= 35 ? "#fbbf24" : "#94a3b8";
  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      aria-hidden="true"
      style={{ filter: active ? `drop-shadow(0 0 8px ${tone}aa)` : undefined }}
    >
      <defs>
        <linearGradient id={`ring-grad-${size}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={tone} stopOpacity="1" />
          <stop offset="100%" stopColor={tone} stopOpacity="0.45" />
        </linearGradient>
      </defs>
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="rgba(148,163,184,0.18)"
        strokeWidth="3"
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={`url(#ring-grad-${size})`}
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray={`${(pct / 100) * c} ${c}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: "stroke-dasharray 0.9s cubic-bezier(0.22, 1, 0.36, 1)" }}
      />
      <text
        x="50%"
        y="50%"
        dominantBaseline="central"
        textAnchor="middle"
        fontSize={size * 0.36}
        fontFamily="ui-sans-serif, system-ui"
        fontWeight={600}
        fill="rgba(241,245,249,0.96)"
      >
        {Math.round(pct)}
      </text>
    </svg>
  );
}

// ── Action badges ─────────────────────────────────────────────────────────────

function statusBadge(c: SignalCell): { label: string; cls: string } {
  const dir = (c.direction ?? "neutral") as Direction;
  const act = (c.candidate_action ?? "").toUpperCase();
  if (act.includes("ACTIONABLE") || c.actionable) {
    if (dir === "bullish") return { label: "ONAYLI", cls: "bg-emerald-500/15 border-emerald-400/40 text-emerald-200" };
    if (dir === "bearish") return { label: "ONAYLI", cls: "bg-rose-500/15 border-rose-400/40 text-rose-200" };
  }
  if (act === "AVOID" || act.includes("BLOCK"))
    return { label: "BLOKE", cls: "bg-rose-500/15 border-rose-400/40 text-rose-200" };
  if (dir === "bullish") return { label: "BEKLİYOR", cls: "bg-amber-400/15 border-amber-300/40 text-amber-200" };
  if (dir === "bearish") return { label: "BEKLİYOR", cls: "bg-amber-400/15 border-amber-300/40 text-amber-200" };
  return { label: "NÖTR", cls: "bg-slate-500/15 border-slate-400/40 text-slate-300" };
}

function actionBadge(c: SignalCell): { label: string; cls: string } {
  const dir = (c.direction ?? "neutral") as Direction;
  const actionable = c.actionable;
  if (actionable && dir === "bullish") return { label: "▲ LONG", cls: "bg-emerald-500/20 text-emerald-100 border-emerald-400/50" };
  if (actionable && dir === "bearish") return { label: "▼ SHORT", cls: "bg-rose-500/20 text-rose-100 border-rose-400/50" };
  if (dir === "bullish") return { label: "▲ LONG SETUP", cls: "bg-emerald-500/10 text-emerald-200/90 border-emerald-400/30" };
  if (dir === "bearish") return { label: "▼ SHORT SETUP", cls: "bg-rose-500/10 text-rose-200/90 border-rose-400/30" };
  return { label: "● WATCH", cls: "bg-teal-500/10 text-teal-100/85 border-teal-300/25" };
}

function cardTheme(score: number, direction: Direction) {
  if (direction === "bullish") {
    return {
      accent: "#22c55e",
      accent2: "#fbbf24",
      shadow: "rgba(34,197,94,0.38)",
      foil: "rgba(34,197,94,0.12)",
      label: "RISK-ON",
    };
  }
  if (direction === "bearish") {
    return {
      accent: "#fb7185",
      accent2: "#f59e0b",
      shadow: "rgba(251,113,133,0.36)",
      foil: "rgba(244,63,94,0.12)",
      label: "RISK-OFF",
    };
  }
  if (score >= 55) {
    return {
      accent: "#fbbf24",
      accent2: "#14b8a6",
      shadow: "rgba(251,191,36,0.32)",
      foil: "rgba(245,158,11,0.10)",
      label: "WATCH",
    };
  }
  return {
    accent: "#94a3b8",
    accent2: "#14b8a6",
    shadow: "rgba(148,163,184,0.26)",
    foil: "rgba(148,163,184,0.08)",
    label: "IDLE",
  };
}

function directionLabel(direction: Direction) {
  if (direction === "bullish") return "BULL";
  if (direction === "bearish") return "BEAR";
  return "NEUTRAL";
}

function archetype(row: DeckRow) {
  const action = row.best.candidate_action?.toUpperCase() ?? "";
  if (row.best.actionable) return "EXECUTION";
  if (action.includes("BLOCK") || action.includes("AVOID")) return "LOCKED";
  if (row.perTf.length >= 4) return "MULTI-TF";
  return "SCOUT";
}

// ── 3D card ───────────────────────────────────────────────────────────────────

function deckTransform(offset: number, compact = false): CSSProperties {
  const abs = Math.abs(offset);
  const txStep = compact
    ? abs === 1
      ? 124
      : abs === 2
        ? 210
        : 286
    : abs === 1
      ? 214
      : abs === 2
        ? 368
        : 500;
  const tx = offset === 0 ? 0 : txStep * (offset > 0 ? 1 : -1);
  const ty = abs === 0 ? -50 : abs === 1 ? -49 : -47;
  const tz = offset === 0 ? (compact ? 44 : 64) : -abs * (compact ? 82 : 118);
  const ry = offset * (compact ? -14 : -22);
  const rz = offset * (compact ? 1.4 : 2.4);
  const rx = abs === 0 ? -5 : -2;
  const scale = compact
    ? abs === 0
      ? 0.94
      : abs === 1
        ? 0.62
        : abs === 2
          ? 0.48
          : 0.36
    : abs === 0
      ? 1.06
      : abs === 1
        ? 0.74
        : abs === 2
          ? 0.56
          : 0.44;
  const op = abs === 0 ? 1 : abs === 1 ? 0.82 : abs === 2 ? 0.42 : 0.16;
  return {
    transform: `translate3d(calc(-50% + ${tx}px), ${ty}%, ${tz}px) rotateX(${rx}deg) rotateY(${ry}deg) rotateZ(${rz}deg) scale(${scale})`,
    opacity: op,
    zIndex: 200 - abs,
    pointerEvents: abs > 2 ? "none" : "auto",
    filter: abs >= 2 ? "blur(1.4px) saturate(0.65)" : "none",
  };
}

function DeckCard({
  row,
  active,
  offset,
  compact = false,
  onSelect,
}: {
  row: DeckRow;
  active: boolean;
  offset: number;
  compact?: boolean;
  onSelect: () => void;
}) {
  const value = round(row.best.score);
  const status = statusBadge(row.best);
  const action = actionBadge(row.best);
  const direction = (row.best.direction ?? "neutral") as Direction;
  const theme = cardTheme(value, direction);
  const style = {
    ...deckTransform(offset, compact),
    "--fut-accent": theme.accent,
    "--fut-accent-2": theme.accent2,
    "--fut-shadow": theme.shadow,
    "--fut-foil": theme.foil,
    transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)",
    transitionDuration: compact ? "900ms" : undefined,
    transformStyle: "preserve-3d",
    width: compact ? 190 : undefined,
    borderColor: active ? theme.accent : "rgba(71,85,105,0.38)",
    boxShadow: active
      ? `0 20px 58px -18px ${theme.shadow}, 0 0 0 1px ${theme.accent}45, inset 0 1px 0 rgba(255,255,255,0.10)`
      : "0 10px 28px rgba(0,0,0,0.42), inset 0 1px 0 rgba(255,255,255,0.04)",
  } as CSSProperties;

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={active}
      className={`fut-signal-card absolute left-1/2 top-1/2 w-[220px] transform-gpu border text-left transition-all duration-[1200ms] sm:duration-[1050ms] ${
        active ? "fut-signal-card-active" : ""
      }`}
      style={style}
    >
      <div className="fut-card-depth" aria-hidden="true" />
      <div className="fut-card-shine" aria-hidden="true" />
      <div className="fut-card-grid" aria-hidden="true" />
      <div className="relative z-10 p-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="fut-rating font-display text-[34px] font-black leading-none">
              {value}
            </p>
            <p className="mt-1 text-[9px] font-semibold uppercase tracking-[0.28em] text-slate-300/80">
              {theme.label}
            </p>
          </div>
          <div className="text-right">
            <span className={`inline-flex rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-widest ${status.cls}`}>
              {status.label}
            </span>
            <p className="mt-2 text-[10px] uppercase tracking-[0.24em] text-slate-400">
              {archetype(row)}
            </p>
          </div>
        </div>

        <div className="relative my-3 flex justify-center">
          <div className="fut-orbit" aria-hidden="true" />
          <div className="fut-asset-emblem">
            <span className="relative z-10">{row.icon}</span>
          </div>
        </div>

        <div className="text-center">
          <p className="font-display text-[18px] font-black tracking-wide text-slate-50">
            {row.symbol}
          </p>
          <p className="mt-1 text-[11px] uppercase tracking-[0.22em] text-slate-400">
            {row.name}
          </p>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2">
          <div className="fut-stat-box">
            <p className="text-[9px] uppercase tracking-widest text-slate-500">Price</p>
            <p className="font-mono text-[12px] text-slate-100">
              {fmtPx(row.price)}
            </p>
            <p className="text-[9px] text-slate-500">{row.unit}</p>
          </div>
          <div className="fut-stat-box">
            <p className="text-[9px] uppercase tracking-widest text-slate-500">Dir</p>
            <p className="font-mono text-[12px] uppercase text-slate-100">
              {directionLabel(direction)}
            </p>
            <p className="text-[9px] text-slate-500">{row.perTf.length} TF</p>
          </div>
        </div>

        <div className="mt-3 border-t border-white/10 pt-2.5">
          <span className={`flex items-center justify-center rounded border px-2 py-1.5 text-[9px] font-semibold uppercase tracking-[0.18em] ${action.cls}`}>
            {action.label}
          </span>
        </div>
      </div>
    </button>
  );
}

// ── Right detail panel ───────────────────────────────────────────────────────

function TfMatrix({ rows }: { rows: AgentBriefCandidate[] }) {
  if (!rows.length) {
    return <p className="text-[11px] italic text-slate-500">Bu sembol için TF dökümü yok.</p>;
  }
  const sorted = [...rows].sort((a, b) => tfIndex(a.timeframe) - tfIndex(b.timeframe));
  return (
    <div className="rounded-md border border-slate-700/40 bg-black/40 overflow-hidden">
      <table className="w-full text-[11px]">
        <thead className="bg-white/[0.03] text-slate-500">
          <tr>
            <th className="px-2 py-1 text-left font-medium uppercase tracking-widest">TF</th>
            <th className="px-2 py-1 text-right font-medium uppercase tracking-widest">Skor</th>
            <th className="px-2 py-1 text-right font-medium uppercase tracking-widest">Yön</th>
            <th className="px-2 py-1 text-right font-medium uppercase tracking-widest">Aksiyon</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => {
            const v = round(r.score);
            const d = (r.direction ?? "neutral") as Direction;
            return (
              <tr key={`${r.timeframe ?? "?"}-${i}`} className="border-t border-white/5">
                <td className="px-2 py-1 font-mono text-slate-300">{r.timeframe ?? "—"}</td>
                <td className={`px-2 py-1 text-right font-mono font-semibold ${scoreTone(v)}`}>{v}</td>
                <td
                  className={`px-2 py-1 text-right font-mono text-[10px] uppercase ${
                    d === "bullish" ? "text-emerald-300" : d === "bearish" ? "text-rose-300" : "text-amber-200"
                  }`}
                >
                  {d}
                </td>
                <td className="px-2 py-1 text-right text-slate-300/90">
                  {r.candidate_action ?? "WATCH"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function TechnicalsBlock({ tech }: { tech: TechnicalTf | undefined }) {
  if (!tech) {
    return (
      <p className="text-[11px] italic text-slate-500">Teknik veri yok.</p>
    );
  }
  const rows: Array<[string, string, string]> = [
    ["RSI 14", String(tech.rsi != null ? Math.round(tech.rsi) : "—"), tech.rsi != null && tech.rsi >= 60 ? "text-emerald-300" : tech.rsi != null && tech.rsi <= 40 ? "text-rose-300" : "text-slate-200"],
    ["MACD", tech.macd != null ? tech.macd.toFixed(2) : "—", "text-slate-200"],
    ["ATR", tech.atr != null ? tech.atr.toFixed(2) : "—", "text-slate-200"],
    ["EMA Dizilim", tech.ema_stack ?? "—", tech.ema_stack === "bullish" ? "text-emerald-300" : tech.ema_stack === "bearish" ? "text-rose-300" : "text-slate-300"],
    ["Skor", `${round(tech.score)}/100`, scoreTone(round(tech.score))],
  ];
  return (
    <div className="rounded-md border border-slate-700/40 bg-black/40 overflow-hidden">
      <table className="w-full text-[11px]">
        <tbody>
          {rows.map(([k, v, cls], i) => (
            <tr key={k} className={i ? "border-t border-white/5" : ""}>
              <td className="px-2 py-1 text-slate-500">{k}</td>
              <td className={`px-2 py-1 text-right font-mono ${cls}`}>{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TradePlanBlock({ ticket, symbol }: { ticket: TradeTicket | undefined; symbol: string }) {
  if (!ticket) {
    return (
      <div className="rounded-md border border-slate-700/40 bg-black/30 p-2.5">
        <p className="text-[10px] uppercase tracking-widest text-slate-500">Trade plan</p>
        <p className="mt-1 text-[11px] text-slate-500">
          {symbol} için aktif ticket yok — yeni giriş açılmıyor.
        </p>
      </div>
    );
  }
  const s = ticket.summary;
  const sideTone =
    ticket.side === "long" ? "text-emerald-300 border-emerald-500/40"
    : ticket.side === "short" ? "text-rose-300 border-rose-500/40"
    : "text-amber-300 border-amber-500/40";
  return (
    <div className="rounded-md border border-teal-300/20 bg-teal-500/[0.035] p-2.5 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest text-teal-200/85">
          Trade plan
        </span>
        <span className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wider ${sideTone}`}>
          {ticket.side} · {ticket.timeframe}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-[11px]">
        <div>
          <p className="uppercase tracking-widest text-slate-500 text-[9px]">Entry</p>
          <p className="font-mono text-slate-100">{fmtPx(s.entry_price)}</p>
        </div>
        <div>
          <p className="uppercase tracking-widest text-slate-500 text-[9px]">Stop</p>
          <p className="font-mono text-rose-300">{fmtPx(s.stop_loss)}</p>
        </div>
        <div>
          <p className="uppercase tracking-widest text-slate-500 text-[9px]">Target</p>
          <p className="font-mono text-emerald-300">{fmtPx(s.take_profit)}</p>
        </div>
      </div>
      <div className="flex items-center justify-between text-[10px] text-slate-400">
        <span>R:R 1:{(s.rr_ratio ?? 0).toFixed(2)} · {s.rr_source}</span>
        <span className="rounded bg-white/[0.05] px-1.5 py-0.5 uppercase">{ticket.status}</span>
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

export function HolographicSignalDeck({ brief }: { brief: AgentBrief }) {
  const { data: snap } = useDataSnapshot();
  const { data: decisionMatrix } = useDecisionMatrix();
  const { data: regime } = useRegimeReport();
  const { data: ticketList } = useTradeTickets();

  const rows = useMemo(
    () => pickDeckRows(brief.top_candidates ?? [], snap?.prices, decisionMatrix?.cells),
    [brief.top_candidates, decisionMatrix?.cells, snap?.prices],
  );
  const supports = useMemo(
    () => pickSupports(regime?.assets, snap?.prices),
    [regime?.assets, snap?.prices],
  );

  const [activeIndex, setActiveIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [selectedTf, setSelectedTf] = useState<Timeframe | null>(null);
  const [compactDeck, setCompactDeck] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(max-width: 768px)").matches,
  );
  const animateRef = useRef(true);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    animateRef.current = !mq.matches;
    const onMQ = () => { animateRef.current = !mq.matches; };
    mq.addEventListener?.("change", onMQ);
    return () => mq.removeEventListener?.("change", onMQ);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(max-width: 768px)");
    const sync = () => setCompactDeck(mq.matches);
    sync();
    mq.addEventListener?.("change", sync);
    return () => mq.removeEventListener?.("change", sync);
  }, []);

  // Auto-rotate
  useEffect(() => {
    if (rows.length <= 1 || paused || !animateRef.current) return;
    const t = setInterval(() => {
      setActiveIndex((i) => (i + 1) % rows.length);
    }, 7600);
    return () => clearInterval(t);
  }, [rows.length, paused]);

  // rows shrink / sembol değişimi → index ve TF reset
  useEffect(() => {
    if (activeIndex >= rows.length && rows.length > 0) setActiveIndex(0);
  }, [activeIndex, rows.length]);
  useEffect(() => {
    setSelectedTf(null);
  }, [activeIndex]);

  const activeRow = rows[activeIndex];
  const active = activeRow?.best;
  const activeSymbol = activeRow?.symbol ?? "—";
  const activeDirection = (active?.direction ?? "neutral") as Direction;
  const activeAction = active ? actionBadge(active) : { label: "—", cls: "" };

  const techForSymbol = snap?.technicals_by_tf?.[activeSymbol];
  const effectiveTf: Timeframe | null =
    selectedTf ?? (active?.timeframe as Timeframe | undefined) ?? null;
  const tech = effectiveTf ? techForSymbol?.[effectiveTf] : undefined;

  const activeTicket = useMemo(
    () => ticketList?.tickets.find((t) => t.symbol === activeSymbol && t.status === "active"),
    [ticketList?.tickets, activeSymbol],
  );

  const blocked = !brief.can_act;

  if (rows.length === 0) {
    return (
      <section
        className="quantum-panel rounded-lg border border-white/10 bg-[#090d14]/88 p-6 text-center text-xs text-slate-400"
        style={getQuantumPanelStyle("layer1_holographic_signals", "#14b8a6", "#fbbf24")}
      >
        <QuantumPanelField id="layer1_holographic_signals" density="compact" />
        <span className="relative z-10">Aktif aday sinyal yok.</span>
      </section>
    );
  }

  if (compactDeck) {
    const activeScore = round(active?.score);
    return (
      <MobileFlipCard
        title="Asset Card"
        front={
          <div className="mobile-asset-front">
            <div className="mobile-back-head">
              <div>
                <p className="mobile-kicker">ASSET CARD</p>
                <strong>{activeSymbol}</strong>
              </div>
              <span className={blocked ? "text-amber-300" : "text-emerald-300"}>
                {blocked ? "BLOCKED" : "GATE CLEAR"}
              </span>
            </div>

            <div className="mobile-asset-hero">
              <div>
                <span className="mobile-asset-icon">{activeRow?.icon}</span>
                <p>{activeRow?.name}</p>
              </div>
              <ScoreRing score={activeScore} size={96} active />
            </div>

            <div className="mobile-metric-grid">
              <div>
                <span>Fiyat</span>
                <strong>{fmtPx(activeRow?.price)} {activeRow?.unit}</strong>
              </div>
              <div>
                <span>Durum</span>
                <strong>{activeAction.label}</strong>
              </div>
              <div>
                <span>Yön</span>
                <strong>{activeDirection}</strong>
              </div>
              <div>
                <span>TF</span>
                <strong>{active?.timeframe ?? "--"}</strong>
              </div>
            </div>

            <p className="mobile-summary-line">{brief.recommended_stance}</p>
            <p className="mobile-flip-hint">Detay için dokun</p>
          </div>
        }
        back={
          <div className="mobile-flip-card__scroll mobile-asset-back">
            <div className="mobile-back-head">
              <div>
                <p className="mobile-kicker">Sinyal detayı</p>
                <strong>{activeRow?.icon} {activeSymbol}</strong>
              </div>
              <span>{activeScore}</span>
            </div>

            <TfMatrix rows={activeRow?.perTf ?? []} />

            <div className="mobile-tf-buttons" data-no-flip>
              {TF_ORDER.filter((tf) => techForSymbol?.[tf]).map((tf) => (
                <button
                  key={tf}
                  type="button"
                  onClick={() => setSelectedTf(tf)}
                  className={effectiveTf === tf ? "is-active" : ""}
                >
                  {tf}
                </button>
              ))}
            </div>
            <TechnicalsBlock tech={tech} />
            <TradePlanBlock ticket={activeTicket} symbol={activeSymbol} />

            <div className="mobile-metric-grid">
              <div>
                <span>DQS</span>
                <strong>{Math.round(brief.dqs?.score ?? 0)}</strong>
              </div>
              <div>
                <span>Mode</span>
                <strong>{brief.data_mode}</strong>
              </div>
            </div>

            {supports.length > 0 ? (
              <div className="mobile-support-list">
                <p className="mobile-kicker">Piyasa göstergeleri</p>
                {supports.slice(0, 5).map((support) => (
                  <div key={support.symbol}>
                    <span>{support.symbol}</span>
                    <strong>{fmtPx(support.price)} {support.unit}</strong>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        }
      />
    );
  }

  return (
    <section
      id="layer1_holographic_signals"
      data-panel="layer1_holographic_signals"
      className="quantum-panel quantum-holo-deck relative flex h-full min-h-0 flex-col overflow-hidden rounded-lg border border-white/10 bg-[#090d14]/92 shadow-[0_18px_56px_rgba(0,0,0,0.30)] lg:min-h-[700px]"
      style={getQuantumPanelStyle("layer1_holographic_signals", "#14b8a6", "#fbbf24")}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <style>{`
        @keyframes hsd-scan { 0%{transform:translateY(-20%);opacity:0} 12%{opacity:.7} 88%{opacity:.7} 100%{transform:translateY(120%);opacity:0} }
        @keyframes hsd-grid-pulse { 0%,100%{opacity:.18} 50%{opacity:.32} }
        @keyframes hsd-orb { 0%,100%{transform:translate(-50%,0) scale(1);opacity:.85} 50%{transform:translate(-50%,-4px) scale(1.05);opacity:1} }
        @keyframes hsd-ring-1 { 0%{transform:translate(-50%,-50%) scale(.85);opacity:.6} 100%{transform:translate(-50%,-50%) scale(1.4);opacity:0} }
        @keyframes hsd-ring-2 { 0%{transform:translate(-50%,-50%) scale(.85);opacity:.4} 100%{transform:translate(-50%,-50%) scale(1.6);opacity:0} }
        @keyframes hsd-ticker { from{transform:translateX(0)} to{transform:translateX(-50%)} }
        @keyframes hsd-corner-glow { 0%,100%{opacity:.6} 50%{opacity:1} }
      `}</style>
      <QuantumPanelField id="layer1_holographic_signals" density="deck" />

      {/* Header */}
      <div className="relative flex flex-wrap items-center justify-between gap-3 border-b border-white/10 bg-black/25 px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <span className="w-1 h-3.5 rounded-full bg-teal-300/70" aria-hidden="true" />
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-200/90">
              Asset Card
            </p>
            <p className="text-[10px] text-slate-500 mt-0.5">
              {rows.length} ana asset · {supports.length} destek göstergesi · PAPER_SAFE
            </p>
          </div>
        </div>
        <span className={`rounded border px-2 py-1 text-[10px] uppercase tracking-widest ${
          blocked
            ? "border-amber-400/40 bg-amber-400/10 text-amber-200"
            : "border-emerald-400/40 bg-emerald-400/10 text-emerald-200"
        }`}>
          {blocked ? "RISK GATED" : "GATE CLEAR"}
        </span>
      </div>

      {/* Body grid */}
      <div className="grid min-h-0 flex-1 gap-0 lg:grid-cols-[minmax(0,1fr)_360px]">
        {/* Left — 3D deck */}
        <div
          className="relative min-h-[360px] overflow-hidden border-r border-white/10 sm:min-h-[420px] lg:min-h-0"
          style={{
            background:
              "radial-gradient(circle at 50% 72%, rgba(20,184,166,0.13), transparent 34%), radial-gradient(circle at 52% 6%, rgba(251,191,36,0.07), transparent 28%), linear-gradient(180deg, rgba(12,17,27,0.92), rgba(5,8,14,0.98))",
          }}
        >
          {/* Holographic grid background */}
          <div
            aria-hidden="true"
            className="absolute inset-0 pointer-events-none"
            style={{
              backgroundImage:
                "linear-gradient(rgba(148,163,184,0.055) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.055) 1px, transparent 1px)",
              backgroundSize: "44px 44px",
              maskImage: "radial-gradient(ellipse at 50% 55%, black 25%, transparent 78%)",
              WebkitMaskImage: "radial-gradient(ellipse at 50% 55%, black 25%, transparent 78%)",
              animation: "hsd-grid-pulse 6s ease-in-out infinite",
            }}
          />
          {/* Dot grid overlay */}
          <div
            aria-hidden="true"
            className="absolute inset-0 pointer-events-none opacity-30"
            style={{
              backgroundImage: "radial-gradient(circle, rgba(148,163,184,0.22) 1px, transparent 1px)",
              backgroundSize: "26px 26px",
              maskImage: "radial-gradient(ellipse at 50% 60%, black 25%, transparent 75%)",
              WebkitMaskImage: "radial-gradient(ellipse at 50% 60%, black 25%, transparent 75%)",
            }}
          />
          {/* Scan line */}
          <div
            aria-hidden="true"
            className="absolute inset-x-0 h-[2px] pointer-events-none"
            style={{
              background:
                "linear-gradient(90deg, transparent, rgba(45,212,191,0.26), rgba(251,191,36,0.18), transparent)",
              boxShadow: "0 0 14px rgba(45,212,191,0.18)",
              animation: "hsd-scan 7s linear infinite",
            }}
          />
          {/* Corner brackets */}
          {(["tl", "tr", "bl", "br"] as const).map((corner) => {
            const pos: CSSProperties = {
              top: corner.startsWith("t") ? 10 : "auto",
              bottom: corner.startsWith("b") ? 10 : "auto",
              left: corner.endsWith("l") ? 10 : "auto",
              right: corner.endsWith("r") ? 10 : "auto",
            };
            return (
              <div
                key={corner}
                aria-hidden="true"
                className="absolute h-5 w-5 border-teal-300/35"
                style={{
                  ...pos,
                  borderTopWidth: corner.startsWith("t") ? 1.5 : 0,
                  borderBottomWidth: corner.startsWith("b") ? 1.5 : 0,
                  borderLeftWidth: corner.endsWith("l") ? 1.5 : 0,
                  borderRightWidth: corner.endsWith("r") ? 1.5 : 0,
                  animation: "hsd-corner-glow 3.4s ease-in-out infinite",
                }}
              />
            );
          })}

          {/* 3D deck stage */}
          <div
            className="relative mx-auto mt-4 h-[280px] sm:h-[330px] lg:h-[360px]"
            style={{ perspective: "2100px", perspectiveOrigin: "50% 40%" }}
          >
            {rows.map((r, i) => {
              const n = rows.length;
              let offset = i - activeIndex;
              if (offset > n / 2) offset -= n;
              if (offset < -n / 2) offset += n;
              return (
                <DeckCard
                  key={r.symbol}
                  row={r}
                  active={i === activeIndex}
                  offset={offset}
                  compact={compactDeck}
                  onSelect={() => setActiveIndex(i)}
                />
              );
            })}
          </div>

          {/* Pagination dots */}
          <div className="relative z-10 -mt-1 flex justify-center gap-1.5">
            {rows.map((r, i) => (
              <button
                key={r.symbol}
                type="button"
                onClick={() => setActiveIndex(i)}
                aria-label={r.symbol}
                className={`h-1 rounded-full transition-all duration-500 ${
                  i === activeIndex ? "w-8 bg-teal-300" : "w-2 bg-slate-600/60 hover:bg-slate-500"
                }`}
              />
            ))}
          </div>

          {/* AI Trading Operations podium */}
          <div className="relative z-10 mx-auto mb-4 mt-1 h-[88px] w-[min(540px,84%)]">
            {/* expanding rings */}
            <div
              aria-hidden="true"
              className="absolute left-1/2 top-1/2 h-16 w-36 rounded-[50%] border border-teal-300/20"
              style={{ animation: "hsd-ring-1 2.6s ease-out infinite" }}
            />
            <div
              aria-hidden="true"
              className="absolute left-1/2 top-1/2 h-16 w-36 rounded-[50%] border border-amber-300/14"
              style={{ animation: "hsd-ring-2 2.6s ease-out infinite 0.6s" }}
            />
            {/* base disc */}
            <div className="absolute inset-x-0 bottom-0 mx-auto h-14 rounded-[50%] border border-teal-300/24 bg-teal-300/[0.035] shadow-[0_0_34px_rgba(20,184,166,0.12)]" />
            <div className="absolute inset-x-[16%] bottom-3 h-8 rounded-[50%] border border-slate-400/18" />
            <div className="absolute inset-x-[30%] bottom-6 h-4 rounded-[50%] border border-amber-300/14" />
            {/* orb */}
            <div
              aria-hidden="true"
              className="absolute bottom-7 left-1/2 h-3 w-3 -translate-x-1/2 rounded-full bg-amber-200"
              style={{
                boxShadow: "0 0 12px rgba(251,191,36,0.68), 0 0 24px rgba(20,184,166,0.22)",
                animation: "hsd-orb 2.4s ease-in-out infinite",
              }}
            />
            {/* label */}
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 rounded border border-white/15 bg-slate-950/72 px-4 py-1 text-[10px] uppercase tracking-[0.32em] text-slate-200">
              ◆ AI Trading Operations ◆
            </div>
          </div>
        </div>

        {/* Right — Sinyal Detayı */}
        <aside className="relative min-h-0 overflow-hidden bg-black/20 p-3">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-teal-300 shadow-[0_0_8px_rgba(45,212,191,0.45)]" />
              <p className="text-[10px] uppercase tracking-[0.22em] text-slate-300/90">
                Sinyal detayı
              </p>
            </div>

            {/* Symbol header */}
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-display text-base font-semibold text-slate-100">
                  {activeRow?.icon} {activeSymbol}
                </p>
                <span className={`mt-1 inline-block rounded border px-2 py-0.5 text-[10px] uppercase tracking-wider ${activeAction.cls}`}>
                  {activeAction.label}
                </span>
              </div>
              <ScoreRing score={round(active?.score)} size={58} active />
            </div>

            {/* Price */}
            <div className="rounded-md border border-slate-700/40 bg-black/30 p-2.5">
              <p className="text-[10px] uppercase tracking-widest text-slate-500">Fiyat</p>
              <p className="mt-0.5 font-display text-xl font-semibold text-slate-100">
                {fmtPx(activeRow?.price)} <span className="text-[10px] text-slate-400">{activeRow?.unit}</span>
              </p>
            </div>

            {/* All TFs */}
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <p className="text-[10px] uppercase tracking-widest text-slate-500">
                  Tüm timeframeler
                </p>
                <p className="text-[9px] text-slate-600">
                  {activeRow?.perTf.length ?? 0} TF
                </p>
              </div>
              <TfMatrix rows={activeRow?.perTf ?? []} />
            </div>

            {/* TF chips + teknik */}
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <p className="text-[10px] uppercase tracking-widest text-slate-500">
                  Teknik {effectiveTf ? `· ${effectiveTf}` : ""}
                </p>
                <div className="flex gap-1">
                  {TF_ORDER.filter((tf) => techForSymbol?.[tf]).map((tf) => (
                    <button
                      key={tf}
                      type="button"
                      onClick={() => setSelectedTf(tf)}
                      className={`rounded px-1.5 py-0.5 text-[9px] font-mono uppercase border transition-colors ${
                        effectiveTf === tf
                          ? "border-teal-300/45 bg-teal-400/10 text-teal-100"
                          : "border-slate-600/40 bg-slate-800/40 text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      {tf}
                    </button>
                  ))}
                </div>
              </div>
              <TechnicalsBlock tech={tech} />
            </div>

            {/* Trade plan */}
            <TradePlanBlock ticket={activeTicket} symbol={activeSymbol} />

            {/* Footer mini stats */}
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div className="rounded border border-slate-700/40 bg-black/30 p-2">
                <p className="uppercase tracking-widest text-slate-500 text-[9px]">DQS</p>
                <p className="font-mono text-teal-300">{Math.round(brief.dqs?.score ?? 0)}</p>
              </div>
              <div className="rounded border border-slate-700/40 bg-black/30 p-2">
                <p className="uppercase tracking-widest text-slate-500 text-[9px]">Mode</p>
                <p className="font-mono text-amber-200">{brief.data_mode}</p>
              </div>
            </div>

            <div className="rounded border border-slate-700/40 bg-white/[0.02] p-2.5">
              <div className="flex items-center gap-2">
                <span className={`h-1.5 w-1.5 rounded-full ${
                  activeDirection === "bullish" ? "bg-emerald-300" :
                  activeDirection === "bearish" ? "bg-rose-300" : "bg-amber-300"
                }`} />
                <span className="text-[10px] uppercase tracking-widest text-slate-500">
                  Agent interpretation
                </span>
              </div>
              <p className="mt-1.5 text-[11px] leading-relaxed text-slate-300/90">
                {brief.recommended_stance}
              </p>
            </div>
          </div>
        </aside>
      </div>

      {/* Bottom — Piyasa göstergeleri ticker */}
      {supports.length > 0 && (
        <div className="border-t border-white/10 bg-black/25 px-4 py-2.5">
          <p className="text-[9px] font-medium uppercase tracking-[0.22em] text-slate-500 mb-1.5">
            Piyasa Göstergeleri
          </p>
          <div
            className="relative overflow-hidden"
            style={{
              maskImage: "linear-gradient(90deg, transparent, black 6%, black 94%, transparent)",
              WebkitMaskImage: "linear-gradient(90deg, transparent, black 6%, black 94%, transparent)",
            }}
          >
            <div
              className="flex gap-2 w-max"
              style={{
                animation: `hsd-ticker ${Math.max(24, supports.length * 6)}s linear infinite`,
                animationPlayState: paused ? "paused" : "running",
              }}
            >
              {[...supports, ...supports].map((s, i) => {
                const tone =
                  s.direction === "bullish" ? "border-emerald-500/35 text-emerald-200"
                  : s.direction === "bearish" ? "border-rose-500/35 text-rose-200"
                  : "border-slate-600/40 text-slate-300";
                return (
                  <div
                    key={`${s.symbol}-${i}`}
                    className={`shrink-0 flex items-center gap-2 rounded border bg-slate-900/40 px-2 py-1 ${tone}`}
                  >
                    <span aria-hidden="true" className="h-1 w-1 rounded-full bg-current" />
                    <span className="text-[10px] font-medium">{s.symbol}</span>
                    <span className="text-[10px] font-mono text-slate-100">
                      {fmtPx(s.price)} {s.unit}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="border-t border-white/10 bg-black/25 px-4 py-1.5 text-center">
        <p className="text-[9px] text-slate-500">
          Yalnız görselleştirme · karar üretmez · final karar deterministik engine + RiskGate
        </p>
      </div>
    </section>
  );
}
