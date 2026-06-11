# TASK RESULT

Date: 2026-06-11
Task: G3 — Mistake Memory Gate (no RiskGate bypass)
Status: completed

## Files changed

Backend
- `packages/learning/mistake_memory.py` (new) — Mistake / MistakeVerdict
  dataclasses; `summary()` aggregates verified+fingerprint'li closed
  trades; `evaluate()` returns AVOID / BOOST / WARNING / NEUTRAL with
  size_factor. `MIN_TRADES=3` fallback → NEUTRAL.
- `packages/decision/engine.py` — TradeDecision now carries `fingerprint`
  and `mistake_verdict`. After consensus thresholds pass, mistake memory
  is consulted: AVOID → hold; BOOST/WARNING → size_factor multiplier
  (size capped at 1.5). **RiskGate hard gates run first**; KILL_SWITCH,
  RISK_REDUCE, NO_POSITION_INCREASE override mistake memory.
- `apps/api/routers/learning.py` — added
  `GET /api/v1/learning/mistakes` (records + verdicts + thresholds +
  flagged_count + total_fingerprints).

Frontend
- `apps/web/types/generated/api.ts` — MistakeAction / MistakeRecord /
  MistakeVerdict / MistakesState.
- `apps/web/lib/api/client.ts` + `lib/queries/{keys,hooks}.ts` —
  `api.mistakes` + `useMistakes`.
- `apps/web/lib/selectors/mistakes.ts` (new).
- `apps/web/components/panels/MistakeMemoryPanel/index.tsx` (new) —
  flagged fingerprints + action badge + reason + size×factor + record
  stats (trades / win_rate / total_pnl / streak / last_seen).
- `apps/web/lib/panel-registry.ts` — mistake_memory entry (learning group).
- `apps/web/app/page.tsx` — grid cell.

Tests
- `tests/unit/test_mistake_memory.py` (new, 11 tests):
  - summary skips unverified + missing-fp.
  - evaluate NEUTRAL below MIN_TRADES.
  - evaluate AVOID for low win_rate.
  - evaluate BOOST for high win_rate.
  - evaluate WARNING for marginal win_rate (no streak).
  - evaluate AVOID for streak ≥ STREAK_AVOID.
  - decision AVOID → hold (forced strong-bullish consensus path).
  - **KILL_SWITCH beats BOOST**.
  - **RISK_REDUCE beats BOOST**.
  - **DQS BLOCKED → blocked even with forced BOOST**.
  - endpoint returns records + verdicts + thresholds.

## Tests run

- `pytest -q` → 47/47 passed (11 new G3 + 36 prior).
- `ruff check packages apps/api apps/tick_worker apps/learning_worker`
  → All checks passed.

## Result

passed

## Notes

- Mistake memory is informational/sizing-only; **never** loosens RiskGate
  or hard gates.
- NEUTRAL fallback: size_factor=1.0; AVOID size_factor=0.0; BOOST=1.2;
  WARNING=0.7.
- Decision engine size_multiplier final capped at [0, 1.5] post-factor.
- Lokal `node`/`pnpm` yok → `next build` CI'da doğrulanacak.

## Next

- G4 — correlation-aware sizing veya G5 — daily-loss / max-DD halt.
