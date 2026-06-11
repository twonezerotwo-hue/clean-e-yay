"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { qk } from "./keys";

export const useHealth = () =>
  useQuery({ queryKey: qk.health, queryFn: api.health, refetchInterval: 30_000 });

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

export const useRiskHalts = () =>
  useQuery({
    queryKey: qk.riskHalts,
    queryFn: api.riskHalts,
    staleTime: 15_000,
    refetchInterval: 30_000,
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
