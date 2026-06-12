# NEXT TASK — v2.7 deep data (öneri) / asset universe 2. slice (alternatif)

OPS **tamamlandı** (bkz. `.tasks/TASK_RESULT.md`, 2026-06-12): contract testleri
(`tests/contract/`), codegen drift guard (CI'da fail eder), dürüst replay
foundation (`reserved_not_active`, sahte replay yok), OpenAPI↔runtime additive
reconciliation, dev reliability (LaunchAgent port çakışması dokümante).

Artık contract/codegen/replay/dev temeli sağlam → provider yüzeyini büyütmek
güvenli.

## Öneri: v2.7 — deep data (sıradaki ana faz)

ROADMAP'in bir sonraki ana adımı. **Kural (DATA_POLICY + ARCHITECTURE §18):**
her yeni veri için ÖNCE karar zincirindeki rolünü tasarla; engine rolü olmadan
provider'a ekleme (ölü veri yasak).

1. **Funding rate / OI** (Binance/Bybit) → RiskAgent/FlowAgent girdisi:
   aşırı funding = kalabalık pozisyon → yalnızca **kısıtlayıcı** CAUTION sinyali.
2. **Options IV / skew** (Deribit) → regime/risk: yüksek IV → size kısıtı (≤1.0).
3. **Realized vol** → sizing/ATR teyidi.
4. **Gerçek haber feed'i** (şu an RSS fixture/placeholder) → CatalystImpact motoru.
5. **T3 catalyst half-life motoru**: T0'da tanımlı `CatalystImpact` contract'ını
   gerçek motorla doldur (haber yarı-ömrü → TF bias decay). Yalnızca kısıtlayıcı.

Her biri için: provider + DQS + karar rolü + dashboard görünürlüğü birlikte;
RiskGate/DQS/KillSwitch/halt bypass YOK; testlerde live network YOK.

## Alternatif: asset universe — 2. slice

JNK/IWM/SMH/XLF/FXI + CoinGecko dominance + FRED HY spread/real yield/M2/PPI.
ÖNCE her veri için karar rolü (sektör genişliği / EM riski / kredi teyidi /
makro spread modülü) tasarla; sonra provider'a ekle.

## Hard rules (değişmez)

- PAPER_SAFE / NO_EXECUTION; broker yok, gerçek emir yok, live execution yok.
- RiskGate/DQS/KillSwitch/halt yalnızca kısıtlayıcı; bypass/gevşetme yok.
- LLM karar vermez. Endpoint path + response alan adları sabit (additive ok).
- Runtime'da mock yok; testlerde live network yok.
- Yeni state → dashboard'da minimum görünürlük (selector + registry; page.tsx büyümez).

## Açık teknik borç (opsiyonel, küçük)

- Gerçek `openapi-typescript` codegen otomasyonu (`make codegen`); şu an drift
  guard testi manuel sync'i koruyor.
- Gerçek deterministik replay/backtest motoru (disk snapshot store gerektirir).
