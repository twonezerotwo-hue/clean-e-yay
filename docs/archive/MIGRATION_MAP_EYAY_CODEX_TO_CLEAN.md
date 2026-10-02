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

## Phase 2 deltas (this branch) — paper guards

Ported the two P0 self-contained guards (price sanity, state anomaly), config-driven:

- `config/thresholds_v1.0.yaml` — new `price_sanity` (bounds + max_jump_pct) and
  `state_anomaly` (equity_multiplier, daily_pnl_fraction) sections.
- `packages/data/guards/price_sanity.py` — canonical guard:
  - `price_sane_reason` / `is_price_sane` — OPEN-time gate (absolute bounds; optional
    jump check vs a reference).
  - `tick_price_usable` — manage/close gate: usable if in-bounds **OR** a small jump
    from the last price; contamination fails both. The OR-rule tolerates a stale
    `current_price` (real in-bounds price still usable) while rejecting cross-pair
    contamination (out of bounds AND a large jump).
- `packages/paper/guards/{__init__,price_sanity,state_anomaly}.py` — paper handles
  (price_sanity re-exports the canonical guard — single source, no duplication).
- `packages/paper/lifecycle.py` — `attempt_open` blocks `price_insane` (absolute
  bounds) and `state_anomaly` (absurd accounting) for NEW opens; `tick`/`flatten_all`
  drop contaminated prices (never close/manage on garbage).
- `tests/unit/test_paper_guards.py` — 11 tests (bounds/jump/contamination, anomaly
  detect, attempt_open rejection, contaminated-tick no-close, anomaly-blocks-open,
  anomaly-allows-close). Updated 4 `attempt_open` test prices to in-bounds values.

Validation: ruff ✓, `make test` → **436 passed** (425 + 11), codegen-check ✓.

Design notes / deferred:
- The **jump guard is unit-tested** but at tick time we rely on the in-bounds OR
  small-jump rule; wiring a per-symbol last-sane-price tracker (true consecutive-tick
  jump rejection within bounds) belongs in `apps/tick_worker` (Phase 5).
### Phase 2b — manual-ready workflow (core landed)

- `packages/paper/state.py` — additive `ManualReady` + `RejectedSignal` dataclasses,
  `PaperState.manual_ready` / `rejected_signals` lists (forward-compatible to_dict/from_dict).
- `packages/paper/manual_queue.py` — `route_to_manual_ready`, `should_silent_block`
  (fingerprint-independent on symbol+side+tf), `is_recurring_signal`, `reject`
  (records rejection), `dismiss` (no rejection), `approve` (opens via guarded
  `attempt_open`, clears queue), `purge_stale_rejection`.
- `apps/api/routers/paper_trading.py` — tick routes DEFENSIVE/CRISIS open candidates to
  the manual-ready queue (no auto-open; silent-block on repeat).
- `tests/unit/test_manual_queue.py` — 12 tests. Suite **448 passed**.

Deferred (next increment — contract-first HTTP layer):
- OpenAPI schemas for the queue + `GET /paper-trading/manual-ready`,
  `POST .../{id}/approve|reject|dismiss` endpoints → codegen → router wiring.
- Surface `manual_ready` in the `/paper-trading/state` response (contract change).
- Integration test of tick routing under a forced DEFENSIVE regime.

Still TODO in Phase 2: `sizing.py` (strip AI boost), `execution_sim.py`,
`maintenance.py`, signal attribution.
- **Pre-existing test-isolation note (not introduced here):** running
  `test_paper_lifecycle` before `test_halt` leaks a monkeypatched pipeline from
  `test_state_endpoint_surfaces_lifecycle_and_audit`, failing the live-pipeline halt
  tests. CI/`make test` collect alphabetically (`test_halt` first) so the suite is
  green; the ordering fragility should be fixed separately.

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
