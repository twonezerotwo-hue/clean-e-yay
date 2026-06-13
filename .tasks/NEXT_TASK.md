# NEXT TASK — seç (UX4 sonrası)

**UX4 — Live Feedback Polish** tamamlandı (bkz. `.tasks/TASK_RESULT.md` +
`docs/CURRENT_STATE.md`): market-structure 3 panel impact-first ("karar etkisi" üstte,
sayılar altta, duplicate rozet kaldırıldı), TimeframeMatrix banner top-3 + tek gate
banner, News ilk-6 + collapsed, Catalyst expired/context-only muted + aktif vurgu,
AgentBrief hard-stop ⛔ banner. Copy/Learning zaten temizdi. Frontend-only; backend
SIFIR diff. tsc/build temiz, SSR 200 + collapsed expert + PAPER_ONLY + HeroScene.
Commit: `feat(web): polish live dashboard readability`.

A1 + DEP1 + UX2 + REL1 + UX3 + UX4 bitti. **Backend FREEZE** — yalnızca P0 hotfix.
Aşağıdaki üç yönden biri seçilir:

## Seçenek A — Production dry-run / long-running soak test (önerilen)
`make prod-up` ile saatlerce/günlerce çalıştır, `prod-status` + `/system/health` ile
heartbeat/stale/warnings izle, tick cycle + snapshot ring-buffer + learning scheduled
+ paper lifecycle akışını gözle. Gözlem + dokümantasyon ağırlıklı; backend FREEZE.
UX1–UX4 cilası bitti; gerçek soak çıktısı bir sonraki UX dalgasının girdisi olur.

## Seçenek B — UX5 after real user feedback
Soak/gerçek oturumdan somut geri bildirim topla, sonra hedefli cila yap: panel
görünürlük tercih kalıcılığı (localStorage; backend state değil), simple bölümlerde
yoğunluk (AIReport compact mod), boş/yükleniyor/hata tutarlılığı, mobil/tablet
kırılma, kontrast/erişilebilirlik. Frontend-only; backend SIFIR diff; openapi/TS
şeması değişmez. Spekülatif değil — yalnızca gözlemlenen sorun varsa.

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
- Frontend: `cd apps/web && pnpm tsc --noEmit && pnpm build` + SSR smoke (`make smoke`
  veya izole port).
- Devops: `bash -n scripts/*.sh` + `make prod-up`/`prod-status`/`prod-smoke`/`prod-down`.
- Backend dokunulursa (yalnızca P0): `pytest -q` (izole runtime path env'leri) +
  `ruff check packages apps/api apps/tick_worker apps/learning_worker tests/contract`
  + codegen/contract drift.
