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

### Macro Surprise Transmission

Structured calendar outcomes are mapped by event semantics: CPI/PCE to
inflation/rates, NFP to growth/rates, unemployment with inverse growth sign,
GDP/PMI/retail sales to growth, policy-rate releases to rates, and oil
inventory with inverse oil pressure. Surprise normalization and half-life are
config-driven; fallback normalization is marked with reduced confidence.
Macro release evidence is separate from policy statements and is exposed on
`WorldStateSnapshot.macro_surprises` and `AssetImpact.macro_surprise_contribution`.

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

### Positioning No-Flip Invariant

Positioning, options, squeeze and volatility are confidence/timing evidence
only. `AssetImpact.direction_score` is the base causal thesis and is not
modified by positioning; caution is represented by `positioning_multiplier`,
`entry_quality`, `positioning_state`, and `positioning_reasons`.

### Event-Specific Causal Attribution

The off-tick worker uses `build_event_asset_attribution()` for each event's own
channel strengths. Global predictions are never copied to every event. Macro
surprise events and geopolitical events share the bounded ledger schema with
an explicit `attribution_method` and prediction confidence.

### Learning and backtest

`packages/learning/news_event_study.py` now also provides a bounded causal event
ledger, channel/asset/horizon event study using existing OHLCV history, a
timestamped historical replay evaluator, and legacy-vs-causal observation
backtest. The learning worker records causal event + asset predictions off-tick;
ledgers are deduplicated and size-capped under `data/runtime/`.

### Historical Replay vs Evaluator

`causal_historical_evaluator()` evaluates timestamped materialized rows and
rejects rows whose event timestamp is after the as-of timestamp.  The runtime
tick worker now retains a compact raw `MarketSnapshot` payload in the existing
snapshot store.  When domain watermarks are complete,
`causal_historical_replay()` filters that payload to T, calls the existing
`world_state.build()` and shadow pipeline, and scores the reconstructed output.
An archive row alone cannot become `REAL_REPLAY`; factor-only legacy rows are
explicitly reported as factor-state reconstruction rather than raw replay.

### Per-Timeframe Causal Timing

World thesis score/direction are global per symbol. Each causal consensus row
adds timeframe-specific technical confirmation, `entry_timing_state`, and
`final_shadow_score_tf`; the timing view can be `WAIT`, `CONFLICT`, or
`CAUTION` without changing thesis direction.
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

## 14. Real Flow Architecture

`FlowObservation` is the single flow evidence model.  Published values are
`REAL_FLOW`; derivatives/holdings evidence is `POSITIONING_PROXY`; existing
rotation momentum is explicitly `PRICE_FLOW_PROXY`.  Selection follows
`REAL_FLOW → POSITIONING_PROXY → PRICE_FLOW_PROXY → UNAVAILABLE`, while all
observations remain visible so a real-flow/price divergence is auditable.

## 15. World-State Archive

`packages/world_state/archive.py` reuses the file-backed runtime pattern and
writes compact material-change snapshots to
`data/runtime/world_state_archive.jsonl`.  It stores factor values, flow
provenance, regime, event/statement/expectation IDs, interactions, impacts and
consensus references; raw provider payloads are not duplicated.  Records carry
`schema_version` and `causal_config_version`, deduplicate unchanged state, and
are bounded by configured retention/max rows.

## 16. Expectations Baseline

`ExpectationState` keeps actual, expected, baseline, source and confidence
provenance.  Numeric surprise uses explicit consensus first; statement
repetition and previous stance reduce novelty.  Missing expectations remain
`UNAVAILABLE` and never become a fabricated zero.

## 17. Full Historical Replay

`causal_historical_evaluator()` remains the materialized-row scorer.  The
separate `causal_historical_replay()` first requires domain-specific
watermarks and a stored raw `MarketSnapshot(T)` input, then rebuilds the
existing WorldState/causal shadow at T.  It reuses the production builders;
there is no parallel replay engine.  An archive row alone cannot become
`REAL_REPLAY`; honest statuses include `PARTIAL_REPLAY`,
`INSUFFICIENT_PROVENANCE`, `INSUFFICIENT_ARCHIVE`, and
`INSUFFICIENT_OUTCOMES`.  Future event/ingestion/macro fields and future bars
are rejected; revised values cannot overwrite a first-release as-of state.

### Replay provenance domain states

Each replay domain (`market`, `events`, `statements`, `macro`, `expectations`,
`flow`) carries `AVAILABLE`, `UNAVAILABLE`, or `UNKNOWN`. `AVAILABLE` requires
a real watermark at or before T; `UNAVAILABLE` explicitly means the provider
did not supply that domain and is accepted; `UNKNOWN` is a blocker. This keeps
an absent flow provider distinct from flow evidence that was used without a
known timestamp. Legacy rows without the explicit state remain conservative:
an absent watermark is treated as unknown.

