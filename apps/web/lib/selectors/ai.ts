import type { AIReport, LLMMeta, PersonaSection } from "@/types/generated/api";

/** v2.6 — AI report persona bölümleri (frontend hesap yapmaz, backend sırası korunur). */
export const selectPersonaSections = (r: AIReport | undefined): PersonaSection[] =>
  r?.personas ?? [];

export const selectNoActionableDecision = (r: AIReport | undefined): boolean =>
  Boolean(r?.no_actionable_decision);

export const selectTimeframeSummaryLines = (r: AIReport | undefined): string[] =>
  r?.timeframe_summary?.lines ?? [];

/** Provenance rozeti — LLM_GENERATED (model adı) veya DETERMINISTIC. */
export const selectLLMBadge = (
  llm: LLMMeta | undefined,
): { label: string; live: boolean } => {
  if (llm?.source === "llm" && llm.model) {
    return { label: `LLM_GENERATED · ${llm.model}`, live: true };
  }
  return { label: "DETERMINISTIC", live: false };
};

export const selectLLMSubtitle = (r: AIReport | undefined): string => {
  const llm = r?.llm;
  if (!llm) return r?.token_usage?.cached ? "cache" : "yeni";
  const parts: string[] = [llm.mode ?? "off"];
  if (llm.cached) parts.push("cache");
  if (llm.source === "fallback" && llm.fallback_reason) parts.push(llm.fallback_reason);
  return parts.join(" · ");
};
