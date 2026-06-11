"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { qk } from "@/lib/queries/keys";

/**
 * Manuel/keyboard-driven refresh için tek nokta. Tüm canlı sorguları
 * (state, paper trading) invalidate eder; statik olanlara (ai-report)
 * dokunmaz.
 */
export function useRealtimeRefresh() {
  const qc = useQueryClient();
  return useCallback(() => {
    qc.invalidateQueries({ queryKey: qk.regimeReport });
    qc.invalidateQueries({ queryKey: qk.dashboardState });
    qc.invalidateQueries({ queryKey: qk.paperTradingState });
  }, [qc]);
}
