# TASK RESULT

Date: 2026-06-11
Task: G6 — Confidence Calibration (Platt scaling tam entegrasyon)
Status: completed

## Files changed

Backend
- `packages/learning/calibration_store.py` (new) — Platt params file store
  (a, b, samples, fitted_at, status); `predict_calibrated()` +
  `raw_confidence_from_score()`. Identity default, no live calibration
  bypass.
- `packages/learning/calibration_trainer.py` (new) — train() reads paper
  state, filters `data_verified=True` and `predicted_confidence is not
  None`, requires `MIN_SAMPLES=10`, writes params + reliability bins.
- `packages/decision/engine.py` — TradeDecision now carries
  `raw_confidence` + `confidence_source`. Calibrated `confidence` (cal_p)
  used for sizing/info only. **RiskGate hard gates run BEFORE consensus
  thresholds:** KILL_SWITCH→blocked (conf=0); RISK_REDUCE/NO_POSITION_
  INCREASE→hold (conf=0). Consensus eşiği aşılmadığında neutral fallback.
- `packages/paper/state.py` + `packages/paper/lifecycle.py` —
  Position/Trade get `predicted_confidence/raw_confidence/confidence_source`.
- `apps/api/routers/learning.py` — added
  `GET /api/v1/learning/calibration`,
  `POST /api/v1/learning/calibration/retrain`.
- `apps/api/routers/paper_trading.py` + `apps/tick_worker/main.py` —
  pass calibration trio from TradeDecision to open_position.
- `apps/learning_worker/main.py` — calls calibration trainer before
  auto-weight trainer.
- `packages/learning/summary.py` — replaced 0.5 placeholder with real
  `predicted_confidence` samples (verified filter).

Frontend
- `apps/web/types/generated/api.ts` — CalibrationParams + CalibrationState.
- `apps/web/lib/api/client.ts` + `lib/queries/{keys,hooks}.ts` —
  `api.calibration` + `useCalibration`.
- `apps/web/components/panels/CalibrationPanel/index.tsx` (new) — status
  chip, (a, b), last fit, reliability grid (uses existing
  CalibrationGrid chart).
- `apps/web/lib/panel-registry.ts` — calibration entry (learning group).
- `apps/web/app/page.tsx` — grid cell.

Tests
- `tests/unit/test_calibration.py` (new, 10 tests):
  - predict identity by default.
  - trainer INSUFFICIENT below MIN_SAMPLES; identity-store wrote.
  - trainer FITTED with sufficient samples; a>0; calibrated p>0.5 for
    high raw.
  - unverified or missing-predicted records excluded.
  - **KILL_SWITCH/RISK_REDUCE not bypassed** by high calibration.
  - TradeDecision carries raw_confidence + confidence_source.
  - GET /learning/calibration returns state.
  - POST /learning/calibration/retrain returns FITTED.
  - DQS BLOCKED → all decisions "blocked" even with calibration high.

## Tests run

- `pytest -q` → 36/36 passed (10 new G6 + 26 prior).
- `ruff check packages apps/api apps/tick_worker apps/learning_worker`
  → All checks passed.

## Result

passed

## Notes

- Calibration is informational/sizing-only; **never** loosens RiskGate.
- Insufficient data path keeps identity (a=1, b=0); confidence_source
  damgalanır ki dashboard kullanıcıyı uyarsın.
- Owner approval calibration için gerekmez (audit: params + fitted_at +
  status + samples).
- Lokal `node`/`pnpm` yok → `next build` CI'da doğrulanacak.

## Next

- G3 — mistake memory gate veya G4 — correlation-aware sizing.
