"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";

import { PanelFrame } from "@/components/shell/PanelFrame";
import {
  useAgentMatrix,
  useCalibration,
  useCockpitBrief,
  useDashboardState,
  useDataSnapshot,
  useDecisionMatrix,
  useMistakes,
  usePaperTradingState,
  useRegimeReport,
  useRiskHalts,
  useShadowComparison,
  useSystemHealth,
  useTradeTickets,
} from "@/lib/queries/hooks";
import { selectAgentBrief } from "@/lib/selectors/cockpit";
import { selectHaltActive } from "@/lib/selectors/halts";
import { selectAgentQuorum } from "@/lib/selectors/dashboard";
import type { TradeTicket } from "@/types/generated/api";

type CheckItem = {
  id: string;
  title: string;
  source: string;
  passed: boolean;
  detail: string;
  metric?: string;
};

const CYCLE_MS = 60_000;
const CHECK_COUNT = 10;
const STEP_MS = CYCLE_MS / CHECK_COUNT;

function sideToDirection(side?: string | null) {
  if (side === "long") return "bullish";
  if (side === "short") return "bearish";
  return null;
}

function formatTime(ms: number) {
  const seconds = Math.max(0, Math.ceil(ms / 1000));
  return `${seconds}s`;
}

function isHardRiskAction(action?: string | null) {
  return action === "NO_POSITION_INCREASE" || action === "RISK_REDUCE" || action === "KILL_SWITCH";
}

function statusLabel(passed: boolean) {
  return passed ? "ONAY" : "GEÇERSİZ";
}

function statusClass(passed: boolean) {
  return passed
    ? "border-emerald-300/55 bg-emerald-400/12 text-emerald-200 shadow-[0_0_24px_rgba(52,211,153,0.22)]"
    : "border-red-300/55 bg-red-400/12 text-red-200 shadow-[0_0_24px_rgba(248,113,113,0.18)]";
}

function CheckBadge({ passed }: { passed: boolean }) {
  return (
    <span
      className={`readiness-mark ${passed ? "readiness-mark-ok" : "readiness-mark-bad"} ${statusClass(passed)}`}
      aria-label={statusLabel(passed)}
    />
  );
}

function ScoreRing({ passed, total }: { passed: number; total: number }) {
  const pct = total > 0 ? Math.round((passed / total) * 100) : 0;
  return (
    <div
      className="readiness-score-ring"
      style={{ "--readiness-score": `${pct}%` } as CSSProperties}
      aria-label={`${passed} / ${total} onay`}
    >
      <div className="readiness-score-ring-inner">
        <span className="text-4xl font-black leading-none text-emerald-200">{passed}</span>
        <span className="text-sm text-white/52">/{total}</span>
      </div>
    </div>
  );
}

