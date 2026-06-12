# TASK RESULT

Date: 2026-06-12
Task: v2.7 D4 — Realized Volatility / Volatility Regime Intelligence
Status: completed

## Prensip

Yeni veri yüzeyi (realized volatility / vol rejimi) karar zincirine **yalnızca
kısıtlayıcı** girer. ASLA size artırmaz; ASLA RiskGate/DQS/KillSwitch/halt'ı
bypass etmez. Ekstra ağ YOK — mevcut OHLCV cache'inden hesaplanır. Runtime'da
mock yok; bar yetersiz → DEGRADED (`insufficient_bars`). Fixture barlar
`verified=false` damgalı ve karar zincirine girmez (yalnızca dashboard bağlamı).
PAPER_SAFE / NO_EXECUTION.

## Ne yapıldı

### 1. Data layer (`packages/data/providers/volatility/`)
- `engine.py`: saf-python, ağsız. Log-getiri tabanlı annualize realized vol
  (short/medium/long pencere, TF'e göre annualizasyon), rv_short z-skoru (kendi
  rolling geçmişine göre), rejim (LOW/NORMAL/ELEVATED/EXTREME), squeeze/expansion/
  shock bayrağı (rv_short/rv_long oranı + son-bar |log-getiri| sigma). Yetersiz
  bar → DEGRADED. Tazelik → DQS.
- `__init__.py`: orchestrator — barları mevcut OHLCV cache'inden okur (ekstra ağ
  yok); symbol → timeframe grid; provider_status; verified = !fixture_mode.

### 2. Risk gate (`packages/risk/volatility_risk.py`)
- `assess()`: yalnızca `verified=True`+`status=OK`. EXTREME→NO_POSITION_INCREASE
  (block); ELEVATED→CAUTION ×0.5; LOW→WATCH (LOW+squeeze breakout = yalnızca
  bağlam, boost YOK); shock→en az CAUTION (rejim ELEVATED/EXTREME ise block);
  expansion/squeeze→WATCH. Yön bağımsız (yüksek vol her yönde riskli).
  size_factor ≤ 1.0 garanti.
- `timeframe_weight()`/`apply_timeframe()`: 15m/1h tam etki (vol shock daha
  etkili), 1d düşük ağırlık → block CAUTION'a yumuşar (rejim bağlamı), 1w off.

### 3. Entegrasyon
- `pipeline.py`: `MarketSnapshot.volatility` (symbol→tf; multi-TF teknik
  sembolleri × tüm TF); DEGRADED → warning; provider_status birleştirildi.
- `decision/engine.py`: volatility gate RiskGate hard gate'lerinden **SONRA**,
  yalnızca açılış adayına (`volatility_report` + blocked_by). matrix banner için
  `volatility` özeti (yalnızca OK + dikkat çeken hücreler).
- `config/thresholds_v1.0.yaml`: `volatility` eşikleri (pencereler, regime_z,
  squeeze/expansion/shock oranları, max_age, timeframe_weight).
- `apps/api/routers/data.py`: `/data/snapshot` `volatility` alanını döner.

### 4. Sözleşme + tipler (additive)
- `contracts/openapi.yaml`: `VolatilitySnapshot` + `VolatilitySummary` +
  `VolatilityRegime`/`VolState` enum; DataSnapshot.volatility + DecisionMatrix.
  volatility. `apps/web/types/generated/api.ts` el-senkron. Codegen drift +
  OpenAPI contract testleri yeşil.

### 5. Frontend (selector + panel-registry; page.tsx → 1 GridCell)
- `VolatilityPanel`: symbol × TF realized vol + z-skoru + rejim + squeeze/
  expansion/shock + status + freshness + karar etkisi rozeti + doğrulanmamış/
  DEGRADED durumları.
- `TimeframeMatrixPanel`: vol rejim banner + hücre `blocked_by` rozeti
  ("VOLATİLİTE"). Selector: `selectVolatility`, `selectMatrixVolatility`.

### 6. Testler (`tests/unit/test_volatility.py`, 28 yeni)
- engine: insufficient→DEGRADED, OK alan tamlığı, determinism, recent-burst→
  EXTREME, squeeze, shock.
- orchestrator: symbol×tf grid, fixture unverified, no-bars→DEGRADED, no-network.
- gate taksonomi (EXTREME block / ELEVATED CAUTION / LOW+squeeze WATCH-no-boost /
  shock / never boost) + timeframe ağırlığı (1w off / 1d softens / 1.0 keeps).
- decide_matrix uçtan uca: verified EXTREME → hücre durur; ELEVATED → size küçülür
  (açılış korunur); unverified → bloklamaz; **DQS BLOCKED & KILL_SWITCH her zaman
  final (volatilite bypass etmez)**.

## Sonuçlar
- **pytest: 266/266** (238 baseline + 28 D4). Live network yok.
- ruff (CI scope: packages + apps/api + workers + tests/contract): temiz.
- `pnpm tsc --noEmit` + `pnpm build`: yeşil.
- Live smoke: API health/snapshot/matrix 200; `/data/snapshot` volatility alanı
  **gerçek OHLCV ile verified** (BTC 1d EXTREME/expansion z=2.53); `/decision/
  matrix` volatility banner 9 kayıt; web SSR 200, "Volatilite Rejimi" paneli +
  mevcut paneller bozulmadı; log temiz.

## PAPER_SAFE
- broker: yok · gerçek emir: yok · live execution: yok.
- RiskGate/DQS/KillSwitch/halt: sıfır diff, bypass yok.
- volatility: yalnızca kısıtlayıcı; asla size artırmaz; verified-only karar.
