import type { DashboardState } from "@/types/generated/api";

export const selectModuleHealthList = (s: DashboardState | undefined) =>
  Object.entries(s?.module_health ?? {}).map(([id, v]) => ({ id, ...v }));

export const selectDegradedModules = (s: DashboardState | undefined) =>
  selectModuleHealthList(s).filter((m) => m.status !== "ok");

export const selectAgentQuorum = (s: DashboardState | undefined) => {
  const votes = s?.agent_votes ?? [];
  const tally: Record<string, number> = {};
  for (const v of votes) tally[v.direction] = (tally[v.direction] ?? 0) + 1;
  const top = Object.entries(tally).sort((a, b) => b[1] - a[1])[0];
  return {
    votes,
    leadDirection: top?.[0] ?? null,
    leadCount: top?.[1] ?? 0,
    quorumReached: !!s?.quorum_reached,
  };
};
