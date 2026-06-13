import type {
  AgentBrief,
  AgentStatus,
  CockpitBrief,
  DecisionTrace,
  MainBlockerCode,
  DataMode,
} from "@/types/generated/api";

// UX1 — cockpit selector'ları: backend ViewModel'inden alanları çeker; karar
// hesaplaması YOK (tonlar yalnızca görsel sunum). DASHBOARD_RULES.

export const selectAgentBrief = (b: CockpitBrief | undefined): AgentBrief | undefined =>
  b?.agent_brief;

export const selectDecisionTrace = (
  b: CockpitBrief | undefined,
): DecisionTrace | undefined => b?.decision_trace;

/** Agent durumu → renk tonu (yalnızca sunum). */
export const AGENT_STATUS_TONE: Record<AgentStatus, string> = {
  ACTIONABLE: "text-signal-up",
  NO_ACTION: "text-white/60",
  WATCHING: "text-accent-cyan",
  FROZEN: "text-amber-400",
  BLOCKED: "text-signal-down",
};

/** main_blocker kodu → ton (NONE yeşil, diğerleri uyarı/blok). */
export const BLOCKER_TONE: Record<MainBlockerCode, string> = {
  NONE: "text-signal-up",
  RISK_GATE: "text-accent-magenta",
  HALT: "text-signal-down",
  DQS_BLOCKED: "text-signal-down",
  PROVIDER_DOWN: "text-signal-down",
};

/** data_mode → ton (LIVE_VERIFIED yeşil, BLOCKED kırmızı). */
export const DATA_MODE_TONE: Record<DataMode, string> = {
  LIVE_VERIFIED: "text-signal-up",
  LIVE_DEGRADED: "text-accent-cyan",
  PARTIAL_FALLBACK: "text-amber-400",
  SIMULATION: "text-amber-400",
  BLOCKED: "text-signal-down",
};

export const AGENT_STATUS_LABEL: Record<AgentStatus, string> = {
  ACTIONABLE: "İŞLEM AÇABİLİR",
  NO_ACTION: "AKSİYON YOK",
  WATCHING: "İZLİYOR",
  FROZEN: "DONDURULDU",
  BLOCKED: "BLOKLU",
};
