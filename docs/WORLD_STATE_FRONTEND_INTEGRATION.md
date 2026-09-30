# World State Frontend Integration TODO

Backend fields are additive and frontend changes are intentionally deferred.

## Existing API fields

Both `/api/v1/dashboard/state` and `/api/v1/cockpit/brief` expose:

- `world_state`: normalized pressures, flow regime, confidence, coverage,
  missing inputs, geopolitical events, and policy statements.
- `causal_shadow`: graph edges, per-asset impacts, conflicts, warnings, and the
  `causal_consensus`, `conflict_shadow`, and the `decision_apply` flag.

## Future components

| UI block | Backend source | Notes |
|---|---|---|
| World State | `world_state` | Show `UNAVAILABLE`/missing inputs explicitly |
| Global Money Flow | `global_flow_regime`, `liquidity` | Evidence badge, not a trade signal |
| Geopolitical Risk | `geopolitical_events`, `geopolitical_risk` | Show confirmation and source confidence |
| Active Statements | `statements` | Show authority and freshness |
| Causal Drivers | `causal_shadow.edges` | Explain source → target transmission |
| Edge audit | edge `applied`, `target_before`, `target_after`, `reason` | Separate applied propagation from direct-measurement evidence |
| Asset Thesis | `causal_shadow.impacts` | Label as shadow thesis |
| Macro | `world_state.rates_pressure`, `real_yield_pressure`, `inflation_pressure`, `growth_pressure` | Render unavailable fields explicitly |
| Macro provenance | `world_state.macro_sources` | Show DIRECT/DERIVED/PROXY/UNAVAILABLE and method |
| Money Flow | `world_state.usd_flow`, `treasury_flow`, `equity_flow`, `credit_flow`, `metals_flow`, `energy_flow`, `crypto_flow`, `defensive_flow` | Show axis coverage |
| Positioning | `world_state.positioning`, impact `positioning_state`, `volatility_regime` | Caution context only |
| Positioning reasons | impact `positioning_reasons`, `positioning_contribution` | Show crowding/options/squeeze/volatility caution |
| Legacy vs Causal | `causal_shadow.causal_consensus` | Backend provides scores and divergence reason |
| World thesis vs timing | `world_thesis_score`, `world_thesis_direction`, `technical_confirmation_tf`, `entry_timing_state`, `final_shadow_score_tf` | Keep global thesis separate from timeframe entry timing |
| Conflict / Confluence | impact `confluence_state`, `causal_shadow.conflict_shadow` | Informational; never execute |
| Learning evidence | backend learning study artifacts | Show `INSUFFICIENT` honestly |
| Event attribution | causal ledger `event_id`, `channels`, `asset_predictions`, `attribution_method` | Render event-specific evidence; never aggregate-copy one event into another |

## Evidence-calibrated contract

