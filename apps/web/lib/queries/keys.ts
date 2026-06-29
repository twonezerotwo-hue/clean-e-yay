export const qk = {
  health: ["health"] as const,
  systemHealth: ["system", "health"] as const,
  regimeReport: ["regime-report"] as const,
  dashboardState: ["dashboard-state"] as const,
  aiReport: ["ai-report"] as const,
  paperTradingState: ["paper-trading", "state"] as const,
  marketSessions: ["market-sessions", "current"] as const,
  marketSessionAsset: (symbol: string) =>
    ["market-sessions", "asset", symbol] as const,
  marketSessionsTradeUniverse: ["market-sessions", "trade-universe"] as const,
  agentQuorumMatrix: ["dashboard", "agent-quorum-matrix"] as const,
  assetRegistry: ["assets", "registry"] as const,
  assetAnalysis: (symbol: string) => ["analysis", "asset", symbol] as const,
  technicalInsight: (symbol: string) =>
    ["technical", "insight", symbol] as const,
  technicalChart: (symbol: string, timeframe: string, limit: number) =>
    ["technical", "chart", symbol, timeframe, limit] as const,
  elliottScenario: (symbol: string, timeframe: string) =>
    ["technical", "elliott", symbol, timeframe] as const,
  zoneAnalysis: (symbol: string, timeframe: string) =>
    ["technical", "zones", symbol, timeframe] as const,
  volumeAnalysis: (symbol: string, timeframe: string) =>
    ["technical", "volume", symbol, timeframe] as const,
  vwapAnalysis: (symbol: string, timeframe: string) =>
    ["technical", "vwap", symbol, timeframe] as const,
  liquiditySweepAnalysis: (symbol: string, timeframe: string) =>
    ["technical", "liquidity-sweep", symbol, timeframe] as const,
  exhaustionScore: (symbol: string, timeframe: string) =>
    ["technical", "exhaustion", symbol, timeframe] as const,
  locationScore: (symbol: string, timeframe: string) =>
    ["technical", "location-score", symbol, timeframe] as const,
  triggerAnalysis: (symbol: string, timeframe: string) =>
    ["technical", "trigger", symbol, timeframe] as const,
  learningSummary: ["learning", "summary"] as const,
  dataSnapshot: ["data", "snapshot"] as const,
  rebalanceProposal: ["learning", "rebalance"] as const,
  calibration: ["learning", "calibration"] as const,
  tfWeights: ["learning", "tf-weights"] as const,
  tfTargets: ["learning", "tf-targets"] as const,
  missedOpportunities: ["learning", "missed-opportunities"] as const,
  bookAudit: ["learning", "book-audit"] as const,
  calibrationJumps: ["learning", "calibration-jumps"] as const,
  historicalEdge: (fingerprint: string) =>
    ["learning", "historical-edge", fingerprint] as const,
  agentModeConfig: ["agent-mode", "config"] as const,
  governorReport: ["governor", "report"] as const,
  governorProposals: ["governor", "proposals"] as const,
  governorTasks: ["governor", "tasks"] as const,
  mistakes: ["learning", "mistakes"] as const,
  riskCorrelation: ["risk", "correlation"] as const,
  riskHalts: ["risk", "halts"] as const,
  decisionMatrix: ["decision", "matrix"] as const,
  agentMatrix: ["technical", "agent-matrix"] as const,
  shadowComparison: ["decision", "shadow"] as const,
  conflictGateStatus: ["learning", "conflict-gate-status"] as const,
  conflictGateValidation: ["learning", "conflict-gate-validation"] as const,
  cockpitBrief: ["cockpit", "brief"] as const,
  replayStatus: ["replay", "status"] as const,
  replayBacktest: ["replay", "backtest"] as const,
  replaySnapshot: (snapshotId: string) => ["replay", "snapshot", snapshotId] as const,
  replayDecisionTrace: (snapshotId: string) =>
    ["replay", "decision-trace", snapshotId] as const,
  tradeTickets: ["paper-trading", "tickets"] as const,
  notifications: ["notifications"] as const,
  agentBriefing: ["agent", "briefing"] as const,
  liquidityRotation: ["liquidity", "rotation"] as const,
  pendingOrders: ["paper-trading", "orders"] as const,
};
