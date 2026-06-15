/**
 * AgentMatrix selectors — backend ViewModel → render-ready shapes. Frontend does
 * NO technical math; the multi-TF pipeline (steps 1–6) is computed server-side and
 * this only maps fields to labels/tones for the panel.
 */
import type {
  AgentMatrix,
  AgentMatrixRow,
  TechnicalBias,
  Timeframe,
} from "@/types/generated/api";

export const AGENT_TF_ORDER: Timeframe[] = ["15m", "1h", "4h", "1d", "1w"];

// ConsensusSnapshot.per_timeframe_bias is keyed m15/h1/h4/d1/w1 (contract naming).
const TF_TO_KEY: Record<Timeframe, string> = {
  "15m": "m15",
  "1h": "h1",
  "4h": "h4",
  "1d": "d1",
  "1w": "w1",
};

export const ACTION_LABEL: Record<string, string> = {
  NO_TRADE: "NO TRADE",
  WATCH: "WATCH",
  SCOUT_ALLOWED: "SCOUT",
  CONFIRMATION_REQUIRED: "CONFIRM",
  RISK_REDUCE: "RISK ↓",
  KILL_SWITCH: "KILL",
};

export function actionTone(action?: string): string {
  switch (action) {
    case "SCOUT_ALLOWED":
      return "border-signal-up/50 text-signal-up bg-signal-up/10";
    case "CONFIRMATION_REQUIRED":
      return "border-amber-400/40 text-amber-300 bg-amber-400/10";
    case "KILL_SWITCH":
    case "RISK_REDUCE":
      return "border-signal-down/50 text-signal-down bg-signal-down/10";
    default: // NO_TRADE / WATCH
      return "border-white/10 text-white/55";
  }
}

export function biasTone(bias?: TechnicalBias | string): string {
  if (bias === "BULLISH") return "border-signal-up/40 text-signal-up bg-signal-up/5";
  if (bias === "BEARISH")
    return "border-signal-down/40 text-signal-down bg-signal-down/5";
  return "border-white/10 text-white/40"; // NEUTRAL / missing
}

const BIAS_GLYPH: Record<string, string> = {
  BULLISH: "▲",
  BEARISH: "▼",
  NEUTRAL: "·",
};

export function biasFor(row: AgentMatrixRow, tf: Timeframe): TechnicalBias | undefined {
  return row.consensus.per_timeframe_bias?.[TF_TO_KEY[tf]];
}

export function biasGlyph(bias?: TechnicalBias | string): string {
  return BIAS_GLYPH[bias ?? ""] ?? "–";
}

export const ALIGNMENT_TONE: Record<string, string> = {
  ALIGNED: "text-signal-up",
  PARTIAL: "text-white/60",
  COUNTERTREND: "text-amber-300",
  CONFLICTED: "text-signal-down",
};

export function selectAgentRows(data?: AgentMatrix): AgentMatrixRow[] {
  return data?.symbols ?? [];
}

/** A restrictive global RiskGate action suspends the whole matrix (single banner). */
export function isRiskRestrictive(action?: string | null): boolean {
  return (
    action === "KILL_SWITCH" ||
    action === "RISK_REDUCE" ||
    action === "NO_POSITION_INCREASE"
  );
}

/** Short economics summary string (R:R + net edge) or the block reason. */
export function economicsSummary(row: AgentMatrixRow): string {
  const e = row.economics;
  if (!e) return "—";
  if (!e.allow) return `⛔ ${e.reason}`;
  const rr = e.rr != null ? `R:R ${e.rr.toFixed(2)}` : "R:R —";
  const edge = e.net_edge_bps != null ? `net ${Math.round(e.net_edge_bps)}bps` : "";
  return [rr, edge].filter(Boolean).join(" · ");
}
