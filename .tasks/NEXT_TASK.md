# NEXT TASK — seç (REL1 sonrası)

**REL1 — Release Packaging / Local Production Runbook** tamamlandı (bkz.
`.tasks/TASK_RESULT.md` + `docs/CURRENT_STATE.md`): `scripts/prod_{up,down,status}.sh`
+ `_prod_common.sh`, Makefile `prod-*`, README "Local production runbook". Tek
komutla API+web+tick (background) + learning seed; port-conflict + eski LaunchAgent
tespiti. Devops/scripts/docs; backend SIFIR diff. Canlı lifecycle (izole 8060/3060):
prod_up→status→smoke(8/8)→down temiz. pytest 419/419, tsc/build temiz. Commit:
`chore(release): add local production runbook`.

A1 (RC audit) + DEP1 (deploy) + UX2 (polish) + REL1 (runbook) bitti. **Backend
FREEZE** — yalnızca P0 hotfix. Aşağıdaki üç yönden biri seçilir:

## Seçenek A — Production dry-run / long-running soak test (önerilen)
Runbook hazır; doğal sıradaki adım gerçek bir dayanıklılık koşusu: `make prod-up`
ile birkaç saat/gün çalıştır, `prod-status` + `/system/health` ile heartbeat/stale/
warnings izle, tick cycle sayısı artıyor mu, snapshot store büyüyor mu (ring-buffer
prune), learning scheduled çağrı, paper lifecycle EXPIRED_PENDING_PRICE akışı, halt
yok. **Gözlem + dokümantasyon** ağırlıklı; kod gerekiyorsa minimal (ölçüm/runbook).
Backend FREEZE korunur (yalnızca P0 çıkarsa hotfix).

## Seçenek B — UX3 live user feedback polish
Gerçek oturumla cockpit'i izle: ilk-bakış anlaşılırlığı, panel yoğunluğu, kopya
netliği, mobil/tablet, dark-neon kontrast. Frontend-only; backend SIFIR diff. Panel
görünürlük tercih kalıcılığı (localStorage) bu turda tamamlanabilir.

## Seçenek C — only P0 backend hotfix mode
Yeni iş açma; backend dondurulmuş RC. Yalnızca gerçek P0 bug → minimal + testli
hotfix. Opsiyonel: A1 P1 hardening (H1–H5) — 5 düşük-churn store atomik write,
schema_version, ARCHITECTURE.md çok-agent şemasını "vizyon" işaretle, gerçek
openapi-typescript codegen, `decide_all` test-only notu.

## Hard rules (her seçenekte)
- Backend FREEZE: packages/ + apps/api + worker SIFIR diff (P0 hotfix hariç).
- PAPER_SAFE / NO_EXECUTION; RiskGate/DQS/KillSwitch/halt dokunulmaz.
- Yeni data source / dashboard redesign / intelligence / trading logic YOK.
- Frontend hesap yapmaz; openapi/TS şeması değişmez (codegen drift yeşil kalır).

## Validation (değişen katmana göre)
- Devops/docs: `bash -n scripts/*.sh` + `make prod-up`/`prod-status`/`prod-smoke`/`prod-down`.
- Frontend: `cd apps/web && pnpm tsc --noEmit && pnpm build` + `make smoke`.
- Backend dokunulursa (yalnızca P0): `pytest -q` (izole runtime path env'leri) +
  `ruff check packages apps/api apps/tick_worker apps/learning_worker tests/contract`
  + codegen/contract drift.
