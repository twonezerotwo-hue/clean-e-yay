# NEXT TASK — gerçek replay/backtest motoru veya kalan deep-data (öneri)

v2.7 **D2/D3/D4/D5** deep-data + **v2.6.1 LLM Persona deep-data derinleşme**
tamamlandı (bkz. `.tasks/TASK_RESULT.md`). Persona/chat/AI-report artık tüm karar
zinciri özetini (options/volatilite/türev/catalyst/rotation) state-grounded
açıklar; LLM hâlâ karar vermez. Tüm deep-data karar zincirine **yalnızca
kısıtlayıcı** girer; live smoke OK, CI-scope yeşil. **334/334 pytest**.

> Not: Öneri B (v2.6 LLM persona derinleşme) BU oturumda tamamlandı — listeden
> düşürüldü.

Sıradaki adaylar (her biri **önce karar rolü** tasarlanıp sonra provider eklenir —
engine rolü olmadan ölü veri yasak; DATA_POLICY + ARCHITECTURE §18):

## Öneri A: Gerçek deterministik replay / backtest motoru
- Disk snapshot store (build_snapshot çıktısını dök) → kayıttan deterministik
  replay; `/replay/{snapshot_id}` şu an `reserved_not_active` döndürüyor.
- Karar rolü: geçmiş kararı yeniden üret + drift tespit; PAPER/REPLAY_ONLY,
  yeni live veri yok.

## Öneri B: Asset universe genişletme / kalan deep-data
- Yeni sembol/asset sınıfı veya ek deep-data slice (önce karar rolü tasarımı).

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
