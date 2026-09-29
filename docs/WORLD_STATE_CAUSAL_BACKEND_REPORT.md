# World State + Causal Backend Report

## 1. Baseline

- Baseline commit: `3ebf05f851418ad045083f00c92f5b2103a5833c`
- Branch: `feat/world-state-causal-shadow-v1`
- Mode: additive, deterministic, shadow-only
- `causal_world.decision_apply`: `false`

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
suite passed: 21 tests. The full main-based suite passes with 2058 tests and
one environment-dependent architecture test skipped because
`node/openapi-typescript` is not installed. There is one existing Starlette/httpx
deprecation warning.

## 10. Known limitations

- There is no verified statement provider or numeric macro-consensus feed yet;
  statement and numeric-surprise models remain conservative evidence models.
- Causal weights are deterministic priors and are not yet calibrated from an
  event-outcome dataset.
- Existing `packages/learning/news_event_study.py` remains the compatible
  observation path; causal event-outcome calibration is intentionally not
  auto-wired into the hot decision path.
- EVREN/LLM extraction is intentionally not wired into the decision path.
- Gürsar and Touche repositories were not available in the workspace.

## 11. Activation plan

Observe `causal_shadow` alongside legacy decisions, then add event-study and
walk-forward evidence. Any future activation must remain behind the existing
RiskGate and owner-approved challenger process.
