"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { HoloHeadScene } from "@/components/cockpit/HoloHeadScene";
import {
  useAgentMatrix,
  useAgentQuorumMatrix,
  useAssetRegistry,
  useCockpitBrief,
  useConflictGateStatus,
  useConflictGateValidation,
  useDashboardState,
  useDataSnapshot,
  useDecisionMatrix,
  useMarketSessionsTradeUniverse,
  usePaperTradingState,
  useRegimeReport,
  useRiskHalts,
  useSystemHealth,
  useTradeTickets,
} from "@/lib/queries/hooks";
import { selectAgentBrief } from "@/lib/selectors/cockpit";
import { selectHaltActive } from "@/lib/selectors/halts";
import type { TradeTicket } from "@/types/generated/api";

type CheckItem = {
  id: string;
  title: string;
  source: string;
  passed: boolean;
  detail: string;
  metric?: string;
};

const CYCLE_MS = 30_000;
const CHECK_COUNT = 10;
const STEP_MS = CYCLE_MS / CHECK_COUNT;

function formatTime(ms: number) {
  const seconds = Math.max(0, Math.ceil(ms / 1000));
  return `${seconds}s`;
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
  const regime = useRegimeReport();
  const paper = usePaperTradingState();
  const conflictGateStatus = useConflictGateStatus();
  const conflictGateValidation = useConflictGateValidation();
  const assetRegistry = useAssetRegistry();
  const sessionUniverse = useMarketSessionsTradeUniverse();
  const agentQuorum = useAgentQuorumMatrix();

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
      () => Promise.all([conflictGateStatus.refetch(), conflictGateValidation.refetch()]),
      () => Promise.all([regime.refetch(), matrix.refetch()]),
      () => Promise.all([matrix.refetch(), cockpit.refetch(), assetRegistry.refetch()]),
      () => sessionUniverse.refetch(),
      () => agentQuorum.refetch(),
      () => paper.refetch(),
      () => tickets.refetch(),
    ],
    [
      agentQuorum,
      assetRegistry,
      conflictGateStatus,
      conflictGateValidation,
      cockpit,
      dashboard,
      halts,
      matrix,
      paper,
      regime,
      sessionUniverse,
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

  const checks = useMemo<CheckItem[]>(() => {
    const dqs = snapshot.data?.dqs;
    const providers = Object.entries(snapshot.data?.provider_status ?? {});
    const downProviders = providers.filter(([, provider]) => provider.status === "down").map(([name]) => name);
    const degradedProviders = providers.filter(([, provider]) => provider.status === "degraded").map(([name]) => name);
    const staleWorkers = system.data?.stale_workers ?? [];
    const haltActive = selectHaltActive(halts.data) || Boolean(system.data?.risk_halt_status?.active);
    const riskGate = dashboard.data?.risk_gate;
    const eventRestrictive = Boolean(regime.data?.event_risk?.restrictive || matrix.data?.event_risk?.restrictive);
    const structureWarnings =
      (matrix.data?.derivatives?.length ?? 0) +
      (matrix.data?.volatility?.length ?? 0) +
      (matrix.data?.options?.length ?? 0) +
      (matrix.data?.catalysts?.length ?? 0);
    const gateModes = conflictGateStatus.data?.profile_modes ?? {};
    const restrictedGateProfiles = Object.entries(gateModes).filter(([, mode]) => mode !== "OFF");
    const validationReport = conflictGateValidation.data;
    const validationProfiles = validationReport
      ? Object.entries(validationReport).filter(
          ([profile, value]) =>
            profile !== "_unmatched_no_shadow_data" &&
            value !== null &&
            typeof value === "object",
        )
      : [];
    const unmatchedShadowRows =
      typeof validationReport?._unmatched_no_shadow_data === "number"
        ? validationReport._unmatched_no_shadow_data
        : 0;
    const conflictGateEnabled = Boolean(conflictGateStatus.data?.enabled);
    const conflictGatePassed =
      Boolean(conflictGateStatus.data) &&
      (!conflictGateEnabled || restrictedGateProfiles.length === 0 || validationProfiles.length > 0);

    // #6 — tüm trade evreninde (statik + custom asset) actionable sinyal sayısı.
    const tradeUniverse = assetRegistry.data?.trade ?? [];
    const matrixCells = matrix.data?.cells ?? [];
    const actionableSymbols = new Set(
      matrixCells
        .filter((cell) => cell.actionable && (cell.action === "open_long" || cell.action === "open_short"))
        .map((cell) => cell.symbol),
    );
    const matrixUsable = Boolean(matrix.data) && matrix.data?.suspended !== true && matrix.data?.dqs_status !== "BLOCKED";
    const universeCount = tradeUniverse.length || new Set(matrixCells.map((c) => c.symbol)).size;

    // #7 — işlem evrenindeki her asset için piyasa/session durumu (tek çağrı).
    const sessionAssets = sessionUniverse.data?.assets ?? [];
    const sessionTradeable = sessionAssets.filter((a) => a.action !== "block");
    const sessionTotal = sessionAssets.length;

    // #8 — agent persona quorum'u, BTCUSD'ye sabit DEĞİL: her actionable sembol için.
    // Backend tüm trade evreni için hesaplıyor; burada actionable olmayan
    // semboller (henüz hiç sinyal yokken quorum gürültüsü) elenir.
    const quorumRows = (agentQuorum.data?.symbols ?? []).filter((row) =>
      actionableSymbols.has(row.symbol),
    );
    const alignedQuorumRows = quorumRows.filter(
      (row) => row.quorum_reached && row.lead_direction !== "neutral" && row.lead_direction !== null,
    );

    // #9 — portföy sağlığı: state anomaly + duplicate + toplam exposure (sistem-geneli, ticket-bağımsız).
    const duplicateWarnings = paper.data?.duplicate_warning?.length ?? 0;
    const positionAlerts = paper.data?.position_rechecks?.filter(
      (row) => row.verdict === "REDUCE" || row.verdict === "EXIT_RECOMMEND",
    ).length ?? 0;
    const newEntriesDisabled = paper.data?.new_entries_disabled === true;
    const anomalyDetected = paper.data?.state_anomaly?.detected === true;
    const exposureUsd = paper.data?.total_exposure_usd ?? 0;
    const equityUsd = paper.data?.equity_usd ?? 0;
    const exposurePct = equityUsd > 0 ? (exposureUsd / equityUsd) * 100 : 0;
    const portfolioPassed = Boolean(paper.data) && !anomalyDetected && duplicateWarnings === 0;

    // #10 — aktif TÜM ticket'lar (tek ticket değil) broker-hazırlığı.
    const activeTickets = tickets.data?.tickets.filter((t) => t.status === "active") ?? [];
    const now = Date.now();
    const readyTickets = activeTickets.filter((t) => {
      const expired = t.expires_at ? Date.parse(t.expires_at) <= now : true;
      const safetyErrors = t.display?.safety_lines?.filter((l) => l.level === "error").length ?? 0;
      return (
        !expired &&
        safetyErrors === 0 &&
        !newEntriesDisabled &&
        (t.summary?.rr_ratio ?? 0) >= 1.5 &&
        (t.summary?.confidence_calibrated ?? 0) >= 0.5
      );
    });

    return [
      {
        id: "data_quality",
        title: "Veri güvenilir mi?",
        source: "DataQuality / Provider / Snapshot",
        passed:
          Boolean(snapshot.data && system.data) &&
          dqs?.status !== "BLOCKED" &&
          (dqs?.score ?? 0) >= 70 &&
          downProviders.length === 0,
        metric: dqs ? `DQS ${Math.round(dqs.score)} · ${dqs.status}` : "DQS yok",
        detail:
          downProviders.length > 0
            ? `Veri sağlayıcı kapalı: ${downProviders.join(", ")}`
            : degradedProviders.length > 0
              ? `Zayıf sağlayıcı var ama veri tamamen kesilmedi: ${degradedProviders.join(", ")}`
              : "Veri akışı açık; DQS ve sağlayıcılar okunabilir.",
      },
      {
        id: "system_safety",
        title: "Sistem güvenli modda mı?",
        source: "SystemHealth / RiskHalts",
        passed:
          Boolean(system.data) &&
          system.data?.paper_safe === true &&
          system.data?.no_execution === true &&
          staleWorkers.length === 0 &&
          !haltActive,
        metric: `${system.data?.paper_safe ? "PAPER_SAFE" : "paper?"} · ${system.data?.no_execution ? "NO_EXECUTION" : "exec?"}`,
        detail: haltActive
          ? "Risk halt aktif; yeni işlem kapısı kapalı."
          : staleWorkers.length
            ? `Geciken worker var: ${staleWorkers.join(", ")}`
            : "Simülasyon güvenliği açık; worker ve halt engeli yok.",
      },
      {
        id: "risk_gate",
        title: "Risk yeni girişe izin veriyor mu?",
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
              ? brief?.main_blocker?.detail ?? brief?.main_blocker?.label ?? "Ana engel temiz değil."
              : "Risk kapısı yeni giriş için açık görünüyor.",
      },
      {
        id: "conflict_gate",
        title: "Conflict Gate hazır mı?",
        source: "Conflict Gate / Validation",
        passed: conflictGatePassed,
        metric: conflictGateEnabled
          ? `${restrictedGateProfiles.length} profil · ${validationProfiles.length} rapor`
          : "kapalı · fail-open",
        detail: !conflictGateStatus.data
          ? "Conflict Gate config okunamıyor."
          : !conflictGateEnabled
            ? "Conflict Gate kapalı; eski karar yolu davranışı değişmiyor."
            : restrictedGateProfiles.length === 0
              ? "Gate aktif ama tüm profiller OFF; eski karar yolu açık."
              : validationProfiles.length === 0
                ? `Gate aktif (${restrictedGateProfiles.map(([profile, mode]) => `${profile}:${mode}`).join(", ")}) ama retrospektif doğrulama raporu boş.`
                : `Gate aktif; ${validationProfiles.length} profil doğrulandı, eşleşmeyen shadow kaydı ${unmatchedShadowRows}.`,
      },
      {
        id: "market_structure",
        title: "Haber / volatilite engeli var mı?",
        source: "Derivatives / Volatility / Options / Catalyst",
        passed: Boolean(regime.data && matrix.data) && !eventRestrictive && structureWarnings === 0,
        metric: `uyarı ${structureWarnings} · event ${eventRestrictive ? "restrictive" : "clear"}`,
        detail: eventRestrictive
          ? regime.data?.event_risk?.reason ?? matrix.data?.event_risk?.reason ?? "Restrictive event risk var."
          : structureWarnings > 0
            ? "Piyasa yapısı, volatilite veya haber katmanında uyarı var."
            : "Haber, volatilite ve piyasa yapısında sert engel görünmüyor.",
      },
      {
        id: "actionable_signals",
        title: "Kaç assette actionable sinyal var?",
        source: "DecisionMatrix / AssetRegistry (tüm trade evreni)",
        passed: matrixUsable && actionableSymbols.size > 0,
        metric: `${actionableSymbols.size}/${universeCount} asset actionable`,
        detail: !matrixUsable
          ? "Decision matrix suspended veya DQS BLOCKED; hiçbir asset için yeni işlem yok."
          : actionableSymbols.size > 0
            ? `Actionable: ${Array.from(actionableSymbols).join(", ")}.`
            : "İşlem evrenindeki hiçbir asset'te şu an actionable hücre yok.",
      },
      {
        id: "session_status",
        title: "Piyasa/session durumu nedir?",
        source: "MarketSessions / trade-universe",
        passed: Boolean(sessionUniverse.data) && sessionTradeable.length > 0,
        metric: `${sessionTradeable.length}/${sessionTotal || "?"} piyasa işleme açık/izinli`,
        detail: !sessionUniverse.data
          ? "Session durumu okunamıyor."
          : sessionTradeable.length === 0
            ? "İşlem evrenindeki tüm asset'lerin session'ı kapalı (block)."
            : `Kapalı: ${sessionAssets.filter((a) => a.action === "block").map((a) => a.asset_code).join(", ") || "yok"}.`,
      },
      {
        id: "agent_consensus",
        title: "Agentlar aynı yönde mi?",
        source: "AgentVotes (her actionable asset için ayrı, BTCUSD'ye sabit değil)",
        passed: Boolean(agentQuorum.data) && alignedQuorumRows.length > 0,
        metric: `${alignedQuorumRows.length}/${quorumRows.length} assette agent quorum'u yönlü`,
        detail: !agentQuorum.data
          ? "Agent quorum matrisi okunamıyor."
          : alignedQuorumRows.length > 0
            ? `Yönlü quorum: ${alignedQuorumRows.map((r) => `${r.symbol}:${r.lead_direction}`).join(", ")}.`
            : "Hiçbir assette agent çoğunluğu yönlü bir konsensüse ulaşmadı (hepsi neutral/çelişkili).",
      },
      {
        id: "portfolio_health",
        title: "Portföy/pozisyon sağlığı nedir?",
        source: "PaperState / StateAnomaly (tüm açık pozisyonlar, tek ticket değil)",
        passed: portfolioPassed,
        metric: `exposure $${Math.round(exposureUsd).toLocaleString("en-US")} (%${exposurePct.toFixed(1)} equity)`,
        detail: anomalyDetected
          ? `State anomaly: ${paper.data?.state_anomaly?.reasons?.join(", ") || "tespit edildi"}.`
          : duplicateWarnings > 0
            ? "Aynı (symbol, timeframe) için duplicate açık pozisyon var."
            : positionAlerts > 0
              ? `${positionAlerts} açık pozisyon REDUCE/EXIT_RECOMMEND uyarısı veriyor (bilgi amaçlı, bloklamaz).`
              : "Portföy muhasebesi tutarlı, duplicate yok.",
      },
      {
        id: "ticket_integrity",
        title: "Tüm aktif ticket'lar broker-hazır mı?",
        source: "TradeTicket (tüm aktif ticket'lar, tek ticket değil)",
        passed: activeTickets.length > 0 && readyTickets.length === activeTickets.length,
        metric: activeTickets.length
          ? `${readyTickets.length}/${activeTickets.length} ticket hazır`
          : "ticket yok",
        detail:
          activeTickets.length === 0
            ? "Entry, stop, hedef ve büyüklük içeren aktif ticket yok."
            : newEntriesDisabled
              ? "Paper state yeni girişleri kapatmış; hiçbir ticket broker'a giremez."
              : readyTickets.length === activeTickets.length
                ? "Tüm aktif ticket'larda entry, stop, hedef, R:R ve güvenlik kontrolleri hazır."
                : `${activeTickets.length - readyTickets.length} ticket süresi dolmuş, güvenlik hatası veya yetersiz R:R/güven nedeniyle hazır değil.`,
      },
    ];
  }, [
    agentQuorum.data,
    assetRegistry.data,
    brief,
    conflictGateStatus.data,
    conflictGateValidation.data,
    cockpit.data,
    dashboard.data,
    halts.data,
    matrix.data,
    paper.data,
    regime.data,
    sessionUniverse.data,
    snapshot.data,
    system.data,
    tickets.data,
  ]);

  const passedCount = checks.filter((check) => check.passed).length;
  const allPassed = passedCount === checks.length;
  const cycleRemaining = CYCLE_MS - cycleElapsed;

  return (
    <>
    <div className="hidden h-full min-[769px]:block">
    <PanelFrame id="execution_readiness" className="readiness-panel rc-panel h-full">
      <div className="rc-stage">
        {/* sol üst — agent modu */}
        <div className="rc-mode">
          <span className="rc-mode-top">CHECK LIST</span>
          <span className="rc-mode-mid">READ ONLY</span>
          <strong className={`rc-mode-state ${allPassed ? "rc-mode-state-ok" : ""}`}>
            {allPassed ? "READY" : "CALIBRATING"}
          </strong>
        </div>

        {/* sağ üst — döngü skoru + sayaç */}
        <div className="rc-cyclehud">
          <div className="rc-cyclehud-score">
            <span className="rc-cyclehud-pass">{passedCount}</span>
            <span className="rc-cyclehud-sep">/</span>
            <span className="rc-cyclehud-total">{checks.length}</span>
          </div>
          <div className="rc-cyclehud-label">hazır · {formatTime(cycleRemaining)}</div>
        </div>

        {/* merkez — holografik agent (3D point-cloud büst) */}
        <div className="rc-figure">
          <HoloHeadScene tone={allPassed ? "ok" : "idle"} />
        </div>

        {/* sol orbit — 10 kontrol node'u */}
        <ul className="rc-orbit">
          {checks.map((check, i) => {
            const state = i === activeIndex
              ? "scanning"
              : i < activeIndex
                ? (check.passed ? "ok" : "bad")
                : "pending";
            const stateLabel =
              state === "scanning"
                ? `${check.passed ? "HAZIR" : "ENGEL VAR"} · kontrol`
                : state === "ok"
                  ? "HAZIR"
                  : state === "bad"
                    ? "ENGEL VAR"
                    : "sırada";
            const reason =
              state === "pending"
                ? "Henüz sıraya gelmedi."
                : check.passed
                  ? check.metric ?? check.detail
                  : check.detail;
            const t = checks.length > 1 ? i / (checks.length - 1) : 0.5;
            const bulge = Math.sin(t * Math.PI) * 7;
            return (
              <li
                key={check.id}
                className={`rc-node rc-node-${state}`}
                style={
                  {
                    "--node-top": `${5 + t * 84}%`,
                    "--node-x": `${bulge}%`,
                  } as CSSProperties
                }
              >
                <span className="rc-node-num">{String(i + 1).padStart(2, "0")}</span>
                <span className="rc-node-mark" aria-hidden="true" />
                <span className="rc-node-body">
                  <span className="rc-node-title">{check.title}</span>
                  <span className="rc-node-state">{stateLabel}</span>
                  <span className="rc-node-reason">{reason}</span>
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      {/* alt — trade ticket şeridi */}
      <TradeTicketStrip ticket={activeTicket} />
    </PanelFrame>
    </div>
    <section className="mobile-check-direct min-[769px]:hidden">
      <div className="mobile-check-head">
        <div>
          <p className="mobile-kicker">CHECK LIST</p>
          <p className="mobile-subline">READ ONLY</p>
          <strong className={allPassed ? "text-emerald-300" : "text-amber-300"}>
            {allPassed ? "READY" : "CALIBRATING"}
          </strong>
        </div>
        <div className="mobile-check-score">
          <span>{passedCount}</span>
          <em>/ {checks.length}</em>
          <small>{formatTime(cycleRemaining)}</small>
        </div>
      </div>
      <div className="mobile-check-list mobile-check-list--all">
        {checks.map((check, index) => (
          <MobileCheckRow
            key={check.id}
            check={check}
            index={index}
            active={index === activeIndex}
          />
        ))}
      </div>
    </section>
    </>
  );
}

function MobileCheckRow({
  check,
  index,
  active,
}: {
  check: CheckItem;
  index: number;
  active: boolean;
}) {
  return (
    <div className={`mobile-check-row ${active ? "is-active" : ""} ${check.passed ? "is-ok" : "is-bad"}`}>
      <span className="mobile-check-row__num">{String(index + 1).padStart(2, "0")}</span>
      <span className="mobile-check-row__mark">{check.passed ? "✓" : "X"}</span>
      <div className="min-w-0">
        <strong>{check.title}</strong>
        <p>{check.metric ?? check.detail}</p>
      </div>
      <em>{check.passed ? "HAZIR" : "ENGEL"}</em>
    </div>
  );
}

function TradeTicketStrip({ ticket }: { ticket?: TradeTicket }) {
  const fields: [string, string][] = ticket
    ? [
        ["YÖN", ticket.side.toUpperCase()],
        ["GİRİŞ", ticket.summary.entry_price.toLocaleString("en-US")],
        ["ZARAR EŞİK", ticket.summary.stop_loss.toLocaleString("en-US")],
        ["KÂR HEDEFİ", ticket.summary.take_profit.toLocaleString("en-US")],
        ["BÜYÜKLÜK", `$${Math.round(ticket.summary.size_usd).toLocaleString("en-US")}`],
        ["RRR", `1:${ticket.summary.rr_ratio.toFixed(2)}`],
        ["GEÇERLİLİK", ticket.display.expiry_text],
      ]
    : [
        ["YÖN", "---"],
        ["GİRİŞ", "---"],
        ["ZARAR EŞİK", "---"],
        ["KÂR HEDEFİ", "---"],
        ["BÜYÜKLÜK", "---"],
        ["RRR", "---"],
        ["GEÇERLİLİK", "---"],
      ];

  return (
    <aside className="rc-ticket">
      <div className="rc-ticket-glow" aria-hidden="true" />
      <div className="rc-ticket-head">
        <div>
          <div className="rc-ticket-title">Trade Ticket</div>
          <div className="rc-ticket-sub">intraday / manuel girmeden tek tıkla kart</div>
        </div>
        <span className={ticket ? "rc-ticket-badge rc-ticket-badge-live" : "rc-ticket-badge rc-ticket-badge-empty"}>
          {ticket ? "HAZIR" : "YOK"}
        </span>
      </div>

      <div className="rc-ticket-grid">
        {fields.map(([label, value]) => (
          <div key={label} className="rc-ticket-field">
            <span className="rc-ticket-label">{label}</span>
            <span className="rc-ticket-value">{value}</span>
          </div>
        ))}
        <div className="rc-ticket-spark" aria-hidden="true">
          <span /><span /><span /><span /><span /><span /><span />
        </div>
      </div>

      <div className="rc-ticket-foot">
        <span className="rc-ticket-foot-label">DURUM</span>
        <span className={ticket ? "rc-ticket-foot-live" : "rc-ticket-foot-empty"}>
          {ticket ? `${ticket.symbol} ${ticket.side.toUpperCase()}` : "TICKET YOK"}
        </span>
      </div>
    </aside>
  );
}
