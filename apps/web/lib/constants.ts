export const TRADED_SYMBOLS = ["BTCUSD", "ETHUSD", "XAUUSD", "XAGUSD"] as const;

export const REGIME_COLOR: Record<string, string> = {
  OFFENSIVE: "text-accent-lime",
  NEUTRAL: "text-accent-cyan",
  DEFENSIVE: "text-accent-magenta",
  CRISIS: "text-signal-down",
};

export const DIRECTION_COLOR: Record<string, string> = {
  bullish: "text-signal-up",
  bearish: "text-signal-down",
  neutral: "text-signal-flat",
};

export const RISK_ACTION_COLOR: Record<string, string> = {
  HOLD: "text-signal-flat",
  WATCH: "text-accent-cyan",
  HEDGE_INCREASE: "text-accent-magenta",
  NO_POSITION_INCREASE: "text-accent-magenta",
  RISK_REDUCE: "text-amber-400",
  KILL_SWITCH: "text-signal-down",
};
