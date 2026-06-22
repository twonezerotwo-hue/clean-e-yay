"use client";

import {
  useAgentBriefing,
  useAgentMatrix,
  useAIReport,
  useCalibration,
  useCockpitBrief,
  useDashboardState,
  useDataSnapshot,
  useDecisionMatrix,
  useHealth,
  useLearningSummary,
  useMarketSessions,
  useMistakes,
  useNotifications,
  usePaperTradingState,
  useRebalanceProposal,
  useRegimeReport,
  useReplayStatus,
  useRiskCorrelation,
  useRiskHalts,
  useShadowComparison,
  useSystemHealth,
  useTfWeights,
  useTradeTickets,
} from "@/lib/queries/hooks";

type QueryLike = {
  data: unknown;
  isLoading: boolean;
  isError: boolean;
  dataUpdatedAt: number;
  error: unknown;
};

type EndpointSpec = {
  group: string;
  name: string;
  method: "GET";
  path: string;
  query: QueryLike;
};

function formatUpdatedAt(value: number) {
  if (!value) return "bekleniyor";
  const diff = Math.max(0, Date.now() - value);
  if (diff < 60_000) return `${Math.max(1, Math.round(diff / 1000))} sn once`;
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)} dk once`;
  return `${Math.round(diff / 3_600_000)} sa once`;
}

function payloadKeys(data: unknown) {
  if (!data || typeof data !== "object") return "payload yok";
  const keys = Object.keys(data as Record<string, unknown>);
  if (!keys.length) return "bos obje";
  return keys.slice(0, 8).join(" / ");
}

function payloadSize(data: unknown) {
  if (data == null) return "0 B";
  try {
    const size = JSON.stringify(data).length;
    if (size < 1024) return `${size} B`;
    return `${(size / 1024).toFixed(1)} KB`;
  } catch {
    return "olculemedi";
  }
}

function payloadPreview(data: unknown) {
  if (data == null) return "null";
  try {
    const raw = JSON.stringify(data, null, 2);
    return raw.length > 900 ? `${raw.slice(0, 900)}\n...` : raw;
  } catch {
    return String(data);
  }
}

function EndpointCard({ endpoint }: { endpoint: EndpointSpec }) {
  const status = endpoint.query.isLoading
    ? "LOADING"
    : endpoint.query.isError
      ? "ERROR"
      : "READY";
  const tone =
    status === "READY"
      ? "border-emerald-400/24 text-emerald-300"
      : status === "ERROR"
        ? "border-red-400/32 text-red-300"
        : "border-amber-400/28 text-amber-300";

  return (
    <article className="rounded-xl border border-white/10 bg-black/28 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded border px-1.5 py-0.5 text-[9px] font-semibold ${tone}`}>
              {status}
            </span>
            <span className="font-mono text-[10px] uppercase tracking-widest text-accent-cyan/78">
              {endpoint.method}
            </span>
          </div>
          <h4 className="mt-2 text-sm font-semibold text-white/88">{endpoint.name}</h4>
          <p className="mt-1 break-all font-mono text-[10px] text-white/42">{endpoint.path}</p>
        </div>
        <div className="shrink-0 text-right font-mono text-[10px] uppercase tracking-widest text-white/34">
          <div>{endpoint.group}</div>
          <div className="mt-1 normal-case tracking-normal text-white/46">
            {formatUpdatedAt(endpoint.query.dataUpdatedAt)}
          </div>
        </div>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <div className="rounded-lg border border-white/8 bg-white/[0.025] px-2.5 py-2">
          <div className="text-[9px] uppercase tracking-widest text-white/32">Top-level alanlar</div>
          <div className="mt-1 text-[11px] leading-5 text-white/62">{payloadKeys(endpoint.query.data)}</div>
        </div>
        <div className="rounded-lg border border-white/8 bg-white/[0.025] px-2.5 py-2">
          <div className="text-[9px] uppercase tracking-widest text-white/32">Payload</div>
          <div className="mt-1 font-mono text-[11px] text-white/62">{payloadSize(endpoint.query.data)}</div>
        </div>
      </div>

      {endpoint.query.isError ? (
        <div className="mt-3 rounded-lg border border-red-400/20 bg-red-400/8 px-2.5 py-2 text-[11px] leading-5 text-red-100/82">
          {endpoint.query.error instanceof Error ? endpoint.query.error.message : "Endpoint okunamadi."}
        </div>
      ) : (
        <pre className="mt-3 max-h-52 overflow-auto rounded-lg border border-white/8 bg-[#02050b]/82 p-2.5 text-[10px] leading-4 text-white/54">
          {endpoint.query.isLoading ? "Yukleniyor..." : payloadPreview(endpoint.query.data)}
        </pre>
      )}
    </article>
  );
}

function GroupBlock({ group, endpoints }: { group: string; endpoints: EndpointSpec[] }) {
  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between gap-3 border-b border-white/10 pb-2">
        <h3 className="text-xs font-semibold uppercase tracking-[0.22em] text-white/72">{group}</h3>
        <span className="font-mono text-[10px] uppercase tracking-widest text-white/36">
          {endpoints.length} endpoint
        </span>
      </div>
      <div className="grid gap-3 xl:grid-cols-2">
        {endpoints.map((endpoint) => (
          <EndpointCard key={endpoint.path} endpoint={endpoint} />
        ))}
      </div>
    </section>
  );
}