function TradeTicketMini({ ticket }: { ticket?: TradeTicket }) {
  const rows = ticket
    ? [
        ["YON", ticket.side.toUpperCase()],
        ["GIRIS", ticket.summary.entry_price.toLocaleString("en-US")],
        ["ZARAR KES", ticket.summary.stop_loss.toLocaleString("en-US")],
        ["KAR HEDEFI", ticket.summary.take_profit.toLocaleString("en-US")],
        ["BUYUKLUK", `$${Math.round(ticket.summary.size_usd).toLocaleString("en-US")}`],
        ["R:R", `1:${ticket.summary.rr_ratio.toFixed(2)}`],
        ["GECERLILIK", ticket.display.expiry_text],
      ]
    : [
        ["YON", "---"],
        ["GIRIS", "---"],
        ["ZARAR KES", "---"],
        ["KAR HEDEFI", "---"],
        ["BUYUKLUK", "---"],
        ["R:R", "---"],
        ["GECERLILIK", "---"],
      ];

  return (
    <aside className="readiness-ticket-card">
      <div className="readiness-ticket-glow" />
      <div className="relative z-10">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-2xl font-black leading-none text-white">Trade Ticket</div>
            <div className="mt-1 text-xs text-white/50">broker'a manuel girmeden tek bakis kart</div>
          </div>
          <span className={ticket ? "readiness-ticket-live" : "readiness-ticket-empty"}>
            {ticket ? "HAZIR" : "YOK"}
          </span>
        </div>

        <div className="mt-5 grid gap-2 text-xs">
          {rows.map(([label, value]) => (
            <div key={label} className="grid grid-cols-[92px_1fr] items-center gap-3">
              <span className="font-mono text-[10px] uppercase tracking-widest text-sky-200/55">{label}</span>
              <span className="min-w-0 truncate text-right font-mono text-white/78">{value}</span>
            </div>
          ))}
        </div>

        <div className="readiness-ticket-radar" aria-hidden="true">
          <span className="readiness-ticket-candle readiness-ticket-candle-a" />
          <span className="readiness-ticket-candle readiness-ticket-candle-b" />
          <span className="readiness-ticket-candle readiness-ticket-candle-c" />
          <span className="readiness-ticket-candle readiness-ticket-candle-d" />
        </div>

        <div className="mt-5 rounded-md border border-white/10 bg-white/[0.03] px-3 py-2">
          <div className="flex items-center justify-between gap-3 text-xs">
            <span className="font-mono uppercase tracking-widest text-white/42">Durum</span>
            <span className={ticket ? "font-black text-emerald-300" : "font-black text-red-300"}>
              {ticket ? `${ticket.symbol} ${ticket.side.toUpperCase()}` : "TICKET YOK"}
            </span>
          </div>
        </div>
      </div>
    </aside>
  );
}

function AgentHologram() {
  return (
    <aside className="readiness-agent-hologram" aria-hidden="true">
      <div className="readiness-agent-chip">
        <span>AI AGENT</span>
        <strong>NEXUS 7</strong>
        <em>CALISIYOR</em>
      </div>
      <span className="readiness-agent-data-thread" />
      <span className="readiness-agent-ring readiness-agent-ring-a" />
      <span className="readiness-agent-ring readiness-agent-ring-b" />
      <span className="readiness-agent-ring readiness-agent-ring-c" />
      <span className="readiness-agent-head" />
      <span className="readiness-agent-temple">2047</span>
      <span className="readiness-agent-neck" />
      <span className="readiness-agent-body" />
      <span className="readiness-agent-arm readiness-agent-arm-think" />
      <span className="readiness-agent-arm readiness-agent-arm-rest" />
      <span className="readiness-agent-core" />
      <span className="readiness-agent-chest">2047</span>
      <span className="readiness-agent-base" />
      <span className="readiness-agent-particle readiness-agent-particle-a" />
      <span className="readiness-agent-particle readiness-agent-particle-b" />
      <span className="readiness-agent-particle readiness-agent-particle-c" />
      <span className="readiness-agent-particle readiness-agent-particle-d" />
      <span className="readiness-agent-particle readiness-agent-particle-e" />
      <span className="readiness-agent-particle readiness-agent-particle-f" />
    </aside>
  );
}

function CheckRow({
  check,
  index,
  active,
  faded,
  progress,
}: {
  check: CheckItem;
  index: number;
  active: boolean;
  faded?: boolean;
  progress?: number;
}) {
  return (
    <li
      className={`readiness-sequence-card ${active ? "readiness-sequence-card-active" : ""} ${faded ? "readiness-sequence-card-faded" : ""}`}
    >
      <div className="readiness-sequence-node-wrap">
        <span className="readiness-sequence-index">{String(index + 1).padStart(2, "0")}</span>
        <CheckBadge passed={check.passed} />
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-black leading-tight text-white/92 2xl:text-base">{check.title}</h3>
          <span className={check.passed ? "readiness-status-ok" : "readiness-status-bad"}>
            {active ? `${statusLabel(check.passed)} · taraniyor` : statusLabel(check.passed)}
          </span>
        </div>
        <div className="mt-1 text-[11px] font-mono text-sky-300/82">{check.source}</div>
        <div className="mt-1 text-xs font-mono text-white/70">{check.metric}</div>
        <p className="mt-1 line-clamp-2 text-xs leading-5 text-white/58">{check.detail}</p>
        {active ? (
          <div className="mt-3 h-1 overflow-hidden rounded-full bg-white/10">
            <div
              className={check.passed ? "h-full bg-sky-300" : "h-full bg-red-300"}
              style={{ width: `${progress ?? 0}%` }}
            />
          </div>
        ) : null}
      </div>
    </li>
  );
}

