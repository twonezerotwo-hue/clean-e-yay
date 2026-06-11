# Current State — Clean E-yAy

_Bu dosya kısa ve güncel tutulur. Her görev sonunda güncellenir._

## Last known status

- Backend endpoints çalışıyor; **G1 tamamlandı**: gerçek price provider'lar
  (CoinGecko, yfinance, FRED) + orchestrator + provider status tracker +
  mock fallback davranışı.
- Yeni endpoint: `GET /api/v1/data/snapshot` — prices, DQS breakdown,
  provider status, snapshot meta.
- 4 yeni dashboard paneli bağlı: DataQualityPanel, ProviderStatusPanel,
  SnapshotPanel, MarketDataPanel (panel-registry + page.tsx).
- `PRICE_USE_MOCK=true` default (tests offline kalır). `PRICE_USE_MOCK=false`
  ile live denenir, hata → mock fallback + `fallback_used=true`.
- Pytest: **12/12** yeşil (4 yeni provider/snapshot testi).
- Ruff (CI scope): yeşil.
- Web build: CI'da doğrulanacak (lokalde node yok).

## Next task

- **G2** — auto-weight trainer (bkz. `docs/ROADMAP.md`)
- `NEXT_TASK.md` G2 için güncellenmelidir.