export function BackendDataSpinePanel() {
  const endpoints: EndpointSpec[] = [
    { group: "system", name: "Health", method: "GET", path: "/api/v1/health", query: useHealth() },
    { group: "system", name: "System Health", method: "GET", path: "/api/v1/system/health", query: useSystemHealth() },
    { group: "system", name: "Replay Status", method: "GET", path: "/api/v1/replay/status", query: useReplayStatus() },

    { group: "agent", name: "Cockpit Brief", method: "GET", path: "/api/v1/cockpit/brief", query: useCockpitBrief() },
    { group: "agent", name: "Agent Briefing", method: "GET", path: "/api/v1/agent/briefing", query: useAgentBriefing() },
    { group: "agent", name: "AI Report", method: "GET", path: "/api/v1/ai-report/current", query: useAIReport() },
    { group: "agent", name: "Notifications", method: "GET", path: "/api/v1/notifications?limit=50&unread_only=false", query: useNotifications() },

    { group: "decision", name: "Dashboard State", method: "GET", path: "/api/v1/dashboard/state", query: useDashboardState() },
    { group: "decision", name: "Decision Matrix", method: "GET", path: "/api/v1/decision/matrix", query: useDecisionMatrix() },
    { group: "decision", name: "Agent Matrix", method: "GET", path: "/api/v1/technical/agent-matrix", query: useAgentMatrix() },
    { group: "decision", name: "Shadow Comparison", method: "GET", path: "/api/v1/decision/shadow", query: useShadowComparison() },

    { group: "market", name: "Regime Report", method: "GET", path: "/api/v1/regime-report/current", query: useRegimeReport() },
    { group: "market", name: "Data Snapshot", method: "GET", path: "/api/v1/data/snapshot", query: useDataSnapshot() },
    { group: "market", name: "Market Sessions", method: "GET", path: "/api/v1/market-sessions/current", query: useMarketSessions() },
    { group: "market", name: "Risk Correlation", method: "GET", path: "/api/v1/risk/correlation", query: useRiskCorrelation() },

    { group: "risk-execution", name: "Risk Halts", method: "GET", path: "/api/v1/risk/halts", query: useRiskHalts() },
    { group: "risk-execution", name: "Paper Trading State", method: "GET", path: "/api/v1/paper-trading/state", query: usePaperTradingState() },
    { group: "risk-execution", name: "Trade Tickets", method: "GET", path: "/api/v1/paper-trading/tickets", query: useTradeTickets() },

    { group: "learning", name: "Learning Summary", method: "GET", path: "/api/v1/learning/summary", query: useLearningSummary() },
    { group: "learning", name: "Rebalance Proposal", method: "GET", path: "/api/v1/learning/rebalance/proposal", query: useRebalanceProposal() },
    { group: "learning", name: "Calibration", method: "GET", path: "/api/v1/learning/calibration", query: useCalibration() },
    { group: "learning", name: "TF Weights", method: "GET", path: "/api/v1/learning/tf-weights", query: useTfWeights() },
    { group: "learning", name: "Mistakes", method: "GET", path: "/api/v1/learning/mistakes", query: useMistakes() },
  ];

  const readyCount = endpoints.filter((endpoint) => !endpoint.query.isLoading && !endpoint.query.isError).length;
  const errorCount = endpoints.filter((endpoint) => endpoint.query.isError).length;
  const groups = Array.from(new Set(endpoints.map((endpoint) => endpoint.group)));

  return (
    <div className="space-y-5 rounded-2xl border border-white/10 bg-black/24 p-4">
      <header className="flex flex-col gap-3 border-b border-white/10 pb-4 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-[0.26em] text-accent-cyan/78">
            Backend Data Spine
          </div>
          <h2 className="mt-1 font-display text-2xl text-white/92">
            Tum read-only backend endpointleri
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-white/52">
            Katman 3 ham veri toplama alanidir. Burada karar yorumu veya frontend hesaplamasi yok;
            endpoint durumlari ve payload onizlemeleri dogrudan gorunur.
          </p>
        </div>
        <div className="grid min-w-[18rem] grid-cols-3 gap-2 text-center">
          <div className="rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2">
            <div className="font-display text-xl text-white/88">{endpoints.length}</div>
            <div className="text-[9px] uppercase tracking-widest text-white/38">endpoint</div>
          </div>
          <div className="rounded-lg border border-emerald-400/18 bg-emerald-400/[0.045] px-3 py-2">
            <div className="font-display text-xl text-emerald-300">{readyCount}</div>
            <div className="text-[9px] uppercase tracking-widest text-white/38">ready</div>
          </div>
          <div className="rounded-lg border border-red-400/18 bg-red-400/[0.045] px-3 py-2">
            <div className="font-display text-xl text-red-300">{errorCount}</div>
            <div className="text-[9px] uppercase tracking-widest text-white/38">error</div>
          </div>
        </div>
      </header>

      <div className="space-y-6">
        {groups.map((group) => (
          <GroupBlock
            key={group}
            group={group}
            endpoints={endpoints.filter((endpoint) => endpoint.group === group)}
          />
        ))}
      </div>
    </div>
  );
}
