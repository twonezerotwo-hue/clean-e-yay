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