### Runtime snapshot replay parity

The snapshot-store reconstruction payload is schema-versioned (`2`) and retains
the normalized runtime fields for derivatives, volatility, options and catalyst
impacts in addition to prices, technicals, news, catalysts, rotation and flow
observations. Deserialization uses the existing models, drops nested evidence
after T, and treats missing old fields as empty/unavailable. Replay then calls
the existing `world_state.build(snapshot_T)` path, so positioning, options
caution, volatility regime and squeeze state use the same runtime calculation
rather than a duplicate replay engine.

## 18. Edge Calibration

`packages/learning/causal_calibration.py` measures factor-to-factor evidence
and emits prior sign/strength, sample N, observed effect, hit rate, median,
confidence interval, stability and a recommended strength.  A sign conflict is
`UNSTABLE_EDGE`; it is never silently inverted.  Recommendations are written
as shadow artifacts only and do not edit YAML or active graph weights.

### Calibration sign invariant

The canonical edge ID and topology sign are separate from the calibrated
magnitude. `edge_id` is the configured graph key (for example
`rates_to_liquidity`), `sign` is `-1` for an inverse relationship, and
`prior_strength`/`recommended_strength`/resolved `weight` are always
non-negative magnitudes. The graph applies exactly one direction operation:
`source_value * sign * positive_strength`. This prevents signed legacy
artifacts from double-flipping negative edges. The calibration artifact is
recommendation-only and `causal_world.calibration.apply=false` remains the
production default.

## 19. Regime- and Horizon-Dependent Causality

Calibration groups global, regime, horizon and regime+horizon observations.
Resolution order is `REGIME_HORIZON_CALIBRATED → HORIZON_CALIBRATED →
REGIME_CALIBRATED → GLOBAL_CALIBRATED → PRIOR`, subject to minimum N.  Applied
edge metadata exposes `weight`, `weight_source`, `sample_n`, `regime` and
`horizon`; the configured activation flag remains false.

## 20. Event Interaction Engine

Pairwise interactions are bounded to shared causal channels.  Same-root events
are `REDUNDANT` and damped; independent aligned shocks may be `SYNERGISTIC`;
opposite shocks are `CONFLICT`.  Root IDs and evidence are retained to prevent
double counting.  No 3-way/4-way combinatorial model is created.

## 21. Weight Resolution and Learning Loop

The existing causal graph remains the only graph.  Event ledger rows now retain
factor predictions, factor/asset outcomes, causal paths and root event IDs.
The off-tick event study can measure both factor transmission and asset
returns; calibration output is recommendation-only with no automatic
promotion.

## 22. Architecture flow

```text
REAL WORLD → OBSERVATIONS → HISTORICAL ARCHIVE → EXPECTATIONS → SURPRISE
→ WORLD STATE → SINGLE CAUSAL GRAPH → REGIME/HORIZON/INTERACTIONS
→ CALIBRATED TRANSMISSION → ASSET IMPACT → TECHNICAL TIMING
→ SHADOW CONSENSUS → EVENT LEDGER → FULL REPLAY → CALIBRATION
```

## 23. Closed-Loop Calibration Runtime

The learning worker calls `causal_calibration.run_if_due()` off-tick.  It uses
the same bounded World-State archive to materialize matured
`source_value → target_response` factor deltas, applies root/horizon
deduplication and quality rejection, then writes
`data/runtime/causal_calibration.json`.  The artifact reports raw, eligible and
rejected rows plus rejection reasons and archive window.  It is recommendation
only; `causal_world.calibration.apply=false` remains the production default.

## 24. Archive Material-Change Policy

`cadence_seconds` controls periodic checkpoints while
`material_change_epsilon` gates factor noise.  Regime, new event/statement/
macro/expectation evidence and material factors bypass cadence.  Rows carry
`archive_write_reason`, `material_changes`, domain provenance, and edge
predictions; retention/max-row limits remain enforced.

## 25. Interaction Channel Application

Interactions use one config-driven bounded map for inflation, growth, rates,
oil, risk, energy, shipping, trade, sanctions and liquidity.  Same-root
redundancy is damped by the existing pairwise engine; independent aligned and
opposite shocks remain bounded synergy/conflict evidence.  Direct factors stay
authoritative and no duplicate graph is created.

## 26. Remaining Limitations

`MarketSnapshot` carries optional domain availability watermarks and the tick
worker persists the raw reconstruction payload beside the existing snapshot
record.  Provider gaps remain `None` (never fabricated from `generated_at`),
so affected rows stay evaluator/archive evidence rather than claiming full
historical reconstruction.  Calibration recommendations require matured
archive horizons and sufficient verified N; they are never auto-promoted.
