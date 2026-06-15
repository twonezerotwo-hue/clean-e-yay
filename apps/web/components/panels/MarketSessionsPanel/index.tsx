"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useMarketSessions } from "@/lib/queries/hooks";
import type { MarketSessionStatusView, SessionPhase } from "@/types/generated/api";

// Read-only observability panel. The BACKEND (packages/market_sessions) owns all
// session meaning — timezone / DST / holidays / phase are computed server-side.
// This panel only renders the provided ViewModel fields: no manual fetch (typed
// hook), no session/time/open-close computation, no trading controls. Phase →
// label/colour maps below are presentation only (choosing a colour band for a
// backend-provided enum), not session logic.

const PHASE_LABEL: Record<SessionPhase, string> = {
  mid_session: "OPEN",
  opening_window: "OPENING",
  closing_window: "CLOSING",
  pre_open: "PRE-OPEN",
  after_close: "CLOSED",
  closed: "CLOSED",
  unknown: "—",
};

const PHASE_TONE: Record<SessionPhase, string> = {
  mid_session: "text-signal-up border-signal-up/40 bg-signal-up/10",
  opening_window: "text-amber-400 border-amber-400/40 bg-amber-400/10",
  closing_window: "text-amber-400 border-amber-400/40 bg-amber-400/10",
  pre_open: "text-accent-cyan border-accent-cyan/40 bg-accent-cyan/10",
  after_close: "text-white/45 border-white/10 bg-white/5",
  closed: "text-white/45 border-white/10 bg-white/5",
  unknown: "text-white/30 border-white/10 bg-white/5",
};

// Sort: volatility boundaries first, then open, then the rest (display order).
const PHASE_ORDER: Record<SessionPhase, number> = {
  opening_window: 0,
  closing_window: 1,
  mid_session: 2,
  pre_open: 3,
  after_close: 4,
  closed: 5,
  unknown: 6,
};

function MarketRow({ m }: { m: MarketSessionStatusView }) {
  // Pure passthrough of backend minute fields — no time/open-close math here.
  let detail = "—";
  if (m.is_open && m.minutes_to_close != null) detail = `closes in ${m.minutes_to_close}m`;
  else if (!m.is_open && m.minutes_to_open != null) detail = `opens in ${m.minutes_to_open}m`;
  else if (m.session_phase === "unknown") detail = "calendar unavailable";
  return (
    <li className="flex items-center justify-between border-b border-white/5 py-1 text-[11px]">
      <span className="flex min-w-0 items-center gap-2">
        <span
          className={`rounded border px-1.5 py-px text-[9px] font-mono uppercase tracking-wide ${PHASE_TONE[m.session_phase]}`}
        >
          {PHASE_LABEL[m.session_phase]}
        </span>
        <span className="truncate text-white/85">{m.label}</span>
        {m.volatility_window && (
          <span className="text-[10px] text-amber-400" title="high-volatility session boundary">
            ⚡
          </span>
        )}
        {!m.holiday_verified && (
          <span
            className="text-[9px] text-white/30"
            title="holidays / early-closes unverified (calendar fallback)"
          >
            ~hol
          </span>
        )}
      </span>
      <span className="shrink-0 tabular-nums text-white/45">{detail}</span>
    </li>
  );
}

export function MarketSessionsPanel() {
  const { data, isLoading } = useMarketSessions();
  if (isLoading) {
    return (
      <PanelFrame id="market_sessions">
        <PanelHeader title="Market Sessions" />
        <LoadingState />
      </PanelFrame>
    );
  }
  if (!data || !data.markets.length) {
    return (
      <PanelFrame id="market_sessions">
        <PanelHeader title="Market Sessions" subtitle="PAPER_SAFE · NO_EXECUTION" />
        <EmptyState />
      </PanelFrame>
    );
  }
  const openCount = data.markets.filter((m) => m.is_open).length;
  const markets = [...data.markets].sort(
    (a, b) => PHASE_ORDER[a.session_phase] - PHASE_ORDER[b.session_phase],
  );
  const calendarFallback = data.diagnostics.some((d) =>
    d.startsWith("exchange_calendar_missing"),
  );
  return (
    <PanelFrame id="market_sessions">
      <PanelHeader
        title="Market Sessions"
        subtitle="global exchange hours · read-only"
        actions={
          <span className="rounded bg-signal-up/15 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-signal-up">
            {openCount} open
          </span>
        }
      />
      <ul>
        {markets.map((m) => (
          <MarketRow key={m.market_id} m={m} />
        ))}
      </ul>
      {calendarFallback && (
        <div className="mt-2 text-[10px] text-white/35">
          calendar fallback — weekday sessions, holidays unverified
        </div>
      )}
      <div className="mt-2 text-[9px] uppercase tracking-widest text-white/30">
        {data.paper_safe ? "PAPER_SAFE" : ""} · {data.no_execution ? "NO_EXECUTION" : ""}
      </div>
    </PanelFrame>
  );
}
