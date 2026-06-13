# NEXT TASK — A1 Final Backend Architecture Audit

**O1 — 7/24 Worker Reliability** tamamlandı (bkz. `.tasks/TASK_RESULT.md` +
`docs/CURRENT_STATE.md`): worker heartbeat store (`packages/ops/heartbeat.py`),
system health ViewModel (`packages/ops/system_health.py`), `GET /api/v1/system/health`,
tick/learning worker heartbeat + stale tespiti + crash raporlama, SystemHealthBar
additive. **419 pytest**, ruff CI-scope + tsc + pnpm build yeşil, live smoke OK.
Commit: `feat(ops): add worker reliability health`.

P1 (paper lifecycle) + L1 (learning loop) + O1 (worker reliability) bitti.
Backend bitirme modu — **yeni veri kaynağı / dashboard redesign / intelligence /
trading logic EKLENMEZ.**

## A1 — Final Backend Architecture Audit

Uçtan uca tutarlılık denetimi (yeni veri/feature YOK; mümkünse sıfır runtime diff):

1. **Ölü kod / kullanılmayan export taraması**: `packages/**`, `apps/**` içinde
   kullanılmayan fonksiyon/şema/`__all__` üyesi; orphan modül.
2. **Sözleşme drift**: openapi ↔ runtime route ↔ TS api.ts tam senkron
   (contract + codegen drift testleri zaten var — boşluk kalmış mı kontrol et).
   Documented GET endpoint'lerin hepsi şemaya uyuyor mu; path drift guard tam mı.
3. **Endpoint/alan sabitliği**: response alan adları + path'ler değişmedi (additive
   geçmişi korunuyor) — kırılgan noktaları raporla.
4. **PAPER_SAFE/NO_EXECUTION sınır denetimi**: her katmanda (decision/risk/paper/
   learning/ops) broker yok · gerçek emir yok · live execution yok · RiskGate/DQS/
   KillSwitch/halt yalnızca kısıtlayıcı, bypass yok · LLM karar vermez. Bypass
   yüzeyi var mı?
5. **Test kapsama boşlukları raporu**: hangi modüller/edge-case'ler test dışı;
   kritik olanlara minimal test ekle.
6. **Runtime mock / look-ahead / sahte geçmiş** taraması (DATA_POLICY ihlali var mı).

Çıktı: kısa **audit raporu** (bulgular + risk seviyesi) + küçük, güvenli düzeltmeler
(varsa). Büyük refactor YOK — bitirme/sağlamlaştırma modu.

## Hard rules (değişmez)
- PAPER_SAFE / NO_EXECUTION; broker yok, gerçek emir yok, live execution yok.
- RiskGate / DQS / KillSwitch / halt yalnızca kısıtlayıcı; bypass/gevşetme yok.
- LLM karar vermez. Endpoint path + response alan adları sabit (additive ok).
- Runtime'da mock yok; testlerde live network yok. Look-ahead / sahte geçmiş yok.

## Validation
- `pytest -q` (narrow → full). **NOT**: runtime state'i izole et —
  `RISK_HALT_PATH` / `PAPER_STATE_PATH` / `PAPER_AUDIT_PATH` / `SNAPSHOT_STORE_PATH` /
  `LEARNING_RUN_PATH` / `LEARNING_OUT_PATH` / `WORKER_HEARTBEAT_PATH` temp dizine al;
  aksi halde önceki live-smoke artığı (aktif halt) `test_event_risk` testlerini
  kırar. CI'da fresh checkout olduğu için bu sorun yaşanmaz.
- ruff CI scope: `ruff check packages apps/api apps/tick_worker apps/learning_worker tests/contract`
- `cd apps/web && pnpm tsc --noEmit && pnpm build`
- codegen/contract drift yeşil
