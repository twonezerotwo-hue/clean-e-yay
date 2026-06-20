"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { qk } from "./keys";

export const useHealth = () =>
  useQuery({ queryKey: qk.health, queryFn: api.health, refetchInterval: 30_000 });

/** O1 — 7/24 worker reliability özeti (worker/provider/dqs/snapshot/halt). */
export const useSystemHealth = () =>
  useQuery({
    queryKey: qk.systemHealth,
    queryFn: api.systemHealth,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

export const useRegimeReport = () =>
  useQuery({
    queryKey: qk.regimeReport,
    queryFn: api.regimeReport,
    staleTime: 60_000,
    refetchInterval: 60_000,
  });

export const useDashboardState = () =>
  useQuery({
    queryKey: qk.dashboardState,
    queryFn: api.dashboardState,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

export const useAIReport = () =>
  useQuery({
    queryKey: qk.aiReport,
    queryFn: api.aiReport,
    staleTime: 30 * 60_000,
    refetchInterval: 30 * 60_000,
  });

export const usePaperTradingState = () =>
  useQuery({
    queryKey: qk.paperTradingState,
    queryFn: api.paperTradingState,
    staleTime: 10_000,
    refetchInterval: 15_000,
  });

/** Global market-session statuses (backend-derived; FE renders only). */
export const useMarketSessions = () =>
  useQuery({
    queryKey: qk.marketSessions,
    queryFn: api.marketSessions,
    staleTime: 60_000,
    refetchInterval: 60_000,
  });

export const useLearningSummary = () =>
  useQuery({
    queryKey: qk.learningSummary,
    queryFn: api.learningSummary,
    staleTime: 5 * 60_000,
  });

export const useDataSnapshot = () =>
  useQuery({
    queryKey: qk.dataSnapshot,
    queryFn: api.dataSnapshot,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

export const useRebalanceProposal = () =>
  useQuery({
    queryKey: qk.rebalanceProposal,
    queryFn: api.rebalanceProposal,
    staleTime: 60_000,
    refetchInterval: 60_000,
  });

export const useCalibration = () =>
  useQuery({
    queryKey: qk.calibration,
    queryFn: api.calibration,
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
  });

/** Step 8 — per-TF calibration + trust-gated tf_weights proposal (owner-approved). */
export const useTfWeights = () =>
  useQuery({
    queryKey: qk.tfWeights,
    queryFn: api.tfWeights,
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
  });

export const useMistakes = () =>
  useQuery({
    queryKey: qk.mistakes,
    queryFn: api.mistakes,
    staleTime: 60_000,
    refetchInterval: 2 * 60_000,
  });

export const useRiskCorrelation = () =>
  useQuery({
    queryKey: qk.riskCorrelation,
    queryFn: api.riskCorrelation,
    staleTime: 60_000,
    refetchInterval: 2 * 60_000,
  });

/** T2 — (symbol × timeframe) karar matrisi. */
export const useDecisionMatrix = () =>
  useQuery({
    queryKey: qk.decisionMatrix,
    queryFn: api.decisionMatrix,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

/** T2 step 7 — multi-TF agent pipeline matrisi (consensus → karar → ekonomi). */
export const useAgentMatrix = () =>
  useQuery({
    queryKey: qk.agentMatrix,
    queryFn: api.agentMatrix,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

/** Step 9 — controlled activation: canlı vs shadow karşılaştırması (observe-only). */
export const useShadowComparison = () =>
  useQuery({
    queryKey: qk.shadowComparison,
    queryFn: api.shadowComparison,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

/** UX1 — Agent Operating Cockpit özeti (AgentBrief + DecisionTrace). */
export const useCockpitBrief = () =>
  useQuery({
    queryKey: qk.cockpitBrief,
    queryFn: api.cockpitBrief,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

export const useRiskHalts = () =>
  useQuery({
    queryKey: qk.riskHalts,
    queryFn: api.riskHalts,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

/** OPS — replay altyapı durumu (rezerve, aktif değil; sahte replay yok). */
export const useReplayStatus = () =>
  useQuery({
    queryKey: qk.replayStatus,
    queryFn: api.replayStatus,
    staleTime: 60_000,
    refetchInterval: 60_000,
  });

/** v2.6 — state-grounded chat (LLM karar vermez; backend guard'lı). */
export const useChat = () =>
  useMutation({ mutationFn: (message: string) => api.chat(message) });

/** UX-A15 — Trade Tickets (broker handoff payload). */
export const useTradeTickets = () =>
  useQuery({
    queryKey: qk.tradeTickets,
    queryFn: api.tradeTickets,
    staleTime: 10_000,
    refetchInterval: 15_000,
  });

/** UX-A16 — Notifications (observer; karar vermez). */
export const useNotifications = () =>
  useQuery({
    queryKey: qk.notifications,
    queryFn: () => api.notifications(false),
    staleTime: 5_000,
    refetchInterval: 10_000,
  });

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

/** Raporcu agent — başlık başlık deterministik özet. SSE tick.complete'te
 *  de invalidate edilir (useEventStream), polling fallback. */
export const useAgentBriefing = () =>
  useQuery({
    queryKey: qk.agentBriefing,
    queryFn: api.agentBriefing,
    refetchInterval: 15_000,
    staleTime: 5_000,
  });

/** G5 — owner reset (tek manuel çıkış yolu; otomatik reset yok). */
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
