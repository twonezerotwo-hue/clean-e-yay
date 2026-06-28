"use client";

import { isValidElement, type ReactNode } from "react";

import { LazyPanelMount } from "./LazyPanelMount";

/**
 * Pano grid'i. Tailwind CSS columns + responsive breakpoints. Her panel
 * span'ine göre yerleşir (1 / 2 / 3 / full).
 */
const SPAN: Record<string, string> = {
  "1": "lg:col-span-1",
  "2": "lg:col-span-2",
  "3": "lg:col-span-3",
  full: "lg:col-span-3",
};

const PANEL_ID_BY_COMPONENT: Record<string, string> = {
  AgentBriefPanel: "agent_brief",
  AgentMatrixPanel: "agent_matrix",
  AgentNarratorPanel: "agent_narrator",
  AgentVotesPanel: "agent_votes",
  AIReportPanel: "ai_report",
  CalibrationPanel: "calibration",
  CapitalRotationPanel: "capital_rotation",
  CatalystImpactPanel: "catalyst_impact",
  ChatPanel: "chat",
  CommandSignalsPanel: "command_signals",
  CorrelationPanel: "correlation",
  CryptoDerivativesPanel: "crypto_derivatives",
  DataQualityPanel: "data_quality",
  DecisionPanel: "decision",
  DecisionTracePanel: "decision_trace",
  DrawdownGuardPanel: "drawdown_guard",
  EventCalendarPanel: "event_calendar",
  ExecutionReadinessPanel: "execution_readiness",
  LearningPanel: "learning",
  MarketDataPanel: "market_data",
  MarketSessionsPanel: "market_sessions",
  MistakeMemoryPanel: "mistake_memory",
  NewsPanel: "news",
  OptionsVolPanel: "options_vol",
  PanelAuditPanel: "panel_audit",
  PaperActionPanel: "paper_action",
  PositionChecksPanel: "position_checks",
  ProviderStatusPanel: "provider_status",
  ReplayStatusPanel: "replay_status",
  RiskDurumuPanel: "risk_durumu",
  ScenarioPanel: "scenario",
  ShadowPanel: "shadow",
  SnapshotPanel: "snapshot",
  SystemHealthBar: "system_health",
  TfWeightsPanel: "tf_weights",
  TfTargetsPanel: "tf_targets",
  MissedOpportunitiesPanel: "missed_opportunities",
  TimeframeMatrixPanel: "timeframe_matrix",
  TradeTicketPanel: "trade_ticket",
  TradingPanel: "trading",
  VolatilityPanel: "volatility",
  WatchConditionsPanel: "watch_conditions",
  WeightHistoryPanel: "weight_history",
  WeightProposalPanel: "weight_proposal",
};

function inferPanelId(children: ReactNode) {
  if (!isValidElement(children)) return undefined;
  const type = children.type as { displayName?: string; name?: string } | string;
  if (typeof type === "string") return undefined;
  const name = type.displayName ?? type.name;
  return name ? PANEL_ID_BY_COMPONENT[name] : undefined;
}

export function DashboardGrid({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 auto-rows-min">
      {children}
    </div>
  );
}

export function GridCell({
  span = "1",
  children,
  lazy = true,
  minHeight,
}: {
  span?: "1" | "2" | "3" | "full";
  children: ReactNode;
  lazy?: boolean;
  minHeight?: number;
}) {
  const content = lazy ? (
    <LazyPanelMount anchorId={inferPanelId(children)} minHeight={minHeight}>
      {children}
    </LazyPanelMount>
  ) : (
    children
  );

  return <div className={SPAN[span]}>{content}</div>;
}
