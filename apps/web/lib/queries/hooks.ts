"use client";

import { useQuery } from "@tanstack/react-query";

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
