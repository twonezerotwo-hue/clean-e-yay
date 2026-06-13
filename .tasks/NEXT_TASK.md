# NEXT TASK — seç (UX3 sonrası)

**UX3 — Dashboard Information Architecture** tamamlandı (bkz. `.tasks/TASK_RESULT.md`
+ `docs/CURRENT_STATE.md`): simple 5 önem-sıralı bölüm + expert 5 grup (Data Quality
& Providers / Market Structure / Macro-Catalyst / Paper & Learning / Ops-System),
ortak `PanelGroup` helper, registry IA grupları. Frontend-only; backend SIFIR diff.
tsc/build temiz, SSR 200 + grup başlıkları + collapsed expert + PAPER_ONLY + HeroScene.
Commit: `feat(web): reorganize dashboard information architecture`.

A1 + DEP1 + UX2 + REL1 + UX3 bitti. **Backend FREEZE** — yalnızca P0 hotfix.
Aşağıdaki üç yönden biri seçilir:

## Seçenek A — UX4 live user feedback polish (önerilen)
Yeni IA hazır; gerçek oturumla cockpit'i izle ve son cilaları yap: panel görünürlük
tercih kalıcılığı (localStorage; backend state değil), simple bölümlerde aşırı
yükseklik/yoğunluk (örn. AIReport compact mod), boş/yükleniyor/hata tutarlılığı,
mobil/tablet kırılma, dark-neon kontrast/erişilebilirlik. Frontend-only; backend
SIFIR diff; openapi/TS şeması değişmez.

## Seçenek B — Production dry-run / long-running soak test
`make prod-up` ile saatlerce/günlerce çalıştır, `prod-status` + `/system/health` ile
heartbeat/stale/warnings izle, tick cycle + snapshot ring-buffer + learning scheduled
+ paper lifecycle akışını gözle. Gözlem + dokümantasyon ağırlıklı; backend FREEZE.

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
