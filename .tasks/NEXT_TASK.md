# NEXT TASK — T1 OHLCV Provider + Gerçek Multi-Timeframe Technicals

T0 contract'ları kodla doldur: gerçek mum verisi + gerçek indikatörler.
Mevcut hash-mock teknik sağlayıcı yerini OHLCV bazlı hesaba bırakır.

## Scope

- `packages/data/types.py` — `OHLCVBar` modeli (symbol, timeframe, o/h/l/c,
  volume, ts, source, verified).
- `packages/data/providers/ohlcv/` (yeni):
  - CoinGecko (BTC/ETH: günlük + saatlik OHLC), yfinance chart API
    (XAU/XAG/endeks: 15m/1h/1d/1wk) — mevcut provider error-handling +
    provider_status desenini izle.
  - 15m/1h/4h/1w: kaynak desteklemiyorsa üst/alt TF'ten **resample**
    (4h = 1h×4); resample edilen barlar `source: "resampled:<base>"`.
  - Disk cache (`data/runtime/ohlcv/`) — tekrar eden çağrıları azalt;
    cache TTL TF'e orantılı (15m→5dk, 1d→6sa).
- `packages/data/providers/technical/` — RSI(14), MACD(12/26/9), ATR(14),
  EMA stack (20/50/200) **gerçek OHLCV'den** hesapla; bar yetersizse
  `TechnicalSnapshot` alanları None + DEGRADED işareti (mock değer YOK —
  DATA_POLICY).
- `packages/data/ingestion/pipeline.py` — `technicals_by_tf` doldur
  (5 TF × DEFAULT_SYMBOLS[:4]); legacy `technicals` alanı 1d'den beslenmeye
  devam eder (geriye uyum). DQS: TF bazlı freshness kuralı (15m>30dk eski
  → DEGRADED; 1d>48sa → DEGRADED).
- Test offline: fixture OHLCV barlarıyla indikatör doğruluğu (bilinen
  seriye bilinen RSI), resample doğruluğu, bar yetersiz → None/DEGRADED,
  legacy `technicals` değişmedi, network yok (provider mock'lanır).

## Rules

- `PAPER_SAFE / NO_EXECUTION`; RiskGate/halt/DQS davranışı değişmez.
- Consensus/decision henüz multi-TF OKUMAZ (o T2) — bu görev sadece veri.
- Runtime'da mock bar yok; veri yoksa None + DEGRADED (DATA_POLICY).
- `technicals_by_tf` dolduğunda dashboard `SnapshotPanel`/`MarketDataPanel`
  içinde minimum görünürlük: TF başına teknik özet satırı (büyük panel yok
  — TimeframeMatrixPanel T2'de).
