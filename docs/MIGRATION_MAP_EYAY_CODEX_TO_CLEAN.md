# MIGRATION MAP — e-yay-codex → clean-e-yay

> Per-feature migration ledger. Statuses: **TAKE** (port behaviour, repackage),
> **REWRITE** (reimplement clean against contract), **ARCHIVE** (keep in codex as
> reference only), **DELETE** (drop, anti-pattern), **ALREADY_EXISTS_IN_CLEAN**.
> codex paths are relative to `e-yay-codex/`; clean targets relative to this repo.
> "Tests" = tests that must exist/pass before the port is accepted.

## Legend of risk
`R1` low · `R2` medium · `R3` high (touches RiskGate / paper safety / live-isolation).

## A. Backend — API & routing

| Item | codex source | Status | clean target | Reason | Tests | Risk |
|---|---|---|---|---|---|---|
| Router framework (55 routers) | `backend/app/api/*` | DELETE | clean `apps/api/routers/*` | codex API is bloated + holds business logic | arch guard | R1 |
| Background tick in lifespan | `backend/app/main.py:69-116` | DELETE | `apps/tick_worker` | HTTP must not own trading loop | `test_api_has_no_background_loop` | R2 |
| Thin app factory | `backend/app/main.py` | ALREADY_EXISTS_IN_CLEAN | `apps/api/main.py` | clean is already thin (85 lines) | — | R1 |

## B. RiskGate

| Item | codex source | Status | clean target | Reason | Tests | Risk |
|---|---|---|---|---|---|---|
| Risk engine | `backend/app/services/risk_engine.py` + root `engine/risk_engine.py` | ALREADY_EXISTS_IN_CLEAN | `packages/risk/engine.py` | clean already unified, priority-ordered, restrictive-only | `test_event_risk`, `test_halt`, `test_single_riskgate` | R3 |
| Duplicate risk logic in paper/aggregator | `services/paper_trading_service.py`, `aggression_awareness.py` | DELETE | — | single gate only | `test_single_riskgate` | R3 |

## C. Paper trading (Phase 2 — the big transplant)

| Item | codex source | Status | clean target | Reason | Tests | Risk |
|---|---|---|---|---|---|---|
| Paper state + atomic write + corrupt backup | `services/paper_trading_service.py`, `paper_account_archive.py` | TAKE | `packages/paper/state.py`, `maintenance.py` | mature field behaviour | `test_paper_account_archive` (port) | R3 |
| Lifecycle (open/close/manage) | `paper_trading_service.py` | TAKE→REWRITE | `packages/paper/lifecycle.py` | split monolith | `test_paper_lifecycle` (exists) | R3 |
| Manual-ready / pending / rejected workflow | `paper_trading_service.py`, `api/paper_trading.py` | TAKE | `packages/paper/manual_queue.py` | DEFENSIVE/CRISIS owner approval | `test_paper_trading_manual_ready` (443 lines, port) | R3 |
| Price sanity guard | `paper_trading_service.py` (inline) | TAKE | `packages/paper/guards/price_sanity.py` (+`packages/data/guards/price_sanity.py`) | cross-pair contamination bug | new `test_price_sanity_guard` | R3 |
| State anomaly guard | `services/paper_trading_service.py`, `test_paper_trading_state_anomaly.py` | TAKE | `packages/paper/guards/state_anomaly.py` | absurd equity/PnL → block new opens | `test_paper_trading_state_anomaly` (463 lines, port) | R3 |
| Position sizing | `services/paper_risk_sizing.py` | TAKE→REWRITE | `packages/paper/sizing.py` | **strip boost** (`_HIGH_BOOST`=1.15) | new `test_no_ai_size_boost` | R3 |
| Execution simulation / mark-to-market | `paper_trading_service.py` | TAKE | `packages/paper/execution_sim.py` | paper-safe fills | port flow test | R2 |
| Signal attribution | `services/signal_attribution.py`, `api/signal_attribution.py` | TAKE | `packages/learning/decision_log.py` | learning + audit trail | new `test_signal_attribution` | R2 |
| AI trade opinion size multiplier >1.0 | `services/ai_trade_opinion_service.py:580`, `paper_risk_sizing.py:27` | DELETE | clamp ≤1.0 in `packages/agent` | AI must never increase size | `test_no_ai_size_boost` | R3 |

## D. Dashboard / frontend (Phase 3)

