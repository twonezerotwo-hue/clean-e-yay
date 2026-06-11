/**
 * HTTP client. Tek `fetchJSON` helper'ı, fetch'in ince sarmalayıcısı.
 * Tüm tipler `types/generated/api.ts`'den gelir.
 */
import type {
  AIReport,
  DashboardState,
  Health,
  LearningSummary,
  PaperTradingState,
  RegimeReport,
  TickResult,
} from "@/types/generated/api";

const BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    throw new Error(`API ${res.status} ${path}: ${await res.text().catch(() => "")}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetchJSON<Health>("/api/v1/health"),
  regimeReport: () => fetchJSON<RegimeReport>("/api/v1/regime-report/current"),
  dashboardState: () => fetchJSON<DashboardState>("/api/v1/dashboard/state"),
  aiReport: () => fetchJSON<AIReport>("/api/v1/ai-report/current"),
  paperTradingState: () =>
    fetchJSON<PaperTradingState>("/api/v1/paper-trading/state"),
  paperTradingTick: () =>
    fetchJSON<TickResult>("/api/v1/paper-trading/tick", { method: "POST" }),
  learningSummary: () =>
    fetchJSON<LearningSummary>("/api/v1/learning/summary"),
};
