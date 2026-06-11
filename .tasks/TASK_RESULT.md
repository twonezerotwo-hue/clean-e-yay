# TASK RESULT

Date: 2026-06-11
Task: G1.1 — Disable runtime mock fallback (data policy enforcement)
Status: completed

## Files changed

Backend
- `packages/data/types.py` — PriceQuote: `price: float | None`, +verified,
  +status (`OK/DATA_UNAVAILABLE/MOCK`), +error.
- `packages/data/providers/price/mock.py` — quotes marked `verified=False`,
  `status="MOCK"`; unmapped symbol → `DATA_UNAVAILABLE`.
- `packages/data/providers/price/coingecko.py` — success: verified+OK.
- `packages/data/providers/price/yfinance.py` — success: verified+OK.
- `packages/data/providers/price/fred.py` — success: verified+OK.
- `packages/data/providers/price/__init__.py` — rewrite: dynamic env,
  `is_test_mock_allowed()`, `is_runtime_mock_explicit()`, `is_mock_mode()`;
  no mock fallback at runtime; FRED missing key explained in error.
- `packages/data/quality/dqs.py` — None-aware DQS, `status` enum
  (OK/DEGRADED/BLOCKED).
- `packages/data/ingestion/pipeline.py` — MOCK MODE warning when runtime
  opt-in.
- `packages/regime/classifier.py` — `_price_or()` helper, None-safe.
- `apps/api/routers/data.py` — serializes new fields + `mode` block.
- `apps/api/routers/paper_trading.py` — filter None prices.
- `apps/tick_worker/main.py` — filter None prices.
- `conftest.py` — set `TEST_USE_MOCK=true` for full test session.
- `tests/unit/test_providers.py` — full rewrite, 10 tests covering policy.

Frontend
- `apps/web/types/generated/api.ts` — LivePrice nullable price + verified
  + status + error; DqsStatus; SnapshotMode; DataSnapshot.mode.
- `apps/web/components/panels/MarketDataPanel` — "VERİ YOK" badge,
  MOCK/unverified chips.
- `apps/web/components/panels/DataQualityPanel` — DQS status badge,
  BLOCKED footer message.
- `apps/web/components/panels/ProviderStatusPanel` — error mesajı satırı.
- `apps/web/components/panels/SystemHealthBar` — DQS status chip.
- `apps/web/components/shell/MockModeBanner.tsx` (new) — red banner when
  runtime opt-in active.
- `apps/web/app/page.tsx` — banner placement.

Docs / tasks
- `docs/DATA_POLICY.md` (new).
- `docs/SAFETY_RULES.md` — link to policy.
- `docs/CURRENT_STATE.md` — G1.1 done.
- `.tasks/CHANGELOG_AGENT.md` — entry.

## Tests run

- `pytest -q` → 18/18 passed (10 new policy tests + 8 prior).
- `ruff check packages apps/api apps/tick_worker apps/learning_worker`
  → All checks passed.

## Result

passed

## Notes

- PAPER_SAFE / NO_EXECUTION preserved. Risk gate KILL_SWITCH (DQS < 55)
  automatically covers BLOCKED status; no separate kill switch added.
- decide_for_symbol / risk thresholds intact.
- Test fixture (`TEST_USE_MOCK=true`) is **explicit** in conftest; tests
  that need live-only behavior disable it via `monkeypatch.delenv`.
- Lokal `node`/`pnpm` yok → `next build` CI'da doğrulanacak.

## Next

- G2 — auto-weight trainer.
