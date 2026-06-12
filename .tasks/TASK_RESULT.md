# TASK RESULT

Date: 2026-06-12
Task: v2.7 D2 — Crypto Derivatives Intelligence (funding / OI / squeeze proxy)
Status: completed

## Prensip

Yeni veri yüzeyi (kripto türevleri) karar zincirine **yalnızca kısıtlayıcı**
girer. ASLA size artırmaz; ASLA RiskGate/DQS/KillSwitch/halt'ı bypass etmez.
`squeeze_proxy` GERÇEK liquidation API'si DEĞİLDİR — funding + OI değişimi +
momentum + volatiliteden türetilen bir vekildir (`is_proxy=true`). Runtime'da
mock yok; live başarısız → DEGRADED. Fixture verisi `verified=false` damgalı ve
karar zincirine girmez (yalnızca dashboard bağlamı). PAPER_SAFE / NO_EXECUTION.

## Ne yapıldı

### 1. Provider (yalnızca kripto: BTCUSD / ETHUSD)
- `packages/data/providers/derivatives/binance.py`: Binance USDⓈ-M public
  futures adapter — `premiumIndex` (funding) + `openInterestHist` (OI + Δ%).
  Anahtarsız, salt-okuma; hata/timeout → None (mock yok, crash yok).
- `engine.py`: deterministik squeeze proxy (0..100) — funding/OI/momentum/
  volatilite ağırlıklı; funding_bias + freshness + DQS. Essential alan yoksa
  DEGRADED.
- `fixtures.py`: offline test/dev verisi (`verified=false`).
- `__init__.py`: orchestrator — momentum/volatilite mevcut 1h OHLCV cache'inden
  (ekstra ağ yok); crypto-only filtre; provider_status; DEGRADED fallback.

### 2. Risk gate (`packages/risk/derivatives_risk.py`)
- `assess()`: yalnızca `verified=True` + `status=OK` snapshot sayılır. Squeeze
  HIGH → NO_POSITION_INCREASE (block); ELEVATED → CAUTION ×0.5; LOW → WATCH;
  funding-chase (aday yön kalabalıkla aynı) → CAUTION; contrarian → NONE (boost
  yok). size_factor ≤ 1.0 garanti.
- `timeframe_weight()` / `apply_timeframe()`: 15m/1h tam etki, 1d düşük ağırlık
  (block CAUTION'a yumuşar), 1w etki yok.

### 3. Entegrasyon
- `pipeline.py`: `MarketSnapshot.derivatives` (crypto-only); DEGRADED → warning;
  provider_status birleştirildi.
- `decision/engine.py`: derivatives gate RiskGate hard gate'lerinden **SONRA**,
  yalnızca açılış adayına uygulanır (`derivatives_report` + blocked_by). matrix
  banner için `derivatives` özeti.
- `config/thresholds_v1.0.yaml`: `derivatives` eşikleri + ağırlık + timeframe.
- `apps/api/routers/data.py`: `/data/snapshot` `derivatives` alanını döner.

### 4. Sözleşme + tipler (additive)
- `contracts/openapi.yaml`: `DerivativesSnapshot` + `DerivativesSummary` +
  `SqueezeLevel`/`FundingBias` enum; DataSnapshot.derivatives + DecisionMatrix.
  derivatives. `apps/web/types/generated/api.ts` el-senkron. Codegen drift +
  OpenAPI contract testleri yeşil.

### 5. Frontend (selector + panel-registry; page.tsx büyümedi → 1 GridCell)
- `CryptoDerivativesPanel`: BTC/ETH funding + OI + ΔOI + squeeze proxy/level +
  funding_bias + source + freshness + DQS + status + karar etkisi rozeti +
  doğrulanmamış/DEGRADED durumları. "gerçek liq değil" açıkça etiketli.
- `TimeframeMatrixPanel`: türev sıkışma banner'ı + hücre `blocked_by` rozeti
  ("TÜREV"). Selector: `selectDerivatives`, `selectMatrixDerivatives`.

### 6. Testler (`tests/unit/test_derivatives.py`, 29 yeni)
- engine parse + DEGRADED + squeeze/bias eşikleri + determinism.
- binance adapter parse (ağsız monkeypatch) + fail→None.
- orchestrator crypto-only + fixture unverified + provider-fail DEGRADED +
  no-network.
- gate taksonomi (HIGH block / ELEVATED CAUTION / chase / contrarian / never
  boost) + timeframe ağırlığı (1w off / 1d softens / 1.0 keeps block).
- decide_matrix uçtan uca: verified HIGH → hücre durur; CAUTION → size küçülür
  (açılış korunur); unverified → bloklamaz (yalnızca bağlam).

## Sonuçlar
- **pytest: 238/238** (209 baseline + 29 D2). Live network yok.
- ruff (CI scope: packages + apps/api + workers + tests/contract): temiz.
- `pnpm tsc --noEmit` + `pnpm build`: yeşil.
- Live smoke: API health/snapshot/matrix/dashboard 200; `/data/snapshot` ve
  `/decision/matrix` derivatives alanı dönüyor; web SSR 200, "Kripto Türevleri"
  paneli + mevcut paneller (Haberler/Rotasyon/Olay/Matris) bozulmadı; log temiz.

## PAPER_SAFE
- broker: yok · gerçek emir: yok · live execution: yok.
- RiskGate/DQS/KillSwitch/halt: sıfır diff, bypass yok.
- derivatives: yalnızca kısıtlayıcı; asla size artırmaz; verified-only karar.