| Field | Type | Meaning/example | UI recommendation | Required / unavailable |
|---|---|---|---|---|
| `flow_state.<axis>` | object | `{value, source_type, confidence, coverage, freshness_seconds}`; source is `REAL_FLOW` or `PRICE_FLOW_PROXY` | Flow card with REAL FLOW/PROXY badge and divergence marker | Optional; show `UNAVAILABLE` |
| `flow_observations` | array | Canonical observations with source/evidence | Evidence drawer per axis | Optional; do not infer zero |
| `expectations` | array | `expected_value`, `actual_value`, `baseline`, source and confidence | Expectation vs Actual panel | Optional; omit panel when unavailable |
| `macro_surprises` | array | Numeric surprise and provenance | Surprise strength/details | Optional; show provenance |
| `interactions` | array | Pairwise `SYNERGISTIC`, `REDUNDANT`, or `CONFLICT` result | Interaction warning/badge | Optional; no client recomputation |
| `causal_shadow.edges[*].weight` | number | Applied weight metadata | Edge detail tooltip | Required per edge; `PRIOR` is valid |
| `causal_shadow.edges[*].edge_id` / `sign` | string/number | Canonical graph edge identity and topology sign | Stable edge label; show negative topology explicitly | Required when present; never infer sign from magnitude |
| `causal_shadow.edges[*].weight_source` | string | `PRIOR` or calibrated hierarchy source | PRIOR/CALIBRATED badge | Required; never hide fallback |
| `causal_shadow.edges[*].sample_n` | integer | Evidence sample count | Calibration sample N | Required; `0` means prior |
| `causal_shadow.edges[*].regime` / `horizon` | string/null | Conditional calibration context | Filter chips | Optional; show `UNKNOWN`/`ALL` |
| `replay.coverage_pct` | number | Timestamp coverage of as-of archive | World State timeline/replay coverage | Optional; show insufficient archive |
| `replay.missing_domains` | array | Missing archive/outcome domains | Coverage warning | Optional; render verbatim |
| `replay.status` | string | `REAL_REPLAY`, `PARTIAL_REPLAY`, `INSUFFICIENT_PROVENANCE`, `INSUFFICIENT_ARCHIVE`, or `INSUFFICIENT_OUTCOMES` | Status badge; never infer success from row count | Required |
| `replay.timestamps_reconstructable` / `timestamps_scored` | integer | Reconstruction and scored timestamp counts | Timeline coverage | Optional |
| `replay.missing_provenance_domains` | array | Domain-specific availability gaps | Explain why replay is partial | Optional |
| `replay.provenance_domains.<domain>.status` | string | `AVAILABLE`, `UNAVAILABLE`, or `UNKNOWN` | Render domain status verbatim; only UNKNOWN blocks replay | Optional |
| `replay.provenance_domains.<domain>.as_of` | string/null | Availability watermark for the domain | Show watermark and unavailable reason | Optional |
| snapshot provenance fields | string/null | `market_data_as_of`, `events_available_as_of`, `statements_available_as_of`, `macro_available_as_of`, `expectations_as_of`, `flow_available_as_of`, `ingested_at` | Timeline provenance tooltip | Optional; `null` means provider watermark unavailable |
| `causal_shadow.edges_by_horizon` | object | Horizon-specific edge metadata when test-only calibration is applied | Timeframe edge tooltip/filter | Optional; PRIOR remains default |
| archive `archive_write_reason` / `material_changes` | string/array | `CADENCE_CHECKPOINT`, `MATERIAL_CHANGE`, `REGIME_CHANGE`, `NEW_EVIDENCE` | Archive timeline annotation | Optional |
| calibration `raw_rows` / `eligible_rows` / `rejected_rows` / `rejection_reasons` | integer/object | Evidence quality and sample N audit | Calibration quality panel | Required for artifact |
| calibration `archive_window` | object | Start/end archive timestamps used by worker | Provenance tooltip | Optional |
| `asset_impacts[*].drivers` / `causal_path` | array | Backend-provided explanation chain | Asset causal path panel | Optional; frontend must not calculate |

Edge `sign` and `weight` are separate display values: sign is topology
direction, weight is a non-negative calibrated magnitude. The client never
multiplies them or resolves calibration. Replay positioning fields are
backend-built and must be rendered as evidence only.

The frontend only renders, filters, sorts and visualizes these fields.  It does
not resolve weights, apply regime/horizon fallback, calculate interactions,
infer expectations, or promote calibration.  `UNAVAILABLE`, `INSUFFICIENT`,
`PRIOR`, and `decision_apply=false` remain visible states.

## Frontend rules

- Backend remains authoritative; no score calculation in TypeScript.
- `decision_apply=false` must be visible as a shadow badge.
- Missing evidence must not render as neutral certainty.
- No EVREN key or provider detail reaches the browser.
- All score scales are explicit: world pressures and asset directions are
  `-1..1`; consensus scores are `0..100`.
- The frontend must render `ABSTAIN`, `UNKNOWN`, `UNAVAILABLE`, and missing
  evidence as such; it must not replace them with neutral certainty.
- Expired events remain visible for audit (`expired=true`, effective strength 0)
  but must not render as active pressure.
- Legacy comparison rows are timeframe-specific; do not overwrite one timeframe
  with another.
- `macro_surprise_contribution` is numeric-release evidence and must remain
  separate from `statement_contribution` (policy communication).
- Interaction contributions are rendered from backend `interactions`; the
  client must not recompute redundancy, synergy, conflict or channel blends.
- Archive checkpoint/material-change reasons and calibration rejection counts
  are audit fields, not trading signals.
