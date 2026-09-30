# World State + Causal Backend Report

## 1. Baseline

- Baseline commit: `3ebf05f851418ad045083f00c92f5b2103a5833c`
- Branch: `feat/world-state-causal-shadow-v1`
- Mode: additive, deterministic, shadow-only
- `causal_world.decision_apply`: `false`
- PR scope: additive shadow evidence only; legacy Decision/RiskGate/EV/Sizing/Paper remain authoritative.

## 2. Reused architecture

The implementation reuses `MarketSnapshot`, the existing DQS, news/catalyst
pipeline, rotation provider, asset registry, and existing cockpit/dashboard
view-models. No new network provider, trade engine, risk path, or LLM client was
created.

## 3. New architecture

```text
MarketSnapshot
  -> WorldStateSnapshot (-1..1 evidence, coverage, missing inputs)
  -> bounded causal graph
  -> AssetImpact (direction thesis, horizon, conflicts)
  -> additive dashboard/cockpit shadow fields
```

World state is evidence only. The legacy consensus, decision engine, RiskGate,
EV, sizing, and paper lifecycle remain authoritative.

`AssetImpact` also carries an observational `technical_confirmation` and
`timing_status` (`CONFIRMED`, `CONFLICT`, `WAIT`, or `UNAVAILABLE`). These are
read from the existing multi-timeframe technical snapshots only to separate
thesis direction from entry timing; they are not merged into a decision score.

## 4. Files added

- `packages/world_state/__init__.py`
- `packages/world_state/model.py`
- `packages/world_state/engine.py`
- `packages/causal/__init__.py`
- `packages/causal/model.py`
- `packages/causal/engine.py`
- `tests/unit/test_world_state_causal.py`
- `docs/WORLD_STATE_FRONTEND_INTEGRATION.md`

## 5. Files modified

- `config/thresholds_v1.0.yaml`: one `causal_world` feature block, default
  shadow-only.
- `apps/api/routers/dashboard_state.py`: additive `world_state` and
  `causal_shadow` fields.
- `apps/api/routers/cockpit.py`: same additive fields for cockpit consumers.
- `conftest.py`: test-only isolation fix; paper price references are seeded for
  every supported timeframe and auth is kept explicitly empty during reloads.
  This does not change runtime behaviour.
- `config/assets.yaml` and `packages/data/registry/assets.py`: additive asset
  class metadata so causal exposure selection uses the existing registry.
- `packages/learning/news_event_study.py`: additive causal ledger, event study,
  and legacy-vs-causal observation backtest; no second learning framework.

No existing response key was removed or renamed. No database or runtime state
file was migrated.

## 6. Safety invariants

- No LLM call is made by the new layer.
- No BUY/SELL/LONG/SHORT action is produced.
- No position size or portfolio weight is produced.
- No RiskGate or kill-switch path is bypassed.
- Missing data remains `None` and is listed in `missing_inputs`.
- Unverified news cannot create a confirmed geopolitical event.
- A bounded single-pass graph prevents recursive score amplification.
- One-line rollback: set `causal_world.enabled: false`.

## 7. Performance and token policy

The layer is pure in-memory computation over an existing snapshot. It adds no
network calls and consumes zero LLM tokens. Full articles are not sent anywhere.

## 8. API impact

Existing endpoints remain compatible. The following additive fields are now
available in `/api/v1/dashboard/state` and `/api/v1/cockpit/brief`:

- `world_state`
- `causal_shadow`

## 9. Tests

Added coverage for bounded scores, missing-data abstention, numeric-surprise
fallback, graph propagation, disable behavior, and shadow output. The targeted
suite passed: 33 tests. The full main-based suite passes with 2064 tests and
one environment-dependent architecture test skipped because
`node/openapi-typescript` is not installed. There is one existing Starlette/httpx
deprecation warning.

## 10. Known limitations

- The repository calendar is mostly date-only today. Structured actual/expected/
  previous fields are accepted and use historical surprise volatility when
  present; otherwise the explicit relative-difference fallback is marked with
  reduced numeric confidence. Missing macro history remains unavailable.
- Growth uses equity/credit only as an explicitly labelled proxy when a direct
  growth series is absent; CPI quote levels are provenance context, not fake
  pressure.
- Causal weights are deterministic priors and are not yet calibrated from an
  event-outcome dataset.
- Existing `packages/learning/news_event_study.py` remains the compatible
  observation path; causal event-outcome calibration is intentionally not
  auto-wired into the hot decision path.
- EVREN/LLM extraction is intentionally not wired into the decision path.
- Gürsar and Touche repositories were not available in the workspace.

## 12. Completion audit

### Money flow and macro world state

The existing rotation basket is reused to expose separate normalized axes for
USD, Treasuries, equities, credit, metals, energy, crypto, and defensive flow.
Macro rates, real-yield, inflation, and growth pressures remain `None` when
their source evidence is unavailable. Flow and macro domain coverage are
reported separately; regime classification uses deterministic stress/flow
rules rather than one asset average.

### Geopolitics, statements, and surprise

Geopolitical headlines are clustered by normalized story key, taxonomy is
expanded to attacks, ceasefires, sanctions, chokepoints, shipping, pipelines,
trade, and nuclear escalation, and exposure channels are emitted before asset
impact. Source families prevent syndicated copies from counting as independent
confirmation. Confidence is source reliability (credibility, confirmation,
diversity, and official evidence); freshness decay is applied once to effective
event strength. Canonical clustering tolerates deterministic wording/synonym
changes.

Statement authority is config-driven. Institution, role, repetition, baseline
stance, semantic surprise, and optional `actual`/`expected` numeric fields are
deterministically extracted. No statement can create a trade action.

### Causal graph and asset exposures

Graph priors live under the single `causal_world.graph` config block, including
sanctions/trade transmission. Active edges now return source value, contribution,
effective strength, applied/non-applied state, target before/after, reason, and evidence,
matching the actual bounded one-pass propagation. Direct measured factors stay
authoritative, so derived nodes cannot double-count the same input. Asset
exposures come from the existing asset registry metadata plus the single
`causal_world.asset_exposures` mapping; no second symbol universe is created.

### Positioning, conflict, and consensus

Verified derivatives, options, skew, put/call, squeeze, and 1d volatility
snapshots are reused as positioning context. Crowded-long/short, options
crowding/fear, squeeze risk, and elevated volatility reduce confidence/caution
only; they never flip the thesis or relax a risk gate. Existing
`packages.decision.conflict_resolver` is called only with real legacy context;
missing RR/history/size inputs remain unavailable. `causal_consensus` compares
legacy score/direction per `(symbol,timeframe)` when supplied,
includes confluence, technical timing, coverage, and `ABSTAIN` for insufficient
evidence. All of these fields are additive and non-authoritative.

### Learning and backtest

`packages/learning/news_event_study.py` now also provides a bounded causal event
ledger, channel/asset/horizon event study using existing OHLCV history, a
timestamped historical replay evaluator, and legacy-vs-causal observation
backtest. The learning worker records causal event + asset predictions off-tick;
ledgers are deduplicated and size-capped under `data/runtime/`.
Forward-return rows are required; missing rows remain pending. Results are
`INSUFFICIENT` below the sample threshold and cannot auto-promote weights or
activate decisions.

## 11. Activation plan

Observe `causal_shadow` alongside legacy decisions, then add event-study and
walk-forward evidence. Any future activation must remain behind the existing
RiskGate and owner-approved challenger process.

## 13. Performance

World State and causal propagation are pure in-memory work over the existing
snapshot. No new network request or LLM token is used. Event study/backtest
functions are off-tick learning utilities and are not called by the decision
hot path.
