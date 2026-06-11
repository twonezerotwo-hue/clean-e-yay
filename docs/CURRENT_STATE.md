# Current State — Clean E-yAy

_Bu dosya kısa ve güncel tutulur. Her görev sonunda güncellenir._

## Last known status

- **Data policy uygulandı** ([DATA_POLICY.md](DATA_POLICY.md)): runtime'da
  mock fallback yasak. Live provider başarısız → `price=null`,
  `status="DATA_UNAVAILABLE"`, `verified=false`, `error=<sebep>`.
- `PRICE_USE_MOCK` default `false`. Test'ler `TEST_USE_MOCK=true` (conftest
  ile) altında mock alır; runtime opt-in `PRICE_USE_MOCK=true` dashboard'da
  kırmızı banner gösterir.
- DQS `status` alanı: `OK / DEGRADED / BLOCKED`. BLOCKED → risk gate
  KILL_SWITCH → yeni paper trade yok.
- Yeni endpoint: `GET /api/v1/data/snapshot` — `prices[].price` nullable;
  her quote `verified/status/error`; `mode.{mock_mode,mock_warning,test_mock}`
  alanları.
- Frontend: MarketDataPanel "VERİ YOK" gösterir, DataQualityPanel BLOCKED
  banner'lı, ProviderStatusPanel hata mesajı satırı, SystemHealthBar DQS
  status chip'i, MockModeBanner page üstünde.
- Paper tick consumer'ları None fiyatları filtreler; mock fiyatla işlem
  açılmaz.
- Pytest: **18/18** yeşil (runtime-fail, FRED missing key, paper tick
  no-open dahil).
- Ruff (CI scope): yeşil.
- Web build: CI'da doğrulanacak.

## Next task

- **G2** — auto-weight trainer (bkz. `docs/ROADMAP.md`).
- `.tasks/NEXT_TASK.md` G2 tanımı hazır.
