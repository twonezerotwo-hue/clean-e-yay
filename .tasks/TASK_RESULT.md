# TASK RESULT

Date: 2026-06-12
Task: T1 — OHLCV provider + gerçek multi-timeframe technicals
Status: completed

## Ne yapıldı

Hash-mock teknik sinyal üretimi kaldırıldı; 15m/1h/4h/1d/1w teknik
snapshot'lar artık gerçek OHLCV barlarından hesaplanıyor.

### Backend

- `packages/data/types.py` — `OHLCVBar` modeli (symbol, timeframe, ts,
  o/h/l/c, volume, source, verified). `TechnicalSnapshot`'a additive
  alanlar: `status` (OK/DEGRADED), `source`, `bars_used`; `macd` alanı
  artık MACD(12/26/9) histogramının fiyata normalize hali
  (hist/close×100 — semboller arası karşılaştırılabilir).
- `packages/data/providers/ohlcv/` (yeni):
  - `coingecko.py` — market_chart adapter (BTC/ETH). 15m=days:1 (5dk
    nokta → 15m resample), 1h=days:90, 1d=days:365. Volume=None
    (CoinGecko total_volumes 24sa kayan toplam — bar hacmi değil).
  - `yfinance.py` — Yahoo chart adapter (XAU/XAG/DXY/VIX/BRENT/SP500/QQQ).
    Native 15m(1mo)/1h(1y)/1d(2y)/1wk(5y); per-bar volume var.
  - `resample.py` — **4h = 1h barlarından epoch bucket** (her iki kaynak),
    **1w = kripto için 1d barlarından ISO hafta** (Pazartesi 00:00 UTC);
    yfinance 1w native. Resample edilen barlar `source="resampled:<base>"`.
  - `cache.py` — disk cache `data/runtime/ohlcv/` (env `OHLCV_CACHE_DIR`);
    TTL TF'e orantılı: 15m→5dk, 1h→15dk, 4h→30dk, 1d→6sa, 1w→24sa.
    Live fetch başarısızsa stale cache servis edilir (gerçek ama eski
    veri; freshness kuralı DEGRADED işaretler) — mock'a asla düşülmez.
  - `fixtures.py` — deterministik sinüs+trend barları; YALNIZCA
    TEST_USE_MOCK / OHLCV_USE_FIXTURE path'inde (runtime'da asla).
  - `__init__.py` — orchestrator + provider_status (`ohlcv_coingecko`,
    `ohlcv_yfinance`; stale-cache kullanımı fallback sayacına işlenir).
- `packages/data/providers/technical/` — gerçek indikatörler:
  - `indicators.py` — RSI(14) Wilder, MACD(12/26/9), ATR(14) Wilder,
    EMA serisi (SMA seed). Yetersiz bar → None (uydurma değer yok).
  - `__init__.py` — `compute_snapshot` (saf hesap) + `get_snapshot`.
    EMA stack 20/50/200 (200 bar yoksa None). Score: 50 + (RSI−50)×0.6 +
    clamp(macd_norm,±3)×5; indikatör yoksa nötr 50.
  - **TF bazlı freshness**: son bar eskiyse DEGRADED — 15m>30dk, 1h>2sa,
    4h>8sa, 1d>48sa, 1w>10g.
- `packages/data/ingestion/pipeline.py` — `technicals_by_tf` dolduruldu
  (5 TF × `MULTI_TF_SYMBOLS` = DEFAULT_SYMBOLS[:4]); legacy `technicals`
  1d snapshot'ın kendisinden beslenir (geriye uyum). DEGRADED TF'ler
  snapshot warnings'e yazılır; ohlcv provider_status merge edilir.
- `apps/api/routers/data.py` — `/data/snapshot` cevabına additive
  `technicals_by_tf` bloğu.
- `contracts/openapi.yaml` — additive `OHLCVBar`, `TechnicalSnapshotTF`.

### Frontend (minimum görünürlük — büyük panel yok, TimeframeMatrixPanel T2)

- `types/generated/api.ts` — `TechnicalTf`, `TechnicalStatus`,
  `DataSnapshot.technicals_by_tf?`.
- `lib/selectors/snapshot.ts` — `selectTechnicalsByTf`,
  `selectTfTechnicalsFor`, `selectTfCoverage`, `TF_ORDER` (frontend
  hesap yapmaz).
- `MarketDataPanel` — sembol altında TF chip satırı (skor; DEGRADED →
  "—" + amber; tooltip RSI/EMA/source).
- `SnapshotPanel` — "TF teknikleri x/y OK" kapsama satırı.
- page.tsx / panel-registry değişmedi (mevcut panellere alan eklendi).

## Güvenlik / kapsam garantileri

- PAPER_SAFE / NO_EXECUTION korunuyor — broker/emir/live execution yok.
- RiskGate / DQS veto / KillSwitch / halt davranışı sıfır diff; global
  DQS hesabı (fiyat bazlı) değişmedi. TF freshness yalnızca
  TechnicalSnapshot.status + snapshot warnings'e işler.
- Consensus/decision multi-TF OKUMUYOR (T2'de); legacy `technicals`
  (1d) ile aynı akış sürüyor.
- Runtime'da mock/fixture bar yok: live fail → stale cache → boş liste
  → indicator None + DEGRADED (testli).
- T0 testi `test_market_snapshot_technicals_by_tf_default_none` T1
  davranışına güncellendi (artık dolu olduğunu doğruluyor) — tek bilinçli
  test değişikliği.

## Tests run

- `pytest -q` → **113/113 passed** (19 yeni T1 testi:
  test_ohlcv_technicals.py — indikatör doğruluğu, resample 4h/1w,
  yetersiz bar → None/DEGRADED, TF stale kuralı, pipeline 5 TF doldurma,
  legacy 1d aynılığı, cache TTL + stale fallback, runtime fixture yasağı,
  endpoint technicals_by_tf). Live network yok.
- `ruff check packages apps/api apps/tick_worker apps/learning_worker`
  → yeşil.
- `pnpm exec tsc --noEmit` + `pnpm build` → yeşil.

## Result

passed

## Next

- T2 — timeframe consensus + decision + paper (time-stop) +
  TimeframeMatrixPanel (`.tasks/NEXT_TASK.md` hazır).
