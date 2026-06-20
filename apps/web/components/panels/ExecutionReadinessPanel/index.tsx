"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
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

function statusIcon(passed: boolean) {
  return passed ? "✓" : "X";
}

function statusLabel(passed: boolean) {
  return passed ? "ONAY" : "GEÇERSİZ";
}

function statusClass(passed: boolean) {
  return passed
    ? "border-emerald-400/45 bg-emerald-400/12 text-emerald-200 shadow-[0_0_18px_rgba(52,211,153,0.16)]"
    : "border-red-400/45 bg-red-400/12 text-red-200 shadow-[0_0_18px_rgba(248,113,113,0.12)]";
}

function CheckBadge({ passed }: { passed: boolean }) {
  return (
    <span
      className={`grid h-8 w-8 shrink-0 place-items-center rounded-full border text-sm font-black ${statusClass(passed)}`}
      aria-label={statusLabel(passed)}
    >
      {statusIcon(passed)}
    </span>
  );
}

function CheckRow({
  check,
  index,
  active,
}: {
  check: CheckItem;
  index: number;
  active: boolean;
}) {
  return (
    <li
      className={`rounded-lg border px-3 py-2 transition-colors ${
        active
          ? "border-accent-cyan/45 bg-accent-cyan/8"
          : "border-white/10 bg-black/24"
      }`}
    >
      <div className="flex items-start gap-3">
        <CheckBadge passed={check.passed} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-2">
              <span className="font-mono text-[10px] text-white/35">{String(index + 1).padStart(2, "0")}</span>
              <span className="truncate text-sm font-medium text-white/88">{check.title}</span>
            </div>
            <span className={`rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-widest ${statusClass(check.passed)}`}>
              {statusLabel(check.passed)}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
            <span className="font-mono uppercase tracking-widest text-accent-cyan/65">{check.source}</span>
            {check.metric ? <span className="font-mono text-white/62">{check.metric}</span> : null}
          </div>
          <p className="mt-1 text-xs leading-5 text-white/60">{check.detail}</p>
        </div>
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

  return (
    <PanelFrame id="execution_readiness" className="border-emerald-400/18">
      <PanelHeader
        title="İşlem Açma Kontrol Döngüsü"
        subtitle="10 kontrol · 60 saniyede tam tarama · frontend read-only"
        actions={
          <div className="flex flex-wrap justify-end gap-2">
            <span className={`rounded border px-2 py-1 text-[10px] font-semibold uppercase tracking-widest ${statusClass(allPassed)}`}>
              {allPassed ? "MANUEL REVIEW HAZIR" : "İŞLEM YOK"}
            </span>
            <span className="rounded border border-white/10 bg-black/30 px-2 py-1 font-mono text-[10px] text-white/55">
              kalan {formatTime(cycleRemaining)}
            </span>
          </div>
        }
      />

      <div className="space-y-4">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_260px]">
          <div className="rounded-lg border border-white/10 bg-black/28 p-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-[10px] uppercase tracking-[0.22em] text-white/42">Şu an kontrol ediliyor</div>
                <div className="mt-1 font-display text-base text-white/90">
                  {String(activeIndex + 1).padStart(2, "0")} · {activeCheck.title}
                </div>
                <p className="mt-1 text-xs text-white/55">{activeCheck.detail}</p>
              </div>
              <CheckBadge passed={activeCheck.passed} />
            </div>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10">
              <div
                className={activeCheck.passed ? "h-full bg-emerald-300" : "h-full bg-red-300"}
                style={{ width: `${activeStepProgress}%` }}
              />
            </div>
          </div>

          <div className="rounded-lg border border-white/10 bg-black/28 p-3">
            <div className="text-[10px] uppercase tracking-[0.22em] text-white/42">Toplam sonuç</div>
            <div className="mt-2 flex items-end gap-2">
              <span className={allPassed ? "font-display text-4xl text-emerald-300" : "font-display text-4xl text-red-300"}>
                {passedCount}
              </span>
              <span className="pb-1 text-sm text-white/50">/ {checks.length} onay</span>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
              <div
                className={allPassed ? "h-full bg-emerald-300" : "h-full bg-amber-300"}
                style={{ width: `${cycleProgress}%` }}
              />
            </div>
            <p className="mt-2 text-[11px] leading-5 text-white/48">
              Döngü bittiğinde başa sarar; aktif adım her 6 saniyede bir kendi veri grubunu yeniden okur.
            </p>
          </div>
        </div>

        <ol className="grid gap-2 lg:grid-cols-2">
          {checks.map((check, index) => (
            <CheckRow
              key={check.id}
              check={check}
              index={index}
              active={index === activeIndex}
            />
          ))}
        </ol>

        <div className="rounded-lg border border-white/10 bg-white/[0.025] px-3 py-2 text-[11px] leading-5 text-white/48">
          Bu panel emir üretmez ve backend kararını değiştirmez. Sadece mevcut dashboard verilerini aynı sırayla okuyup manuel işlem kontrolü için tek ekranda onay/X durumuna indirger.
        </div>
      </div>
    </PanelFrame>
  );
}
