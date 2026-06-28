"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type ChartTimeframe, type UpdateRiskPlanRequest } from "@/lib/api/client";
import { usePanelQueryPolicy } from "@/lib/panel-runtime";
import { qk } from "./keys";

export const useHealth = () => {
  const policy = usePanelQueryPolicy(30_000);
  return useQuery({ queryKey: qk.health, queryFn: api.health, ...policy });
};

export const useSystemHealth = () => {
  const policy = usePanelQueryPolicy(30_000);
  return useQuery({
    queryKey: qk.systemHealth,
    queryFn: api.systemHealth,
    staleTime: 15_000,
    ...policy,
  });
};

export const useRegimeReport = () => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.regimeReport,
    queryFn: api.regimeReport,
    staleTime: 60_000,
    ...policy,
  });
};

export const useDashboardState = () => {
  const policy = usePanelQueryPolicy(30_000);
  return useQuery({
    queryKey: qk.dashboardState,
    queryFn: api.dashboardState,
    staleTime: 30_000,
    ...policy,
  });
};

export const useAIReport = () => {
  const policy = usePanelQueryPolicy(30 * 60_000);
  return useQuery({
    queryKey: qk.aiReport,
    queryFn: api.aiReport,
    staleTime: 30 * 60_000,
    ...policy,
  });
};

export const usePaperTradingState = () => {
  const policy = usePanelQueryPolicy(15_000);
  return useQuery({
    queryKey: qk.paperTradingState,
    queryFn: api.paperTradingState,
    staleTime: 10_000,
    ...policy,
  });
};

export const useClosePaperPosition = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (positionId: string) => api.closePaperPosition(positionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.paperTradingState });
      void queryClient.invalidateQueries({ queryKey: qk.cockpitBrief });
    },
  });
};

export const useUpdatePaperPositionRiskPlan = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      positionId,
      body,
    }: {
      positionId: string;
      body: UpdateRiskPlanRequest;
    }) => api.updatePaperPositionRiskPlan(positionId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.paperTradingState });
      void queryClient.invalidateQueries({ queryKey: qk.cockpitBrief });
    },
  });
};

export const useMarketSessions = () => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.marketSessions,
    queryFn: api.marketSessions,
    staleTime: 60_000,
    ...policy,
  });
};

export const useMarketSessionsTradeUniverse = () => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.marketSessionsTradeUniverse,
    queryFn: api.marketSessionsTradeUniverse,
    staleTime: 60_000,
    ...policy,
  });
};

export const useAgentQuorumMatrix = () => {
  const policy = usePanelQueryPolicy(30_000);
  return useQuery({
    queryKey: qk.agentQuorumMatrix,
    queryFn: api.agentQuorumMatrix,
    staleTime: 20_000,
    ...policy,
  });
};

export const useMarketSessionAsset = (symbol: string) => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.marketSessionAsset(symbol),
    queryFn: () => api.marketSessionAsset(symbol),
    enabled: Boolean(symbol),
    staleTime: 60_000,
    ...policy,
  });
};

export const useAssetRegistry = () => {
  const policy = usePanelQueryPolicy(5 * 60_000);
  return useQuery({
    queryKey: qk.assetRegistry,
    queryFn: api.assetRegistry,
    staleTime: 5 * 60_000,
    ...policy,
  });
};

export const useAssetAnalysis = (symbol: string) => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.assetAnalysis(symbol),
    queryFn: () => api.assetAnalysis(symbol),
    enabled: Boolean(symbol),
    staleTime: 45_000,
    ...policy,
  });
};

export const useTechnicalInsight = (symbol: string) => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.technicalInsight(symbol),
    queryFn: () => api.technicalInsight(symbol),
    enabled: Boolean(symbol),
    staleTime: 60_000,
    ...policy,
  });
};

export const useTechnicalChart = (
  symbol: string,
  timeframe: ChartTimeframe = "1d",
  limit = 180,
) => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.technicalChart(symbol, timeframe, limit),
    queryFn: () => api.technicalChart(symbol, timeframe, limit),
    enabled: Boolean(symbol && timeframe),
    staleTime: 45_000,
    ...policy,
  });
};

export const useElliottScenario = (symbol: string, timeframe = "1d") => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.elliottScenario(symbol, timeframe),
    queryFn: () => api.elliottScenario(symbol, timeframe),
    enabled: Boolean(symbol),
    staleTime: 60_000,
    ...policy,
  });
};

