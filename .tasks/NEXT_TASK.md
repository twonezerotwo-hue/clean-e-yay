# NEXT TASK — T2 Timeframe Consensus + Decision + Paper (time-stop) + TimeframeMatrixPanel

T1'in doldurduğu `technicals_by_tf`'i karar katmanına bağla: sinyal uzayı
(symbol, timeframe) çifti olur. Risk kapsamı GLOBAL kalır.

## Scope

- `packages/consensus` — TF-aware consensus: `build(symbol, snap, regime,
  timeframe="1d")`; touche modülü `technicals_by_tf[symbol][tf]`'ten okur
  (yoksa legacy 1d fallback). DEGRADED teknik → o TF'te touche nötr (50)
  + uyarı.
- `packages/decision/engine.py` — `decide_matrix(symbols, snap, risk_in,
  open_positions)`: her (symbol, tf) için TradeDecision; OpenAPI'deki
  `TimeframeDecision`/`DecisionMatrix` şemalarını doldur.
  - `thresholds.timeframe_risk` ÇARPANLARI uygula (≤1.0, sadece
    küçültür): 15m ×0.25, 1h ×0.5, 4h/1d ×1.0.
  - **1w `paper_execution: false`** → asla open kararı üretmez; yalnızca
    bias/filtre (üst TF veto: 1w bearish ise alt TF long'ları scale-down
    veya WATCH — asla scale-up).
  - Fingerprint v2'ye gerçek TF segmenti geçir (artık default "1d" değil).
- `packages/paper` — TF bazlı **time-stop**: `thresholds.timeframe_risk.
  time_stop_hours` dolan pozisyon TIME_STOP_EXIT ile kapanır (tick
  yolunda); `Position.timeframe` artık açılışta gerçek TF taşır.
- `apps/api` — `GET /api/v1/decision/matrix` endpoint'i (DecisionMatrix
  döner); paper tick TF'li kararlarla çalışır.
- Frontend — **TimeframeMatrixPanel**: symbol × TF grid (skor/aksiyon/
  DEGRADED işareti), selector + panel-registry girişi + tek GridCell;
  page.tsx büyütülmez. TradingPanel pozisyon satırına TF rozeti.

## Rules

- `PAPER_SAFE / NO_EXECUTION`; RiskGate / DQS veto / KillSwitch / halt
  **global** kalır — halt aktifse 5 TF'in 5'inde de trade yok; hiçbir TF
  RiskGate'i bypass edemez/gevşetemez.
- timeframe_risk çarpanları yalnızca azaltır; scale-up yok.
- DEGRADED/None teknik olan TF'te yeni pozisyon açılmaz (WATCH/hold).
- Legacy davranış: decide_all (1d) çalışmaya devam eder; mevcut endpoint
  path/alan isimleri değişmez (matrix additive).

## Tests

- (symbol, tf) kararlarında risk çarpanı uygulanıyor (15m size ×0.25).
- 1w hiçbir koşulda open üretmiyor; 1w bearish → alt TF veto/scale-down.
- KILL_SWITCH/halt aktifken tüm TF'lerde blocked.
- DEGRADED TF → open yok.
- Time-stop: süresi dolan pozisyon TIME_STOP_EXIT ile kapanıyor.
- Fingerprint v2 gerçek TF segmenti taşıyor; legacy lookup kırılmıyor.
- pytest + ruff + tsc + build yeşil; live network yok (fixture barlar).
