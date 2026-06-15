# PHASE 3 — Dashboard Transplant Map

> Living artifact. **Wave 0 (guardrails) + first Wave 1 slice are DONE.**
> Goal: **codex dashboard visual parity** with the **clean web architecture preserved**.

## Progress (current reality)

- ✅ **Contract debt cleared — all 6 orphan friendly types resolved** (`KNOWN_UNCONTRACTED` is now empty; `test_friendly_types_map_to_contract` ratchets at zero):
  - **Promoted to named OpenAPI schemas (5):** `OutcomeBucket`, `LearningWorkerRun`, `ClusterPosition`, `AgentBriefCandidate` (parents re-wired to `$ref`; `worker_last_run` nullable via `anyOf`+`type: "null"`), and `TechnicalTf`.
  - **`TechnicalTf` → documented alias of the existing `TechnicalSnapshotTF`** (identical shape; FE-friendly name kept, no field duplication). `DataSnapshot.technicals_by_tf` keeps the canonical `TechnicalSnapshotTF`.
  - **`SnapshotMode` → deleted as dead**, not promoted: it was never referenced; `/data/snapshot` + `/dashboard/state` return the 7-field `ProvenanceMode` stamp. No schema invented for a non-response.
- ✅ **Wave 0 guards added** (`tests/test_architecture_guards.py`): `test_no_manual_fetch_in_panels` + `test_no_frontend_decision_math` (see §6).
- ✅ **First typed dashboard slice done:** `TradingPanel` (codex `PaperTradingTicker` visual language, ViewModel-only). Surfaced `unrealized_pnl_usd` (state + per-position, passthrough); **removed** the prior client-side equity reconstruction; read-only (no order/close/reset UI).
- ⏭️ **Next recommended (Wave 1, R1, existing schemas):** `AIReportPanel` or `DataQualityPanel` (no animation, no new schema). Then the rest of Wave 1, then Wave 2 (remaining orphan-fed panels are already de-orphaned, so they're now plain visual wires), then Wave 3 (animated/3D layers).

## 0. Rules (binding for every row below)

- No manual/untyped `fetch("/api/v1/...")` — data only via the typed `lib/queries/hooks` → `lib/api/client` (generated contract).
- Frontend renders **backend ViewModels only**. No trading / risk / regime / DQS math in React.
- No backend decision logic in the frontend. Panels are presentational over a selector output.
- Promote the 6 orphan friendly types to OpenAPI schemas **as their panels are wired** (contract-first).
- Keep codex visuals, animations, UX where possible; replace any dirty wiring with typed ViewModel wiring.
- **Do not change paper-engine (Phase 2) behavior** unless a bug is found and isolated (separate fix + tests).

## 1. Current-state finding (important)

The clean web app is **already architecturally clean**:

- Every panel pulls data through typed hooks in `apps/web/lib/queries/hooks.ts` → `lib/api/client.ts` (generated `schema.ts`).
- Raw responses become ViewModels in `apps/web/lib/selectors/*`; panels are presentational.
- **No `fetch(`/`axios`/`XMLHttpRequest` exists in `components/` or `lib/selectors/`** (verified). There is **no dirty wiring to remove** on the clean side.
- The "dirty wiring" the rules warn about lives in the **codex** source (`frontend/lib/api.ts`, manual `fetch`). Phase 3 must **not** bring it across.

**Therefore Phase 3 is mainly:**
1. **Visual parity** — port codex's richer visuals/animations/3D-radar layers into the existing typed panels (most rows are *visual-only*, R1).
2. **6 orphan schema promotions** — break nested friendly types out into named OpenAPI schemas as their panels are touched (contract-first, R2).
3. **Guardrails** — ✅ added: a structural `no manual fetch in panels` arch guard and a `no frontend decision-math` guard so the clean wiring can't regress (§6).

There is **no R3 work in Phase 3** (no RiskGate/paper-safety surface is touched). Any R3 would mean a paper-engine change → out of scope.

## 2. Endpoint / ViewModel reference (typed sources panels may use)

| Hook | Endpoint | Primary ViewModel schema(s) |
|---|---|---|
| `useCockpitBrief` | `GET /cockpit/brief` | `CockpitBrief`, `AgentBrief`, `AgentBriefCandidate*`, `DecisionTrace`, `WatchCondition` |
| `useAIReport` | `GET /ai-report/current` | `AIReport`, `PersonaSection`, `LLMMeta` |
| `useDashboardState` | `GET /dashboard/state` | `DashboardState`, `RiskGate`, `HaltMetrics`, `NewsHeadline`, `PaperAuditEvent`, `WatchCondition` |
| `useDecisionMatrix` | `GET /decision/matrix` | `DecisionMatrix`, `TimeframeDecision`, `TimeframeSummary`, `AssetSignal` |
| `usePaperTradingState` | `GET /paper-trading/state` | `PaperTradingState`, `Position`, `Trade`, `PaperLifecycleStatus`, `PaperAuditEvent` |
| `useLearningSummary` | `GET /learning/summary` | `LearningSummary`, `OutcomeBucket*`, `LearningWorkerRun*` |
| `useDataSnapshot` | `GET /data/snapshot` | `DataSnapshot`, `LivePrice`, `OHLCVBar`, `TechnicalSnapshotTF`, `TechnicalTf*`, `SnapshotMode*`, `DqsBreakdown`, `DerivativesSnapshot`, `VolatilitySnapshot`, `OptionsSnapshot`, `Catalyst` |
| `useRebalanceProposal` | `GET /learning/rebalance/proposal` | `RebalanceState`, `WeightDelta`, `RebalanceProposalRecord` |
| `useCalibration` | `GET /learning/calibration` | `CalibrationState`, `CalibrationBin`, `CalibrationParams` |
| `useMistakes` | `GET /learning/mistakes` | `MistakesState`, `MistakeRecord`, `MistakeVerdict` |
| `useRiskCorrelation` | `GET /risk/correlation` | `CorrelationState`, `CorrelationEntry`, `ExposureCluster`, `ClusterPosition*` |
| `useRegimeReport` | `GET /regime-report/current` | `RegimeReport`, `RegimeLayer`, `Catalyst`, `EventRiskView`, `NewsHeadline` |
| `useRiskHalts` | `GET /risk/halts` | `HaltsState`, `HaltEvent`, `HaltMetrics` |
| `useSystemHealth` | `GET /system/health` | `SystemHealth`, `WorkerHealth`, `ModuleHealth`, `ModulePerf`, `ProviderStatus` |
| `useReplayStatus` | `GET /replay/status` | `ReplayStatus` |
| `useChat` | `POST /chat` | `ChatRequest`, `ChatResponse` |
| `useHealth` | `GET /health` | `Health` |

`*` = friendly type that **was** an orphan (no named OpenAPI schema). **All resolved — see §5** (`SnapshotMode` deleted as dead; the rest now have schemas, incl. `TechnicalTf` aliased to `TechnicalSnapshotTF`). The contract layer is complete and the friendly-types ratchet is at zero.

## 3. Component transplant map (codex → clean), by IA group

Columns: **codex source** · **clean target** · **backend endpoint / ViewModel** · **missing schema** · **kind** (visual-only \| +contract) · **risk** · **checks**.
Default checks for every row: `tsc`/`pnpm build` + the new `no-manual-fetch-in-panels` arch guard. Rows marked `+contract` additionally need `make codegen` + `codegen-check` + `test_friendly_types_map_to_contract`.

### 3.1 Command (Agent Command Center)

| codex source | clean target | endpoint / ViewModel | missing schema | kind | risk | checks |
|---|---|---|---|---|---|---|
| `AgentCommandCenter.tsx` | `AgentBriefPanel` | `/cockpit/brief` → `AgentBrief` | `AgentBriefCandidate` | +contract | R2 | codegen, friendly-types guard |
| `AgentInsightBar.tsx` | `AgentBriefPanel` (header bar) | `/cockpit/brief` → `CockpitBrief` | — | visual-only | R1 | tsc |
| `DecisionBanner.tsx` | `DecisionPanel` | `/cockpit/brief` + `/decision/matrix` → `DecisionTrace`/`DecisionMatrix` | — | visual-only | R1 | tsc |
| `AsymmetryCard.tsx` | `DecisionPanel` (sub-card) | `/cockpit/brief` → `AgentBrief` | — | visual-only | R1 | tsc |
| `AIAnalystReport.tsx` | `AIReportPanel` | `/ai-report/current` → `AIReport`, `PersonaSection` | — | visual-only | R1 | tsc |
| `AIChatPanel.tsx` | `ChatPanel` | `POST /chat` → `ChatResponse` | — | visual-only | R2 (mutation; no client-side decisioning) | tsc |

### 3.2 Risk & Execution Freeze

| codex source | clean target | endpoint / ViewModel | missing schema | kind | risk | checks |
|---|---|---|---|---|---|---|
| `RiskGateEvidence.tsx` | `RiskGatePanel` | `/dashboard/state` → `RiskGate` | — | visual-only | R1 | tsc; **no risk math in FE** |
| (drawdown viz) | `DrawdownGuardPanel` | `/risk/halts` → `HaltsState`/`HaltMetrics` | — | visual-only | R1 | tsc |
| `PaperTradingTicker.tsx` | `PaperActionPanel` | `/paper-trading/state` + `/cockpit/brief` → `PaperTradingState` | — | visual-only | R1 | tsc |
| `ConfirmationChecklist.tsx` | `PositionChecksPanel` | `/paper-trading/state` → `Position`/`Trade` | — | visual-only | R1 | tsc |
| `MacroRiskFilterStrip.tsx` | `RiskGatePanel`/regime strip | `/regime-report/current` → `RegimeReport` | — | visual-only | R1 | tsc |

### 3.3 Decision Trace / Candidate Matrix

| codex source | clean target | endpoint / ViewModel | missing schema | kind | risk | checks |
|---|---|---|---|---|---|---|
| `ActionCenter.tsx`, `ActionSignalPanelShell.tsx`, `ActionSignalRaceLayer.tsx`, `ActionSignalErrorBoundary.tsx` | `CommandSignalsPanel` | `/cockpit/brief` + `/regime-report` → `AgentBriefCandidate`/`AssetSignal` | `AgentBriefCandidate` | +contract | R2 (animated layer) | codegen, friendly-types guard |
| `CommandSignalCardsLayer.tsx`, `CommandSignalsPanelShell.tsx`, `CommandSignalsErrorBoundary.tsx` | `CommandSignalsPanel` | `/cockpit/brief` → `AgentBrief` | (shared w/ above) | visual-only | R2 (animation) | tsc |
| `TechnicalPanel.tsx` | `TimeframeMatrixPanel` / `PatternsPanel` | `/decision/matrix` + `/data/snapshot` → `TimeframeDecision`/`TechnicalSnapshotTF` | `TechnicalTf` | +contract | R2 | codegen, friendly-types guard |
| `DecisionBanner` (trace mode) | `DecisionTracePanel` | `/cockpit/brief` → `DecisionTrace` | — | visual-only | R1 | tsc |
| `RiskGateEvidence` (evidence chain) | `AgentVotesPanel` | `/ai-report` + `/dashboard/state` → `AgentVote` | — | visual-only | R1 | tsc |

### 3.4 Watch & Chat

| codex source | clean target | endpoint / ViewModel | missing schema | kind | risk | checks |
|---|---|---|---|---|---|---|
| `ConfirmationStrip.tsx` | `WatchConditionsPanel` | `/cockpit/brief` → `WatchCondition` | — | visual-only | R1 | tsc |
| `AIChatPanel.tsx` (chat surface) | `ChatPanel` | `POST /chat` → `ChatResponse` | — | visual-only | R2 | tsc |

### 3.5 Data Quality & Providers

| codex source | clean target | endpoint / ViewModel | missing schema | kind | risk | checks |
|---|---|---|---|---|---|---|
| `AssetGrid.tsx`, `MiniChart.tsx` | `MarketDataPanel` (+ `charts/SparkLine`) | `/data/snapshot` → `LivePrice`/`OHLCVBar`/`TechnicalTf` | `TechnicalTf` | +contract | R2 | codegen, friendly-types guard |
| (DQS viz) | `DataQualityPanel` | `/data/snapshot` → `DqsBreakdown` | — | visual-only | R1 | tsc; **no DQS math in FE** |
| (provider viz) | `ProviderStatusPanel` | `/data/snapshot` + `/system/health` → `ProviderStatus` | — | visual-only | R1 | tsc |
| (snapshot/provenance viz) | `SnapshotPanel` | `/data/snapshot` → `SnapshotMeta`/`ProvenanceMode` | ~~`SnapshotMode`~~ (deleted as dead — use `ProvenanceMode`) | visual-only | R1 | tsc |
| (audit viz) | `PanelAuditPanel` | `/dashboard/state` → `PaperAuditEvent` | — | visual-only | R1 | tsc |

### 3.6 Market Structure

| codex source | clean target | endpoint / ViewModel | missing schema | kind | risk | checks |
|---|---|---|---|---|---|---|
| `CapitalFlowWidget.tsx`, `CapitalFlowAnimatedLayer.tsx`, `CapitalRotationPanelShell.tsx`, `CapitalFlowErrorBoundary.tsx` | `CapitalRotationPanel` | `/regime-report/current` → `RegimeReport`/`RegimeLayer` | — | visual-only | R2 (animation) | tsc |
| (correlation/exposure viz) | `CorrelationPanel` | `/risk/correlation` → `CorrelationState`/`ExposureCluster` | `ClusterPosition` | +contract | R2 | codegen, friendly-types guard |
| (derivatives viz) | `CryptoDerivativesPanel` | `/data/snapshot` → `DerivativesSnapshot`/`DerivativesSummary` | — | visual-only | R1 | tsc |
| (vol-regime viz) | `VolatilityPanel` | `/data/snapshot` → `VolatilitySnapshot`/`VolatilitySummary` | — | visual-only | R1 | tsc |
| (options IV/skew viz) | `OptionsVolPanel` | `/data/snapshot` → `OptionsSnapshot`/`OptionsSummary` | — | visual-only | R1 | tsc |
| `TechnicalPanel.tsx` (patterns) | `PatternsPanel` | `/data/snapshot` → `TechnicalSnapshotTF` | (TechnicalTf shared) | visual-only | R1 | tsc |

### 3.7 Macro / Catalyst

| codex source | clean target | endpoint / ViewModel | missing schema | kind | risk | checks |
|---|---|---|---|---|---|---|
| `CatalystStrip.tsx`, `CatalystSidebar.tsx` | `CatalystImpactPanel` | `/data/snapshot` → `Catalyst`/`CatalystImpact`/`CatalystSummary` | — | visual-only | R1 | tsc |
| `EventCalendar3DLayer.tsx`, `EventCalendarPanelShell.tsx`, `EventCalendarErrorBoundary.tsx` | `EventCalendarPanel` | `/regime-report/current` → `EventRiskView`/`EventRiskTrigger` | — | visual-only | R2 (3D layer) | tsc |
| `NewsPanel.tsx`, `NewsPanelShell.tsx`, `NewsMapRadarLayer.tsx`, `BreakingNewsRadarLayer.tsx`, `BreakingNewsPanelShell.tsx`, `BreakingNewsErrorBoundary.tsx`, `WarBreakingAlert.tsx` | `NewsPanel` | `/regime-report/current` → `NewsHeadline` | — | visual-only | R2 (radar/alert anim) | tsc |
| `ScenarioPanel.tsx`, `ScenarioPanelShell.tsx`, `ScenarioBattleLayer.tsx`, `ScenarioBattleErrorBoundary.tsx` | `ScenarioPanel` | `/regime-report/current` → `RegimeReport` (scenario view) | verify (may need a `ScenarioView` schema if codex adds fields) | visual-only / maybe +contract | R2 | tsc (+ codegen if new fields) |
| `MacroPanel.tsx` | (folds into `RiskGatePanel`/regime strip) | `/regime-report/current` → `RegimeLayer` | — | visual-only | R1 | tsc |

### 3.8 Paper & Learning

| codex source | clean target | endpoint / ViewModel | missing schema | kind | risk | checks |
|---|---|---|---|---|---|---|
| `PaperTradingTicker.tsx` | `TradingPanel` ✅ **DONE** | `/paper-trading/state` → `PaperTradingState`/`Trade` | — | visual-only | R1 | tsc; **read-only, no order UI** |
| `LearningPanel.tsx` | `LearningPanel` | `/learning/summary` → `LearningSummary` | `OutcomeBucket`, `LearningWorkerRun` | +contract | R2 | codegen, friendly-types guard |
| (calibration viz) | `CalibrationPanel` (+ `charts/CalibrationGrid`) | `/learning/calibration` → `CalibrationState` | — | visual-only | R1 | tsc |
| (mistake viz) | `MistakeMemoryPanel` | `/learning/mistakes` → `MistakesState`/`MistakeRecord` | — | visual-only | R1 | tsc |
| (weight viz) | `WeightProposalPanel`, `WeightHistoryPanel` | `/learning/rebalance/proposal` → `RebalanceState`/`WeightDelta` | — | visual-only | R1 | tsc; **proposal display only** |

### 3.9 Ops / System

| codex source | clean target | endpoint / ViewModel | missing schema | kind | risk | checks |
|---|---|---|---|---|---|---|
| `SystemHealthBar.tsx`, `SystemHealthPanel.tsx` | `SystemHealthBar` | `/system/health` + `/health` → `SystemHealth`/`WorkerHealth` | — | visual-only | R1 | tsc |
| (replay viz) | `ReplayStatusPanel` | `/replay/status` → `ReplayStatus` | — | visual-only | R1 | tsc (replay reserved; no fake replay) |

## 4. Shell / shared / cross-cutting components

| codex source | clean target | kind | risk | notes |
|---|---|---|---|---|
| `Header.tsx`, `Footer.tsx` | `app/layout.tsx` + `components/shell/*` | visual-only | R1 | chrome only |
| `AutoRefresh.tsx`, `RefreshButton.tsx` | `hooks/useRealtimeRefresh.ts` (exists) | visual-only | R1 | reuse clean hook; do not add polling fetch in components |
| `*ErrorBoundary.tsx` (per-panel, codex) | `components/shell/ErrorBoundary.tsx` (exists) | visual-only | R1 | one shared boundary, not per-panel duplicates |
| `*PanelShell.tsx` (codex) | `components/shell/PanelFrame.tsx` + `PanelHeader.tsx` (exist) | visual-only | R1 | map codex shell chrome onto clean frame |
| `HeroScene` / animated background | `components/visuals/HeroScene.tsx` (exists, 41 lines) | visual-only | R2 | extend to codex hero fidelity |

### Codex visual layers to preserve (heaviest visual effort — port as ViewModel-fed sub-components)

`ScenarioBattleLayer`, `EventCalendar3DLayer`, `CapitalFlowAnimatedLayer`, `NewsMapRadarLayer`, `BreakingNewsRadarLayer`, `ActionSignalRaceLayer`, `CommandSignalCardsLayer`.
Each is a pure-presentation animation/3D layer. **Rule:** the layer receives a ViewModel prop; it must contain **no fetch and no math** beyond layout/animation. Risk R2 (rendering/perf), never R3.

## 5. Orphan schema promotions (contract-first, do as each panel is wired)

**✅ RESOLVED — all 6 done** (commit `chore(web): promote dashboard orphan types to openapi schemas`). `KNOWN_UNCONTRACTED` is now empty; the friendly-types guard ratchets at zero. Shapes were verified against the backend serializers (`outcomes.py`, `run_store.py`, `correlation.py`, `cockpit.py`, `data/types.py`) — no fields invented.

| orphan type | lives in (parent ViewModel) | endpoint | resolution |
|---|---|---|---|
| `AgentBriefCandidate` | `AgentBrief.top_candidates` | `/cockpit/brief` | ✅ named schema; `top_candidates.items` → `$ref` |
| `ClusterPosition` | `ExposureCluster.positions` | `/risk/correlation` | ✅ named schema; `positions.items` → `$ref` |
| `LearningWorkerRun` | `LearningSummary.worker_last_run` | `/learning/summary` | ✅ named schema; `worker_last_run` → nullable `$ref` (`anyOf` + `type: "null"`) |
| `OutcomeBucket` | `LearningSummary.by_{timeframe,symbol,regime,dominant_module,close_reason}` | `/learning/summary` | ✅ named schema; `by_*.additionalProperties` → `$ref` |
| `SnapshotMode` | (none — was never referenced) | `/data/snapshot` | ✅ **deleted as dead**; `/data/snapshot` + `/dashboard/state` use the 7-field `ProvenanceMode`. No schema invented. |
| `TechnicalTf` | `DataSnapshot.technicals_by_tf` | `/data/snapshot` | ✅ **alias** of existing `TechnicalSnapshotTF` (`allOf` ref) — identical shape, FE-friendly name documented in contract |

**Per-promotion procedure (contract-first) — the record of how each was done:**
1. Add the named schema to `contracts/openapi.yaml` `components.schemas` (matching the backend response shape — verify against the router/ViewModel, do **not** invent fields).
2. `make codegen` → regenerate `apps/web/types/generated/schema.ts`; `make codegen-check` clean.
3. Update `apps/web/types/generated/api.ts` so the friendly type references / re-exports the generated schema (kill manual drift).
4. Remove the type from `KNOWN_UNCONTRACTED` in `tests/test_architecture_guards.py`.
5. Verify `test_friendly_types_map_to_contract`, `test_openapi_schema_ts_in_sync`, `tsc`/`pnpm build`.

Backend note: these are **presentation ViewModel fields only** (no new decision logic). If a field the panel needs is not yet emitted by the router, add it to the **ViewModel/serializer** (presentation), never as new decision math.

## 6. Cross-cutting checks & new guards

Run on every Phase 3 PR / wave:
- `cd apps/web && pnpm build` (Next build + `tsc` types valid).
- `make codegen && make codegen-check` (contract ↔ generated TS in sync).
- `make lint` + `make test` (backend untouched → stays green; **paper-engine behavior unchanged**).
- `tests/test_architecture_guards.py` — all existing guards green; `KNOWN_UNCONTRACTED` shrinks as orphans are promoted (ratchet).

✅ **Wave-0 guards added** in `tests/test_architecture_guards.py` (both ignore comments + string/template literals, line-count preserving, so prose/class-names that *mention* fetch/risk/PnL don't false-positive):
- **`test_no_manual_fetch_in_panels`** — no `fetch(`/`axios`/`XMLHttpRequest`/`EventSource`/`new WebSocket` under `apps/web/components/**` (data only via `lib/queries/hooks` → typed `lib/api` client). react-query `refetch` is allowed (`\bfetch\(` doesn't match `refetch(`).
- **`test_no_frontend_decision_math`** — `components/**` + `lib/selectors/**` must not **reconstruct** trading/risk/regime/DQS/sizing/PnL decisions. Keys on the **computational fingerprint**: an arithmetic operator (`+ - * /`) on a decision field — PnL/equity/size reconstruction (`equity_usd`/`*_pnl_usd`/`size_usd`/…), sizing math (`size *=`, `size_factor * …`), or DQS-subfield score reconstruction (`freshness`/`completeness`/`drift`/…). **Deliberately narrow:** reading a field, formatting it, and *thresholding a finished backend value for a colour band* (e.g. `score >= 60`, `dqs.score >= 75`) is presentation and stays allowed — verified against the existing color-band panels to avoid false positives. Negative-tested: both guards fail on a planted `fetch(` + `equity_usd - realized_pnl_usd`.

## 7. Risk legend & recommended sequencing

`R1` pure visual, schema already exists · `R2` visual + schema promotion **or** heavy animation/3D · `R3` would touch RiskGate/paper safety → **not present in Phase 3** (any R3 = out of scope).

**Wave 0 — guardrails:** ✅ both arch guards added (§6). ⏭️ still to do: port shared shell (`Header/Footer/PanelShell/ErrorBoundary/AutoRefresh`) onto the existing clean shell.
**Wave 1 — R1 visual-only panels with existing schemas:** ✅ **Trading done** (first slice). Next: **AIReport** or **DataQuality** (no animation, no schema). Remaining: ProviderStatus, Derivatives, Volatility, OptionsVol, Patterns, Calibration, MistakeMemory, Weights, SystemHealth, Replay, PanelAudit, RiskGate, DrawdownGuard, PositionChecks, WatchConditions, Catalyst, Macro. (Bulk of the visual parity, lowest risk.)
**Wave 2 — the (formerly) orphan-fed panels:** AgentBrief, CommandSignals, MarketData, Snapshot, Correlation, Learning. **The contract work is already done** (all 6 orphans resolved in §5), so these are now plain R1/R2 visual wires — no schema/codegen step remains, just port the visuals over the existing typed ViewModels.
**Wave 3 — heavy animated/3D layers:** Scenario battle, EventCalendar 3D, CapitalFlow animation, News radar/war alert, ActionSignal race, CommandSignal cards. Visual-fidelity + perf focus.

## 8. Out of scope (explicit)

- No paper-engine / RiskGate / sizing / lifecycle behavior changes (Phase 2 is frozen; bug → separate isolated fix + tests).
- No new backend decision logic; ViewModel/serializer changes are presentation-only.
- No live/network data sources added.
- Replay/backtest deep transplant is **Phase 4** (only the existing reserved `/replay/status` surface is shown).

## 9. Exit criteria for Phase 3

- ⏳ Visual parity with codex across the panels above; codex animations/3D/radar UX preserved. (1/N panels done — Trading.)
- ✅ Zero manual fetch in `components/`; all data via typed hooks → ViewModels — **now enforced** by `test_no_manual_fetch_in_panels`.
- ✅ `KNOWN_UNCONTRACTED` empty (all 6 orphans resolved) and `test_friendly_types_map_to_contract` green with no baseline.
- ✅ Full gate green: `pnpm build`, `make codegen-check`, `make lint`, `make test` (509 passed), arch guards (incl. the 2 new ones).
- ✅ No change to Phase 2 backend behavior (paper suite unchanged).

---
**Status: IN PROGRESS — Wave 0 guards done · contract debt cleared (6/6 orphans) · first Wave 1 slice (Trading) done. Next: shared-shell port + AIReport/DataQuality.**
