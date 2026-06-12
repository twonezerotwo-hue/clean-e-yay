# NEXT TASK — v2.7 deep data, kalan slice'lar (öneri)

v2.7 **D2 — Crypto Derivatives**, **D4 — Realized Volatility** ve **D5 — Real News
Feed + Catalyst Half-Life** tamamlandı (bkz. `.tasks/TASK_RESULT.md`, 2026-06-12).
Üçü de karar zincirine **yalnızca kısıtlayıcı** girer; live smoke OK, CI-scope
yeşil. 287/287 pytest.

Kalan deep-data slice'ları (her biri **önce karar rolü** tasarlanıp sonra provider
eklenir — engine rolü olmadan ölü veri yasak; DATA_POLICY + ARCHITECTURE §18):

## Öneri: D3 — Options IV / skew (Deribit)
- Deribit public API → ATM implied vol + 25Δ skew (BTC/ETH).
- Karar rolü: yüksek IV → regime/risk **size kısıtı** (≤1.0, asla artırmaz);
  skew → contrarian bağlam. Yalnızca kısıtlayıcı, RiskGate'i bypass etmez.
- DQS + freshness + DEGRADED fallback (mock yok). Dashboard görünürlüğü
  (VolatilityPanel'e ek IV satırı veya yeni panel) + matrix etkisi.
- Not: D4 realized vol ile birlikte "vol surface" bağlamı tamamlanır
  (realized vs implied spread → bağlam).

## Açık teknik borç (opsiyonel)
- Gerçek `openapi-typescript` codegen otomasyonu (`make codegen`); şu an drift
  guard testi manuel sync'i koruyor.
- Gerçek deterministik replay/backtest motoru (disk snapshot store gerektirir).

## Hard rules (değişmez)
- PAPER_SAFE / NO_EXECUTION; broker yok, gerçek emir yok, live execution yok.
- RiskGate/DQS/KillSwitch/halt yalnızca kısıtlayıcı; bypass/gevşetme yok.
- LLM karar vermez. Endpoint path + response alan adları sabit (additive ok).
- Runtime'da mock yok; testlerde live network yok.
- Yeni state → dashboard'da minimum görünürlük (selector + registry; page.tsx
  büyümez). 3D/R3F/Framer Motion ruhu korunur.
