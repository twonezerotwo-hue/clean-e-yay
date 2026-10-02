# MERGE BLUEPRINT — Clean Backbone + Codex Transplant

> Status: **living document**. Created on the `migration/clean-backbone-codex-transplant`
> branch. Phase 1 in progress. Verified against real repo state (not README claims).

## 0. Decision

- **`clean-e-yay` is the architectural backbone.** It keeps `apps/` + `packages/` +
  `contracts/openapi.yaml`, a thin HTTP API, a single RiskGate, worker separation, a
  typed data policy, and a contract-first frontend.
- **`e-yay-codex` is the transplant source** for mature *behaviour* and *dashboard look* —
  never copied as-is. Every port is repackaged into clean's structure with tests.
- **Not a blind merge.** Goal = clean backbone + selective codex transplant that stays
  contract-first, deterministic, typed, testable, paper-safe, and maintainable.

## 1. Verified repo state (measured, June 2026)

| Metric | e-yay-codex | clean-e-yay |
|---|---|---|
| Backend Python | ~72,500 LOC / 222 files | ~14,300 LOC / 142 files |
| Test functions | 1,290 / 86 files | **419 passed** (29 files) — *verified green locally* |
| API routers | 55 files (~11,900 LOC) | 15 routers, `main.py` = 85 lines, **no bg loop** |
| Largest file | `paper_trading_service.py` = 2,762 lines | data pkg (split) |
| Replay surface | 67 files | a few modules |
| Background tick | **in FastAPI lifespan** (`main.py:75`, 30s) | none (worker-separated) |
| OpenAPI contract | none (router-driven) | `openapi.yaml` 1,924 lines / 81 schemas / 25 paths |
| TS codegen | manual fetch, no types | `openapi-typescript` installed; `make codegen` was placeholder |
| Risk logic | 7+ locations + root `engine/risk_engine.py` | single `packages/risk/engine.py` |
| AI size multiplier | **>1.0** (`ai_trade_opinion_service.py:580` =1.10; `_HIGH_BOOST`=1.15) | risk pkg explicitly "boost YOK" |

**Corrections to earlier informal report:**
- clean is **not** a skeleton anymore — 14.3k LOC of real implementation. Only
  `packages/paper` (699 LOC) is genuinely thin.
- clean's "419/419" is **true** (verified: `419 passed in 26s`, ruff clean).
- `make codegen` "not yet implemented" — **confirmed** (placeholder echo). Fixed in Phase 1.

## 2. Subsystem comparison & ownership

| Subsystem | Winner | Final owner in merged repo |
|---|---|---|
| Overall architecture | clean | clean `apps/`+`packages/`+`contracts/` |
| Backend HTTP layer | clean | clean thin `apps/api` |
| RiskGate | clean | single `packages/risk/engine.py` |
| Paper trading behaviour | codex (content) | codex behaviour split into `packages/paper/*` |
| Dashboard visuals/UX | codex | codex look re-homed in clean `apps/web` (typed) |
| Dashboard wiring | clean | generated types + ViewModels (no manual fetch) |
| Data policy / no-mock | clean | clean typed `PriceStatus`/`verified` |
| Replay diagnostics | codex (richness) | grouped endpoints in `packages/replay/diagnostics` |
| Learning | clean (proposal+approval) | clean; codex signal-attribution ported |
| Worker/runtime | clean | `apps/tick_worker` + `apps/learning_worker` |
| Contracts/codegen | clean | `contracts/openapi.yaml` truth source + real codegen |
| Tests | codex (volume) | port codex tests with each behaviour |

## 3. Target architecture

See the canonical tree in the task brief (`packages/{data,regime,consensus,decision,risk,
paper,replay,learning,agent,shared}`, `apps/{api,tick_worker,learning_worker,web}`,
`tools/admin_gradio`). The merged repo grows clean toward that tree; codex contributes
behaviour modules and visual components only.

## 4. Non-negotiable system rules (enforced by guards)

1. AI never makes final decisions, never increases size, never bypasses RiskGate/DQS/KillSwitch/owner approval.
2. RiskGate is the single final gate (`packages/risk/engine.py`); no duplicates.
3. Verified data required for live-sounding output; otherwise simulation/paper-safe.
4. Strict paper/live isolation; no broker execution; `AUTO_FULL` disabled.
5. Frontend renders ViewModels; never computes decisions/risk/DQS/PnL/regime.
6. Contract-first: `openapi.yaml` is truth; codegen refreshes types; no manual drift.
7. Worker separation: no tick loop in API lifespan.
8. Config-driven thresholds/pairs/bounds/limits.
9. Every important decision is auditable.

Phase 1 lands machine-checkable guards for rules **2, 6, 7** (`tests/test_architecture_guards.py`);
rules 1, 4, 5, 8 get guards in Phase 6.

## 5. Phase ledger

| Phase | Scope | State |
|---|---|---|
| 0 | Inspection + this blueprint + migration map | **done** |
| 1 | Strict backbone: real codegen, API no-bg-loop guard, single-RiskGate guard, OpenAPI drift check | **in progress** |
| 2 | Port codex paper behaviour into `packages/paper/*` (+guards, strip AI boost, config) | pending |
| 3 | Transplant codex dashboard visuals onto typed ViewModels (no manual fetch) | pending |
| 4 | Grouped replay diagnostics in `packages/replay/diagnostics` | pending |
| 5 | Worker/runtime hardening | pending |
| 6 | Full architecture guard suite | pending |
| 7 | Parity tests codex vs merged | pending |

## 6. Known limitations carried forward (honest)

- **Friendly type layer (`apps/web/types/generated/api.ts`, 1113 lines / 110 aliases) is
  still hand-written.** 80 map 1:1 to schemas; 30 are inline enums. Phase 1 generates the
  canonical `schema.ts` + adds a drift check + a coverage guard, but does **not** rewrite
  `api.ts` (it feeds 31 components — rewriting belongs with Phase 3 panel transplant, where
  each panel switches to `schema.ts`-backed types). Tracked in the migration map.
- **Pydantic model generation deferred.** Backend hand-writes its models and does not import
  generated ones, so per the "if used by backend" rule we do not emit unused Pydantic yet.
  Revisit when a package consumes generated models.
