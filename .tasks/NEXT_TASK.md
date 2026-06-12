# NEXT TASK — v2.7 deep data, D3+ slice (öneri)

v2.7 **D2 — Crypto Derivatives Intelligence tamamlandı** (bkz.
`.tasks/TASK_RESULT.md`, 2026-06-12): funding / OI / squeeze proxy provider +
yalnızca-kısıtlayıcı gate + decision/matrix entegrasyonu + openapi/TS + panel +
29 test. 238/238 pytest, CI-scope ruff + tsc + build yeşil, live smoke OK.

D1 (funding/OI) ROADMAP maddesi artık D2 ile karşılandı. Sıradaki deep-data
slice'ları (her biri **önce karar rolü** tasarlanıp sonra provider eklenir —
engine rolü olmadan ölü veri yasak; DATA_POLICY + ARCHITECTURE §18):

## Öneri: D3 — Options IV / skew (Deribit)
- Deribit public API → ATM implied vol + 25Δ skew (BTC/ETH).
- Karar rolü: yüksek IV → regime/risk **size kısıtı** (≤1.0, asla artırmaz);
  skew → contrarian bağlam. Yalnızca kısıtlayıcı, RiskGate'i bypass etmez.
- DQS + freshness + DEGRADED fallback (mock yok). Dashboard görünürlüğü
  (CryptoDerivativesPanel'e ek satır veya yeni VolPanel) + matrix etkisi.

## Alternatif: D4 — Realized volatility / ATR teyidi
- 1h/1d OHLCV'den realized vol → sizing/ATR teyidi (yalnızca kısıtlayıcı).
- Ekstra ağ yok (mevcut cache); en düşük riskli slice.

## Alternatif: D5 — Gerçek haber feed + T3 catalyst half-life
- RSS fixture/placeholder → gerçek feed; T0'daki `CatalystImpact` contract'ını
  gerçek yarı-ömür motoruyla doldur (haber decay → TF bias). Yalnızca kısıtlayıcı.

## Açık teknik borç (opsiyonel)
- Gerçek `openapi-typescript` codegen otomasyonu (`make codegen`); şu an drift
  guard testi manuel sync'i koruyor.
- Gerçek deterministik replay/backtest motoru (disk snapshot store gerektirir).
- D2 küçük: live Binance smoke (TEST_USE_MOCK kapalı) ile verified=true akışını
  bir kez gözlemle; gate'in gerçek HIGH squeeze'de açılışı kıstığını doğrula.

## Hard rules (değişmez)
- PAPER_SAFE / NO_EXECUTION; broker yok, gerçek emir yok, live execution yok.
- RiskGate/DQS/KillSwitch/halt yalnızca kısıtlayıcı; bypass/gevşetme yok.
- LLM karar vermez. Endpoint path + response alan adları sabit (additive ok).
- Runtime'da mock yok; testlerde live network yok.
- Yeni state → dashboard'da minimum görünürlük (selector + registry; page.tsx
  büyümez). 3D/R3F/Framer Motion ruhu korunur.