| Item | codex source | Status | clean target | Reason | Tests | Risk |
|---|---|---|---|---|---|---|
| Visual components (49) | `frontend/components/*` | TAKE (visual only) | `apps/web/components/*` | preferred look/UX | tsc + panel arch test | R2 |
| Manual `fetch("/api/v1/...")` wiring | `frontend/lib/api.ts` | DELETE | generated client + ViewModels | no frontend truth source | `no manual fetch in panels` guard | R2 |
| Friendly TS types (hand-written) | — (clean's own `types/generated/api.ts`) | REWRITE | re-export from generated `schema.ts` | kill manual drift | tsc drift | R2 |
| Gradio admin panel | `backend/app/dashboard/gradio_dashboard.py` (1048) | TAKE (optional) | `tools/admin_gradio/` | local debug only, not main UI | smoke | R1 |

## E. Replay / backtest (Phase 4)

| Item | codex source | Status | clean target | Reason | Tests | Risk |
|---|---|---|---|---|---|---|
| Replay store + snapshot validation | `services/snapshot_replay_*` (67 files) | TAKE→REWRITE | `packages/replay/store.py` | dedupe 67→grouped | `test_snapshot_replay` (exists) | R2 |
| Source quality/registry/timing diagnostics | `services/snapshot_replay_source_*` | TAKE | `packages/replay/diagnostics/{source_quality,source_registry}.py` | valuable, fragmented | new grouped tests | R2 |
| Risk/regime stability diagnostics | `services/snapshot_replay_transition_diagnostics.py` | TAKE | `packages/replay/diagnostics/{risk_stability,regime_timeline}.py` | audit value | new tests | R2 |
| 49 per-diagnostic endpoints | `api/snapshot_replay_routes_*` | DELETE | 4 grouped endpoints | maintenance cost | contract test | R1 |

## F. Data providers

| Item | codex source | Status | clean target | Reason | Tests | Risk |
|---|---|---|---|---|---|---|
| Provider adapters | `backend/app/providers/*` | ALREADY_EXISTS_IN_CLEAN | `packages/data/providers/*` | clean typed pipeline | `test_providers` | R2 |
| Mock market provider | `providers/mock_market_provider.py` | DELETE (prod path) | fixtures only, test-scoped | no runtime mock | `test_provenance` + Phase-6 guard | R3 |
| Price bounds / jump constants (hardcoded) | `paper_trading_service.py` | REWRITE | `config/*.yaml` | config-driven | config load test | R2 |

## G. Learning

| Item | codex source | Status | clean target | Reason | Tests | Risk |
|---|---|---|---|---|---|---|
| Calibration / mistake memory | codex learning services | ALREADY_EXISTS_IN_CLEAN | `packages/learning/*` | clean proposal+approval is safer | `test_calibration`, `test_mistake_memory` | R1 |
| Auto-weight write | codex auto-tune | DELETE | proposal + owner approval | no auto weight write | `test_rebalance` | R2 |
| Similar-trade memory | codex memory service | TAKE (narrative only) | `packages/learning/mistake_memory.py` | explanation, not decision | port test | R1 |

## H. Worker / runtime

| Item | codex source | Status | clean target | Reason | Tests | Risk |
|---|---|---|---|---|---|---|
| Tick scheduler | codex API lifespan | REWRITE | `apps/tick_worker` | SIGTERM-aware daemon | `test_worker_reliability` (exists) | R2 |
| Learning worker | codex scheduler | ALREADY_EXISTS_IN_CLEAN | `apps/learning_worker` | one-shot/scheduled | `test_worker_reliability` | R1 |

## I. Contracts / codegen

| Item | codex source | Status | clean target | Reason | Tests | Risk |
|---|---|---|---|---|---|---|
| OpenAPI contract | none | ALREADY_EXISTS_IN_CLEAN | `contracts/openapi.yaml` | clean is contract-first | drift check | R1 |
| Real codegen pipeline | none | REWRITE (Phase 1) | `scripts/codegen.py` + `make codegen` | placeholder → real `schema.ts` | `test_openapi_schema_ts_in_sync` | R1 |

## Phase 1 deltas (this branch)

- `scripts/codegen.py` — real `openapi.yaml → apps/web/types/generated/schema.ts`
  (via installed `openapi-typescript`) + `--check` drift mode.
- `Makefile` — `codegen` target now runs `scripts/codegen.py`.
- `apps/web/types/generated/schema.ts` — **new generated artifact** (canonical contract types).
- `tests/test_architecture_guards.py` — no-bg-loop, single-RiskGate, codegen drift,
  friendly-types↔contract coverage.

## Deferred / next

- Rewrite `apps/web/types/generated/api.ts` to re-export from `schema.ts` (with Phase 3).
- Pydantic generation once a backend package consumes generated models.
- Phase-6 guards: no-mock-in-prod, no `AUTO_FULL`, AI no-boost, frontend no-decision-math.