export const useZoneAnalysis = (symbol: string, timeframe = "1d") => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.zoneAnalysis(symbol, timeframe),
    queryFn: () => api.zoneAnalysis(symbol, timeframe),
    enabled: Boolean(symbol),
    staleTime: 60_000,
    ...policy,
  });
};

export const useVolumeAnalysis = (symbol: string, timeframe = "1d") => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.volumeAnalysis(symbol, timeframe),
    queryFn: () => api.volumeAnalysis(symbol, timeframe),
    enabled: Boolean(symbol),
    staleTime: 60_000,
    ...policy,
  });
};

export const useVwapAnalysis = (symbol: string, timeframe = "1d") => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.vwapAnalysis(symbol, timeframe),
    queryFn: () => api.vwapAnalysis(symbol, timeframe),
    enabled: Boolean(symbol),
    staleTime: 60_000,
    ...policy,
  });
};

export const useLiquiditySweepAnalysis = (symbol: string, timeframe = "1d") => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.liquiditySweepAnalysis(symbol, timeframe),
    queryFn: () => api.liquiditySweepAnalysis(symbol, timeframe),
    enabled: Boolean(symbol),
    staleTime: 60_000,
    ...policy,
  });
};

export const useExhaustionScore = (symbol: string, timeframe = "1d") => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.exhaustionScore(symbol, timeframe),
    queryFn: () => api.exhaustionScore(symbol, timeframe),
    enabled: Boolean(symbol),
    staleTime: 60_000,
    ...policy,
  });
};

export const useLocationScore = (symbol: string, timeframe = "1d") => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.locationScore(symbol, timeframe),
    queryFn: () => api.locationScore(symbol, timeframe),
    enabled: Boolean(symbol),
    staleTime: 60_000,
    ...policy,
  });
};

export const useTriggerAnalysis = (symbol: string, timeframe = "1d") => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.triggerAnalysis(symbol, timeframe),
    queryFn: () => api.triggerAnalysis(symbol, timeframe),
    enabled: Boolean(symbol),
    staleTime: 60_000,
    ...policy,
  });
};

export const useLearningSummary = () => {
  const policy = usePanelQueryPolicy();
  return useQuery({
    queryKey: qk.learningSummary,
    queryFn: api.learningSummary,
    staleTime: 5 * 60_000,
    ...policy,
  });
};

export const useDataSnapshot = () => {
  const policy = usePanelQueryPolicy(30_000);
  return useQuery({
    queryKey: qk.dataSnapshot,
    queryFn: api.dataSnapshot,
    staleTime: 15_000,
    ...policy,
  });
};

export const useLiquidityRotation = () => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.liquidityRotation,
    queryFn: api.liquidityRotation,
    staleTime: 30_000,
    ...policy,
  });
};

export const useRebalanceProposal = () => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.rebalanceProposal,
    queryFn: api.rebalanceProposal,
    staleTime: 60_000,
    ...policy,
  });
};

export const useCalibration = () => {
  const policy = usePanelQueryPolicy(5 * 60_000);
  return useQuery({
    queryKey: qk.calibration,
    queryFn: api.calibration,
    staleTime: 60_000,
    ...policy,
  });
};

export const useTfWeights = () => {
  const policy = usePanelQueryPolicy(5 * 60_000);
  return useQuery({
    queryKey: qk.tfWeights,
    queryFn: api.tfWeights,
    staleTime: 60_000,
    ...policy,
  });
};

export const useTfTargets = () => {
  const policy = usePanelQueryPolicy(5 * 60_000);
  return useQuery({
    queryKey: qk.tfTargets,
    queryFn: api.tfTargets,
    staleTime: 60_000,
    ...policy,
  });
};

export const useMissedOpportunities = () => {
  const policy = usePanelQueryPolicy(5 * 60_000);
  return useQuery({
    queryKey: qk.missedOpportunities,
    queryFn: api.missedOpportunities,
    staleTime: 60_000,
    ...policy,
  });
};

export const useMistakes = () => {
  const policy = usePanelQueryPolicy(2 * 60_000);
  return useQuery({
    queryKey: qk.mistakes,
    queryFn: api.mistakes,
    staleTime: 60_000,
    ...policy,
  });
};

export const useRiskCorrelation = () => {
  const policy = usePanelQueryPolicy(2 * 60_000);
  return useQuery({
    queryKey: qk.riskCorrelation,
    queryFn: api.riskCorrelation,
    staleTime: 60_000,
    ...policy,
  });
};

