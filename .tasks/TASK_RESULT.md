# TASK RESULT

Date: 2026-06-11
Task: G1 — Real price providers + DQS visibility
Status: completed

## Files changed

Backend:
- `packages/data/providers/price/coingecko.py` (new)
- `packages/data/providers/price/yfinance.py` (new)
- `packages/data/providers/price/fred.py` (new)
- `packages/data/providers/price/__init__.py` (rewrite — orchestrator + status tracker)
- `packages/data/ingestion/pipeline.py` (provider_status field on MarketSnapshot)
- `apps/api/routers/data.py` (new — `/api/v1/data/snapshot`)
- `apps/api/main.py` (wire data router)
- `tests/unit/test_providers.py` (new — 4 tests)

Frontend:
- `apps/web/types/generated/api.ts` (DataSnapshot, ProviderStatus, DqsBreakdown, LivePrice types)
- `apps/web/lib/api/client.ts` (api.dataSnapshot)
- `apps/web/lib/queries/{keys,hooks}.ts` (useDataSnapshot)
- `apps/web/lib/selectors/snapshot.ts` (new)
- `apps/web/components/panels/DataQualityPanel/index.tsx` (new)
- `apps/web/components/panels/ProviderStatusPanel/index.tsx` (new)
- `apps/web/components/panels/SnapshotPanel/index.tsx` (new)
- `apps/web/components/panels/MarketDataPanel/index.tsx` (new)
- `apps/web/lib/panel-registry.ts` (4 new entries)
- `apps/web/app/page.tsx` (4 new GridCells, en üstte)

Docs:
- `docs/CURRENT_STATE.md` (G1 done, next = G2)
- `.tasks/NEXT_TASK.md` (G2'ye güncellenecek — finalize sonrası)
- `.tasks/CHANGELOG_AGENT.md` (G1 entry)

## Tests run

- `pytest -q` → 12/12 passed (4 yeni provider/snapshot testi)
- `ruff check packages apps/api apps/tick_worker apps/learning_worker` → All checks passed

## Result

passed

## Notes

- Live provider'lar stdlib `urllib.request` ile yazıldı; ek Python dep yok.
- `PRICE_USE_MOCK=true` default → tests + CI offline kalıyor.
- FRED için `FRED_API_KEY` env değişkeni gerek; yoksa None → mock fallback.
- Lokal `node`/`pnpm` yok; `next build` doğrulaması CI'da yapılacak.
- Preview server eski projeye (`E_YAY CODEX`) bağlı olduğu için yerel
  browser verify yapılamadı.

## Next

- G2 — auto-weight trainer.
