# NEXT TASK — R2 rolling replay runner veya cockpit cilası (öneri)

**UX1 — Agent Operating Cockpit** tamamlandı (bkz. `.tasks/TASK_RESULT.md`):
backend ViewModel (`packages/decision/cockpit.py`) + `GET /api/v1/cockpit/brief`
(AgentBrief + DecisionTrace), tek ana engel (no "veya"), data_mode, watch/trigger
koşulları; yeni cockpit panelleri (AgentBrief üstte tek ana kart + DecisionTrace +
WatchConditions + PaperAction) + Simple/Expert grouping (page.tsx `<details>`).
Mevcut paneller sadeleşti (matrix tek banner, paper time-stop EXPIRED, agent
evidence chain, candidate signals, learning insufficient sample). **366/366
pytest**, CI-scope ruff + tsc + pnpm build yeşil, live smoke OK. RiskGate/DQS/
KillSwitch/halt sıfır diff.

> Backend yeterince güçlü — **yeni veri kaynağı / intelligence module EKLENMEZ.**

Sıradaki adaylar (her biri **önce karar/kullanım rolü** tasarlanır — ölü veri
yasak; DATA_POLICY + ARCHITECTURE §18):

## Öneri A: R2 — Deterministic rolling replay / backtest runner
- Stored snapshot serisi (`packages/data/snapshot_store.py`) üzerinde
  deterministik yeniden-üretim + karar **drift tespiti** (kayıtlı karar vs
  yeniden hesaplanan). PAPER/REPLAY_ONLY, yeni live veri YOK, sahte performans YOK.
- Runner store'u okur, decide_matrix'i stored snapshot'a uygular, farkı raporlar
  (RiskGate/DQS bypass yok). Cockpit DecisionTrace ile aynı dilde rapor.

## Öneri B: Cockpit cilası (yeni veri yok — UX devamı)
- Panel drag-drop düzeni + görünürlük tercihi kalıcılığı (usePanelVisibility
  zaten var; Simple/Expert toggle butonu).
- AgentBrief'e küçük "son N tick" trend mini-göstergesi (stored snapshot'tan).

## Açık teknik borç (opsiyonel)
- Gerçek `openapi-typescript` codegen otomasyonu (`make codegen`); şu an drift
  guard testi manuel sync'i koruyor.

## Hard rules (değişmez)
- PAPER_SAFE / NO_EXECUTION; broker yok, gerçek emir yok, live execution yok.
- RiskGate/DQS/KillSwitch/halt yalnızca kısıtlayıcı; bypass/gevşetme yok.
- LLM karar vermez. Endpoint path + response alan adları sabit (additive ok).
- Runtime'da mock yok; testlerde live network yok.
- Yeni state → dashboard'da minimum görünürlük (selector + registry; page.tsx
  şişmez). 3D/R3F/Framer Motion ruhu + HeroScene + PAPER_ONLY korunur.
