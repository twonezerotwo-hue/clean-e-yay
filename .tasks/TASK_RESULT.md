# TASK RESULT

Date: 2026-06-11
Task: G2 — Auto-Weight Trainer + Owner-Approved Rebalance
Status: completed

## Files changed

Backend
- `packages/paper/state.py` — Position/Trade `data_verified: bool` flag.
- `packages/paper/lifecycle.py` — `open_position(..., data_verified)`;
  close transfers flag.
- `apps/api/routers/paper_trading.py` — `verified_flags` from snapshot,
  passed into open.
- `apps/tick_worker/main.py` — same wiring.
- `packages/data/registry/loader.py` — `load_active_weights()`,
  `weights_manifest_path()`, `active_weights_version()` (no cache).
- `packages/consensus/engine.py` — uses `load_active_weights()`.
- `packages/learning/auto_weight_trainer.py` (new) — `train()`,
  `proposal_to_dict()`, RebalanceProposal/ModulePerf/WeightDelta dataclasses.
  Filters non-verified trades; respects YAML constraints; bumps version.
- `packages/learning/rebalance_store.py` (new) — file-backed proposal
  store (pending/history); `approve_current()` writes new YAML + manifest;
  `reject_current()` archives.
- `apps/api/routers/rebalance.py` (new) — propose/proposal/approve/reject
  endpoints.
- `apps/api/main.py` — wire rebalance router.
- `apps/learning_worker/main.py` — calls `trainer.train()` after summary;
  writes pending proposal when eligible.

Frontend
- `apps/web/types/generated/api.ts` — WeightDelta, ModulePerf,
  RebalanceProposalRecord, RebalanceState, ProposalStatus.
- `apps/web/lib/api/client.ts` + `lib/queries/{keys,hooks}.ts` —
  `api.rebalanceProposal` + `useRebalanceProposal`.
- `apps/web/lib/selectors/rebalance.ts` (new).
- `apps/web/components/panels/WeightProposalPanel/index.tsx` (new) —
  active version → proposed version, top delta'lar, audit_note;
  "owner approval bekliyor" badge.
- `apps/web/components/panels/WeightHistoryPanel/index.tsx` (new) —
  history timeline.
- `apps/web/lib/panel-registry.ts` — 2 yeni giriş (learning group).
- `apps/web/app/page.tsx` — 2 yeni GridCell.

Tests
- `tests/unit/test_rebalance.py` (new, 8 tests):
  - INSUFFICIENT: no_verified_trades, below_min_total.
  - Proposal emit + normalized weights.
  - Unverified records excluded; rejected_records count correct.
  - Propose → approve → manifest yazar, active_weights_version yeni.
  - Reject pending'i siler, baseline'a düşer.
  - active_weights baseline fallback (manifest yok).
  - consensus active weights üzerinden çalışır.

## Tests run

- `pytest -q` → 26/26 passed (8 new G2 + 18 prior).
- `ruff check packages apps/api apps/tick_worker apps/learning_worker`
  → All checks passed.

## Result

passed

## Notes

- Owner approval mantığı: pending proposal yazılır; consensus baseline
  okur. Yalnızca `POST /learning/rebalance/approve` çağrısı yeni yaml +
  manifest yazar → consensus o anda yeni weights'e geçer.
- Trainer constraint'lere uyar: `max_delta_per_module=0.03`,
  `max_total_drift=0.10`, `min_module_floor=0.02`.
- Lokal `node`/`pnpm` yok → `next build` CI'da doğrulanacak.

## Next

- G6 — confidence calibration (Platt scaling tam entegrasyon)
  veya G3 — mistake memory gate.