export function ExecutionReadinessPanel() {
  const cycleStartedAt = useRef(Date.now());
  const [now, setNow] = useState(() => Date.now());

  const system = useSystemHealth();
  const snapshot = useDataSnapshot();
  const dashboard = useDashboardState();
  const cockpit = useCockpitBrief();
  const halts = useRiskHalts();
  const tickets = useTradeTickets();
  const matrix = useDecisionMatrix();
  const agentMatrix = useAgentMatrix();
  const regime = useRegimeReport();
  const paper = usePaperTradingState();
  const calibration = useCalibration();
  const mistakes = useMistakes();
  const shadow = useShadowComparison();

  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(interval);
  }, []);

  const cycleElapsed = (now - cycleStartedAt.current) % CYCLE_MS;
  const activeIndex = Math.min(CHECK_COUNT - 1, Math.floor(cycleElapsed / STEP_MS));
  const activeStepProgress = ((cycleElapsed % STEP_MS) / STEP_MS) * 100;
  const cycleProgress = (cycleElapsed / CYCLE_MS) * 100;

  const refetchers = useMemo(
    () => [
      () => Promise.all([snapshot.refetch(), system.refetch()]),
      () => Promise.all([system.refetch(), halts.refetch()]),
      () => Promise.all([dashboard.refetch(), halts.refetch(), cockpit.refetch()]),
      () => cockpit.refetch(),
      () => tickets.refetch(),
      () => matrix.refetch(),
      () => Promise.all([dashboard.refetch(), agentMatrix.refetch()]),
      () => Promise.all([regime.refetch(), matrix.refetch()]),
      () => Promise.all([paper.refetch(), calibration.refetch(), mistakes.refetch(), shadow.refetch()]),
      () => tickets.refetch(),
    ],
    [
      agentMatrix,
      calibration,
      cockpit,
      dashboard,
      halts,
      matrix,
      mistakes,
      paper,
      regime,
      shadow,
      snapshot,
      system,
      tickets,
    ],
  );

  useEffect(() => {
    void refetchers[activeIndex]?.();
  }, [activeIndex, refetchers]);

  const brief = selectAgentBrief(cockpit.data);
  const activeTicket = tickets.data?.tickets.find((ticket) => ticket.status === "active");
  const ticketDirection = sideToDirection(activeTicket?.side);
  const ticketSafetyErrors = activeTicket?.display?.safety_lines?.filter((line) => line.level === "error").length ?? 0;
  const ticketExpired = activeTicket?.expires_at ? Date.parse(activeTicket.expires_at) <= Date.now() : true;

  const checks = useMemo<CheckItem[]>(() => {
    const dqs = snapshot.data?.dqs;
    const providers = Object.entries(snapshot.data?.provider_status ?? {});
    const downProviders = providers.filter(([, provider]) => provider.status === "down").map(([name]) => name);
    const degradedProviders = providers.filter(([, provider]) => provider.status === "degraded").map(([name]) => name);
    const staleWorkers = system.data?.stale_workers ?? [];
    const haltActive = selectHaltActive(halts.data) || Boolean(system.data?.risk_halt_status?.active);
    const riskGate = dashboard.data?.risk_gate;
    const quorum = selectAgentQuorum(dashboard.data);
    const actionableCandidates = brief?.top_candidates?.filter(
      (candidate) =>
        candidate.actionable &&
        candidate.direction !== "neutral" &&
        (candidate.score ?? 0) >= 55,
    ) ?? [];
    const matrixCells = matrix.data?.cells ?? [];
    const actionableMatrixCells = matrixCells.filter(
      (cell) =>
        cell.actionable &&
        (cell.action === "open_long" || cell.action === "open_short") &&
        (!activeTicket || cell.symbol === activeTicket.symbol),
    );
    const matrixDirectionOk = !activeTicket
      ? actionableMatrixCells.length > 0
      : actionableMatrixCells.some((cell) =>
          activeTicket.side === "long" ? cell.action === "open_long" : cell.action === "open_short",
        );
    const eventRestrictive = Boolean(regime.data?.event_risk?.restrictive || matrix.data?.event_risk?.restrictive);
    const structureWarnings =
      (matrix.data?.derivatives?.length ?? 0) +
      (matrix.data?.volatility?.length ?? 0) +
      (matrix.data?.options?.length ?? 0) +
      (matrix.data?.catalysts?.length ?? 0);
    const positionAlerts = paper.data?.position_rechecks?.filter(
      (row) => row.verdict === "REDUCE" || row.verdict === "EXIT_RECOMMEND",
    ).length ?? 0;
    const duplicateWarnings = paper.data?.duplicate_warning?.length ?? 0;
    const calibrationData = calibration.data;
    const calibrationReady = calibrationData
      ? calibrationData.params.status === "fitted" ||
        calibrationData.samples_in_state >= calibrationData.min_required
      : false;
    const avoidMistakes = mistakes.data?.verdicts?.filter((verdict) => verdict.action === "AVOID").length ?? 0;
    const shadowConflicts = shadow.data
      ? shadow.data.summary.disagree_direction +
        shadow.data.summary.live_only_entry +
        shadow.data.summary.shadow_only_entry
      : 0;
    const agentMatrixBlocks = isHardRiskAction(agentMatrix.data?.risk_action);
    const ticketSummary = activeTicket?.summary;
    const ticketPassed =
      Boolean(activeTicket) &&
      !ticketExpired &&
      ticketSafetyErrors === 0 &&
      (ticketSummary?.rr_ratio ?? 0) >= 1.5 &&
      (ticketSummary?.confidence_calibrated ?? 0) >= 0.5;

    return [
      {
        id: "data_quality",
        title: "Veri kalitesi ve sağlayıcılar",
        source: "DataQuality / Provider / Snapshot",
        passed:
          Boolean(snapshot.data && system.data) &&
          dqs?.status !== "BLOCKED" &&
          (dqs?.score ?? 0) >= 70 &&
          downProviders.length === 0,
        metric: dqs ? `DQS ${Math.round(dqs.score)} · ${dqs.status}` : "DQS yok",
        detail:
          downProviders.length > 0
            ? `Down provider: ${downProviders.join(", ")}`
            : degradedProviders.length > 0
              ? `Degraded provider var ama hard down yok: ${degradedProviders.join(", ")}`
              : "Snapshot, DQS ve provider katmanı işlem kontrolü için okunabilir.",
      },
      {
        id: "system_safety",
        title: "Sistem güvenliği",
        source: "SystemHealth / RiskHalts",
        passed:
          Boolean(system.data) &&
          system.data?.paper_safe === true &&
          system.data?.no_execution === true &&
          staleWorkers.length === 0 &&
          !haltActive,
        metric: `${system.data?.paper_safe ? "PAPER_SAFE" : "paper?"} · ${system.data?.no_execution ? "NO_EXECUTION" : "exec?"}`,
        detail: haltActive
          ? "Aktif risk halt var; yeni işlem kontrolü kırmızı."
          : staleWorkers.length
            ? `Stale worker: ${staleWorkers.join(", ")}`
            : "Paper-safe ve no-execution guard aktif; worker/halt engeli yok.",
      },
      {
        id: "risk_gate",
        title: "Risk kapısı",
        source: "RiskDurumu / RiskGate",
        passed:
          Boolean(dashboard.data && cockpit.data) &&
          riskGate?.action === "HOLD" &&
          brief?.main_blocker?.code === "NONE" &&
          !haltActive,
        metric: riskGate ? `RiskGate ${riskGate.action}` : "RiskGate yok",
        detail:
          riskGate?.action !== "HOLD"
            ? riskGate?.reason ?? "RiskGate HOLD değil."
            : brief?.main_blocker?.code !== "NONE"
              ? brief?.main_blocker?.detail ?? brief?.main_blocker?.label ?? "Ana blocker temiz değil."
              : "RiskGate ve ana blocker yeni girişe engel göstermiyor.",
      },
      {
        id: "agent_permission",
        title: "Agent işlem izni",
        source: "AgentNarrator / AgentBrief / Decision",
        passed:
          Boolean(brief) &&
          brief?.can_act === true &&
          brief?.status === "ACTIONABLE" &&
          brief?.data_mode !== "BLOCKED",
        metric: brief ? `${brief.status} · ${brief.data_mode}` : "Agent yok",
        detail:
          brief?.can_act && brief.status === "ACTIONABLE"
            ? brief.recommended_stance
            : brief?.summary ?? "Agent brief henüz okunmadı veya actionable değil.",
      },
      {
        id: "trade_signal",
        title: "Aktif sinyal / ticket adayı",
        source: "CommandSignals / TradeTicket",
        passed: Boolean(activeTicket) && actionableCandidates.length > 0,
        metric: activeTicket
          ? `${activeTicket.symbol} ${activeTicket.side.toUpperCase()} · ${activeTicket.timeframe}`
          : `${actionableCandidates.length} actionable aday`,
        detail: activeTicket
          ? `Broker handoff ticket bulundu; aday sayısı ${actionableCandidates.length}.`
          : "Aktif trade ticket yok; manuel işlem açma kontrolü geçmez.",
      },
      {
        id: "timeframe_matrix",
        title: "Timeframe matrix uyumu",
        source: "TimeframeMatrix",
        passed:
          Boolean(matrix.data) &&
          matrix.data?.suspended !== true &&
          matrix.data?.dqs_status !== "BLOCKED" &&
          matrixDirectionOk,
        metric: `${actionableMatrixCells.length} actionable hücre`,
        detail:
          matrix.data?.suspended === true
            ? "Matrix suspended; tüm TF'lerde yeni işlem yok."
            : matrixDirectionOk
              ? "Ticket yönü ile matrix actionable hücreleri uyumlu."
              : "Ticket yönünü destekleyen actionable TF hücresi bulunamadı.",
      },
      {
        id: "agent_consensus",
        title: "Agent quorum ve yön birliği",
        source: "AgentVotes / AgentMatrix",
        passed:
          Boolean(dashboard.data) &&
          quorum.quorumReached &&
          quorum.leadCount >= 2 &&
          !agentMatrixBlocks &&
          (!ticketDirection || quorum.leadDirection === ticketDirection),
        metric: `lead ${quorum.leadDirection ?? "-"} · ${quorum.leadCount}/${quorum.votes.length}`,
        detail: agentMatrixBlocks
          ? `Agent matrix risk action bloklayıcı: ${agentMatrix.data?.risk_action}`
          : quorum.quorumReached
            ? "Agent quorum yönü ticket ile çelişmiyor."
            : "Agent quorum oluşmadı veya ticket yönüyle çelişiyor.",
      },
      {
        id: "market_structure",
        title: "Piyasa yapısı ve catalyst",
        source: "Derivatives / Volatility / Options / Catalyst",
        passed: Boolean(regime.data && matrix.data) && !eventRestrictive && structureWarnings === 0,
        metric: `uyarı ${structureWarnings} · event ${eventRestrictive ? "restrictive" : "clear"}`,
        detail: eventRestrictive
          ? regime.data?.event_risk?.reason ?? matrix.data?.event_risk?.reason ?? "Restrictive event risk var."
          : structureWarnings > 0
            ? "Türev/volatilite/options/catalyst katmanında kısıtlayıcı uyarı var."
            : "Makro/catalyst ve piyasa yapı katmanlarında hard kısıt görünmüyor.",
      },
      {
        id: "position_learning",
        title: "Pozisyon, öğrenme ve shadow kontrolü",
        source: "PositionChecks / Calibration / Mistake / Shadow",
        passed:
          Boolean(paper.data && calibration.data && mistakes.data) &&
          paper.data?.new_entries_disabled !== true &&
          duplicateWarnings === 0 &&
          positionAlerts === 0 &&
          calibrationReady &&
          avoidMistakes === 0 &&
          shadowConflicts === 0,
        metric: `pos alert ${positionAlerts} · avoid ${avoidMistakes} · shadow ${shadowConflicts}`,
        detail:
          paper.data?.new_entries_disabled === true
            ? "Paper state yeni girişleri kapatmış."
            : !calibrationReady
              ? "Kalibrasyon örnekleri yetersiz veya fitted değil."
              : avoidMistakes > 0
                ? "Mistake memory AVOID verdict üretiyor."
                : shadowConflicts > 0
                  ? "Shadow/live karşılaştırmasında entry veya yön çatışması var."
                  : "Pozisyon, kalibrasyon, mistake memory ve shadow katmanı temiz.",
      },
      {
        id: "ticket_integrity",
        title: "Trade ticket bütünlüğü",
        source: "TradeTicket",
        passed: ticketPassed,
        metric: activeTicket
          ? `R:R 1:${(ticketSummary?.rr_ratio ?? 0).toFixed(2)} · conf ${Math.round((ticketSummary?.confidence_calibrated ?? 0) * 100)}%`
          : "ticket yok",
        detail: !activeTicket
          ? "Aktif Trade Ticket yok."
          : ticketExpired
            ? "Ticket süresi dolmuş."
            : ticketSafetyErrors > 0
              ? "Ticket safety_lines içinde error var."
              : ticketPassed
                ? "Entry, SL, TP, R:R, confidence ve safety lines geçerli."
                : "Ticket var ama R:R veya confidence eşiği yetersiz.",
      },
    ];
  }, [
    activeTicket,
    agentMatrix.data,
    brief,
    calibration.data,
    cockpit.data,
    dashboard.data,
    halts.data,
    matrix.data,
    mistakes.data,
    paper.data,
    regime.data,
    shadow.data,
    snapshot.data,
    system.data,
    ticketExpired,
    ticketSafetyErrors,
  ]);

  const passedCount = checks.filter((check) => check.passed).length;
  const allPassed = passedCount === checks.length;
  const activeCheck = checks[activeIndex] ?? checks[0];
  const cycleRemaining = CYCLE_MS - cycleElapsed;
  const visibleChecks = checks.slice(0, 5);

  return (
    <PanelFrame id="execution_readiness" className="readiness-panel">
      <div className="readiness-panel-shell">
        <div className="readiness-frame-line readiness-frame-line-top" />
        <div className="readiness-frame-line readiness-frame-line-bottom" />

        <header className="readiness-header">
          <div className="readiness-logo">
            <span className="readiness-logo-mark" />
            <span className="font-mono text-xs font-black text-sky-300">2047</span>
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="text-3xl font-black tracking-tight text-white md:text-4xl">
              İşlem Açma Kontrol Döngüsü
            </h2>
            <p className="mt-1 text-sm text-white/68 md:text-base">
              10 kontrol / 60 saniyede tam tarama / frontend read-only
            </p>
          </div>
          <div className="hidden text-right md:block">
            <div className="font-mono text-2xl font-black text-sky-300">
              {new Intl.DateTimeFormat("tr-TR", {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              }).format(now)}
            </div>
            <div className="font-mono text-xs font-black uppercase tracking-widest text-sky-300/80">
              {new Intl.DateTimeFormat("tr-TR", {
                day: "2-digit",
                month: "long",
                year: "numeric",
              }).format(now)}
            </div>
          </div>
        </header>

        <div className="readiness-scene-grid">
          <section className="readiness-control-zone">
            <div className="readiness-mini-grid">
              <section className={`readiness-active-card ${allPassed ? "readiness-active-card-ok" : ""}`}>
                <div className="readiness-shield readiness-shield-mini" aria-hidden="true">
                  <span className="readiness-shield-core" />
                  <span className="readiness-shield-check" />
                </div>
                <div className="min-w-0">
                  <div className="text-2xl font-black text-emerald-300">
                    {allPassed ? "MANUEL REVIEW HAZIR" : "İŞLEM YOK"}
                  </div>
                  <div className="mt-1 flex flex-wrap items-end gap-2">
                    <span className="text-sm font-semibold text-white/78">kalan</span>
                    <span className="font-mono text-4xl font-black leading-none text-emerald-300">
                      {formatTime(cycleRemaining)}
                    </span>
                  </div>
                  <div className="mt-3 text-sm text-white/72">Şu an kontrol ediliyor</div>
                  <div className="font-black text-xl text-emerald-200">
                    {String(activeIndex + 1).padStart(2, "0")} / {activeCheck.title}
                  </div>
                  <p className="mt-2 max-w-xl text-sm leading-6 text-white/68">{activeCheck.detail}</p>
                  <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/10">
                    <div
                      className={activeCheck.passed ? "h-full bg-emerald-300" : "h-full bg-red-300"}
                      style={{ width: `${activeStepProgress}%` }}
                    />
                  </div>
                </div>
              </section>

              <section className="readiness-total-card">
                <ScoreRing passed={passedCount} total={checks.length} />
                <div className="min-w-0 flex-1">
                  <div className="text-lg font-black text-white">Toplam sonuç</div>
                  <div className="mt-2 flex items-end gap-2">
                    <span className="text-5xl font-black text-emerald-300">{passedCount}</span>
                    <span className="pb-2 text-xl font-semibold text-white/72">/ {checks.length} onay</span>
                  </div>
                  <div className="mt-3 h-px bg-sky-300/20" />
                  <p className="mt-3 text-sm leading-6 text-white/62">
                    Döngü bittiğinde başa sarar; aktif adım her 6 saniyede bir kendi veri grubunu yeniden okur.
                  </p>
                  <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/10">
                    <div
                      className={allPassed ? "h-full bg-emerald-300" : "h-full bg-amber-300"}
                      style={{ width: `${cycleProgress}%` }}
                    />
                  </div>
                </div>
              </section>
            </div>

            <ol className="readiness-sequence-flow">
              {visibleChecks.map((check, index) => (
                <CheckRow
                  key={check.id}
                  check={check}
                  index={index}
                  active={index === activeIndex}
                  faded={index > activeIndex + 1 || (activeIndex > 4 && index < 4)}
                  progress={activeStepProgress}
                />
              ))}
              <li className="readiness-sequence-more">
                <span>06-10</span>
                <strong>Derin kontroller akista</strong>
                <em>TF matrix / agent quorum / catalyst / shadow / ticket integrity</em>
              </li>
            </ol>

            <div className="readiness-footnote">
              <span className="readiness-info-icon">i</span>
              <span>
                Bu panel emir üretmez ve backend kararını değiştirmez. Sadece mevcut dashboard verilerini aynı sırayla okuyup manuel işlem kontrolü için tek ekranda onay/X durumuna indirger.
              </span>
            </div>
          </section>

          <section className="readiness-ai-zone">
            <AgentHologram />
            <TradeTicketMini ticket={activeTicket} />
          </section>
        </div>
      </div>
    </PanelFrame>
  );
}
