# NEXT TASK — O1 7/24 Worker Reliability (veya A1 Final Architecture Audit)

**L1 — Learning Loop Finalization** tamamlandı (bkz. `.tasks/TASK_RESULT.md` +
`docs/CURRENT_STATE.md`): dominant_module v2 bug fix, canonical outcome record
(`packages/learning/outcomes.py`), timeframe-aware summary (15m outcome 1d
bucket'ını etkilemez), auto-weight trainer verified-only + owner-approval +
timeframe/regime/module evidence, learning worker run metadata
(`packages/learning/run_store.py`), API/dashboard additive. **407 pytest**, ruff
CI-scope + tsc + pnpm build yeşil, live smoke OK. Commit:
`feat(learning): finalize outcome learning loop`.

P1 (paper lifecycle) ve L1 (learning loop) bitti. Backend bitirme modu — **yeni
veri kaynağı / dashboard redesign / trading logic EKLENMEZ.**

## Aday görevler (görev başında biri seçilir)

### O1 — 7/24 worker reliability
tick_worker + learning_worker'ın kesintisiz, gözlemlenebilir, hata-toleranslı
çalışması. Yeni feature YOK — yalnızca dayanıklılık:
- Loop sağlığı: tek tick/run hatası loop'u öldürmez (backoff + log + sayaç).
- Heartbeat / last_run gözlenebilirliği (learning_worker run_store paterni;
  tick_worker için benzer son-tick metadata).
- Graceful shutdown / yeniden başlatma; çökme sonrası state robustness (P1 atomik
  state + audit zaten var).
- Tekrarlı hata → görünür DEGRADED durumu (yeni endpoint değil, mevcut yüzeyler).

### A1 — Final backend architecture audit
Uçtan uca tutarlılık denetimi (yeni veri/feature yok):
- Ölü kod / kullanılmayan export / sözleşme-runtime drift taraması.
- Endpoint path + response alan adları sabitliği; openapi↔runtime↔TS tam senkron.
- PAPER_SAFE/NO_EXECUTION sınırlarının her katmanda korunduğunun doğrulanması.
- Test kapsama boşlukları raporu.

## Hard rules (değişmez)
- PAPER_SAFE / NO_EXECUTION; broker yok, gerçek emir yok, live execution yok.
- RiskGate / DQS / KillSwitch / halt yalnızca kısıtlayıcı; bypass/gevşetme yok.
- LLM karar vermez. Endpoint path + response alan adları sabit (additive ok).
- Runtime'da mock yok; testlerde live network yok.
- Learning active weights owner approval olmadan değişmez.

## Validation
- `pytest -q` (narrow → full). **NOT**: runtime state'i izole et —
  `RISK_HALT_PATH` / `PAPER_STATE_PATH` / `PAPER_AUDIT_PATH` /
  `SNAPSHOT_STORE_PATH` / `LEARNING_RUN_PATH` / `LEARNING_OUT_PATH` temp dizine
  al; aksi halde önceki live-smoke artığı (aktif halt) `test_event_risk` testlerini
  kırar. CI'da fresh checkout olduğu için bu sorun yaşanmaz.
- ruff CI scope: `ruff check packages apps/api apps/tick_worker apps/learning_worker tests/contract`
- `cd apps/web && pnpm tsc --noEmit && pnpm build`
- codegen/contract drift yeşil
