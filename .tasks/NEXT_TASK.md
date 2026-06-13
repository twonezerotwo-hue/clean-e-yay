# NEXT TASK — UX1 Agent Operating Cockpit veya R2 rolling replay runner (öneri)

**R1 — Real Snapshot Replay Foundation** tamamlandı (bkz. `.tasks/TASK_RESULT.md`):
disk snapshot store (`packages/data/snapshot_store.py`, atomik + corruption-safe),
tick_worker producer, `/replay/status` + `/replay/{id}` + `/replay/{id}/decision-trace`
endpoint'leri gerçek store'dan okur (live refetch yok), ReplayStatusPanel store
durumunu gösterir. Sahte backtest YOK. **349/349 pytest**, CI-scope yeşil, live smoke OK.

> Replay foundation GERÇEKTEN çalışıyor (store + endpoint + panel + producer). Yeni
> veri kaynağı önermeden önce: foundation hazır — sıradaki iş onu kullanmak/cilalamak.

Sıradaki adaylar (her biri **önce karar rolü** tasarlanır — ölü veri yasak;
DATA_POLICY + ARCHITECTURE §18):

## Öneri A: UX1 — Agent Operating Cockpit
- Mevcut paneller + replay/decision-trace'i tek "operating cockpit" akışında
  birleştir: snapshot seç → decision-trace incele → blocked_by/risk gate kanıt
  zinciri. Yeni veri/intelligence YOK; mevcut state'in operatör UX'i.
- page.tsx büyümez; selector + mevcut panel pattern; 3D/R3F ruhu korunur.

## Öneri B: R2 — Deterministic rolling replay / backtest runner
- Stored snapshot serisi üzerinde deterministik yeniden-üretim + karar **drift
  tespiti** (kayıtlı karar vs yeniden hesaplanan karar). PAPER/REPLAY_ONLY,
  yeni live veri YOK, sahte performans YOK.
- Snapshot store zaten var; runner store'u okur, decide_matrix'i stored snapshot'a
  uygular, farkı raporlar (RiskGate/DQS bypass yok).

## Açık teknik borç (opsiyonel)
- Gerçek `openapi-typescript` codegen otomasyonu (`make codegen`); şu an drift
  guard testi manuel sync'i koruyor.
- snapshot_store `count()` bozuk dosyaları da sayar (latest=None ile sinyallenir);
  istenirse readable-only count'a çevrilebilir.

## Hard rules (değişmez)
- PAPER_SAFE / NO_EXECUTION; broker yok, gerçek emir yok, live execution yok.
- Replay emir/karar üretmez, paper açmaz, RiskGate'i bypass etmez, live çağırmaz.
- RiskGate/DQS/KillSwitch/halt yalnızca kısıtlayıcı; bypass/gevşetme yok.
- LLM karar vermez. Endpoint path + response alan adları sabit (additive ok).
- Runtime'da mock yok; testlerde live network yok.
- Yeni state → dashboard'da minimum görünürlük (selector + registry; page.tsx
  büyümez). 3D/R3F/Framer Motion ruhu korunur.
