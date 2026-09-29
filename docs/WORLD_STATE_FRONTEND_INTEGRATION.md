# World State Frontend Integration TODO

Backend fields are additive and frontend changes are intentionally deferred.

## Existing API fields

Both `/api/v1/dashboard/state` and `/api/v1/cockpit/brief` expose:

- `world_state`: normalized pressures, flow regime, confidence, coverage,
  missing inputs, geopolitical events, and policy statements.
- `causal_shadow`: graph edges, per-asset impacts, conflicts, warnings, and the
  `decision_apply` flag.

## Future components

| UI block | Backend source | Notes |
|---|---|---|
| World State | `world_state` | Show `UNAVAILABLE`/missing inputs explicitly |
| Global Money Flow | `global_flow_regime`, `liquidity` | Evidence badge, not a trade signal |
| Geopolitical Risk | `geopolitical_events`, `geopolitical_risk` | Show confirmation and source confidence |
| Active Statements | `statements` | Show authority and freshness |
| Causal Drivers | `causal_shadow.edges` | Explain source → target transmission |
| Asset Thesis | `causal_shadow.impacts` | Label as shadow thesis |
| Legacy vs Causal | existing decision trace + shadow impacts | Never let frontend merge scores |

## Frontend rules

- Backend remains authoritative; no score calculation in TypeScript.
- `decision_apply=false` must be visible as a shadow badge.
- Missing evidence must not render as neutral certainty.
- No EVREN key or provider detail reaches the browser.
