# NEXT TASK — v2.7 deep data, kalan slice'lar (öneri)

v2.7 **D2 — Crypto Derivatives**, **D3 — Options IV/Skew**, **D4 — Realized
Volatility** ve **D5 — Real News Feed + Catalyst Half-Life** tamamlandı (bkz.
`.tasks/TASK_RESULT.md`). Dördü de karar zincirine **yalnızca kısıtlayıcı** girer;
live smoke OK, CI-scope yeşil. **323/323 pytest**. D3 ile vol surface bağlamı
(realized vs implied spread) tamamlandı.

Sıradaki adaylar (her biri **önce karar rolü** tasarlanıp sonra provider eklenir —
engine rolü olmadan ölü veri yasak; DATA_POLICY + ARCHITECTURE §18):

## Öneri A: Gerçek deterministik replay / backtest motoru
- Disk snapshot store (build_snapshot çıktısını dök) → kayıttan deterministik
  replay; `/replay/{snapshot_id}` şu an `reserved_not_active` döndürüyor.
- Karar rolü: geçmiş kararı yeniden üret + drift tespit; PAPER/REPLAY_ONLY,
  yeni live veri yok.

## Öneri B: v2.6 LLM persona derinleşme
- AIReportPanel persona bölümleri + ChatPanel mevcut; persona açıklama kalitesi /
  evidence bağı derinleştirilebilir. LLM yalnızca açıklar, karar vermez.

## Öneri C: Asset universe genişletme / kalan deep-data
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