export const useDecisionMatrix = () => {
  const policy = usePanelQueryPolicy(30_000);
  return useQuery({
    queryKey: qk.decisionMatrix,
    queryFn: api.decisionMatrix,
    staleTime: 15_000,
    ...policy,
  });
};

export const useAgentMatrix = () => {
  const policy = usePanelQueryPolicy(30_000);
  return useQuery({
    queryKey: qk.agentMatrix,
    queryFn: api.agentMatrix,
    staleTime: 15_000,
    ...policy,
  });
};

export const useShadowComparison = () => {
  const policy = usePanelQueryPolicy(30_000);
  return useQuery({
    queryKey: qk.shadowComparison,
    queryFn: api.shadowComparison,
    staleTime: 15_000,
    ...policy,
  });
};

export const useConflictGateStatus = () => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.conflictGateStatus,
    queryFn: api.conflictGateStatus,
    staleTime: 30_000,
    ...policy,
  });
};

export const useConflictGateValidation = () => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.conflictGateValidation,
    queryFn: api.conflictGateValidation,
    staleTime: 30_000,
    ...policy,
  });
};

export const useCockpitBrief = () => {
  const policy = usePanelQueryPolicy(30_000);
  return useQuery({
    queryKey: qk.cockpitBrief,
    queryFn: api.cockpitBrief,
    staleTime: 15_000,
    ...policy,
  });
};

export const useRiskHalts = () => {
  const policy = usePanelQueryPolicy(30_000);
  return useQuery({
    queryKey: qk.riskHalts,
    queryFn: api.riskHalts,
    staleTime: 15_000,
    ...policy,
  });
};

export const useReplayStatus = () => {
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.replayStatus,
    queryFn: api.replayStatus,
    staleTime: 60_000,
    ...policy,
  });
};

export const useReplayBacktest = () => {
  const policy = usePanelQueryPolicy();
  return useQuery({
    queryKey: qk.replayBacktest,
    queryFn: api.replayBacktest,
    enabled: false,
    retry: false,
    staleTime: 5 * 60_000,
    ...policy,
  });
};

export const useReplaySnapshot = (snapshotId?: string | null) => {
  const id = snapshotId ?? "";
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.replaySnapshot(id),
    queryFn: () => api.replaySnapshot(id),
    enabled: Boolean(id),
    staleTime: 60_000,
    ...policy,
  });
};

export const useReplayDecisionTrace = (snapshotId?: string | null) => {
  const id = snapshotId ?? "";
  const policy = usePanelQueryPolicy(60_000);
  return useQuery({
    queryKey: qk.replayDecisionTrace(id),
    queryFn: () => api.replayDecisionTrace(id),
    enabled: Boolean(id),
    staleTime: 60_000,
    ...policy,
  });
};

export const useChat = () =>
  useMutation({ mutationFn: (message: string) => api.chat(message) });

export const useTradeTickets = () => {
  const policy = usePanelQueryPolicy(15_000);
  return useQuery({
    queryKey: qk.tradeTickets,
    queryFn: api.tradeTickets,
    staleTime: 10_000,
    ...policy,
  });
};

export const useNotifications = () => {
  const policy = usePanelQueryPolicy(10_000);
  return useQuery({
    queryKey: qk.notifications,
    queryFn: () => api.notifications(false),
    staleTime: 5_000,
    ...policy,
  });
};

/** Owner bekleyen (limit/stop) emirleri. */
export const usePendingOrders = () =>
  useQuery({
    queryKey: qk.pendingOrders,
    queryFn: api.pendingOrders,
    staleTime: 5_000,
    refetchInterval: 8_000,
  });

/** Owner emir aç (market/limit/stop/stop_limit). */
export const usePlaceOrder = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.placeOrder,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.pendingOrders });
      void queryClient.invalidateQueries({ queryKey: qk.paperTradingState });
    },
  });
};

/** Bekleyen emir iptal. */
export const useCancelOrder = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (orderId: string) => api.cancelOrder(orderId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.pendingOrders });
    },
  });
};

export const useAckNotification = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.ackNotification(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.notifications });
    },
  });
};

export const useAckAllNotifications = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.ackAllNotifications,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.notifications });
    },
  });
};

export const useAgentBriefing = () => {
  const policy = usePanelQueryPolicy(15_000);
  return useQuery({
    queryKey: qk.agentBriefing,
    queryFn: api.agentBriefing,
    staleTime: 5_000,
    ...policy,
  });
};

export const useHaltReset = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.riskHaltsReset,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.riskHalts });
      void queryClient.invalidateQueries({ queryKey: qk.dashboardState });
    },
  });
};
