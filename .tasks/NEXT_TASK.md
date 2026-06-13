# NEXT TASK — UX2: Dashboard Polish / Usability Pass

**DEP1 — Deployment / DevOps Checklist** tamamlandı (bkz. `.tasks/TASK_RESULT.md` +
`docs/CURRENT_STATE.md`): `.env.example` doğru+tam, `scripts/smoke.sh` +
`scripts/workers.sh`, README "Deployment / 7-24 readiness" + PAPER_SAFE checklist.
Kod sıfır diff; pytest 419/419, canlı smoke 8/8 PASS. Commit:
`chore(devops): add deployment readiness checklist`.

A1 (RC audit) + DEP1 (deploy) bitti. **Backend FREEZE** — yalnızca P0 hotfix.

## UX2 — Dashboard Polish / Usability Pass (FRONTEND ONLY)

Amaç: cockpit'i son kullanım cilası. Sadece `apps/web/`; **backend SIFIR diff**
(yeni endpoint / response alanı / karar mantığı YOK). Frontend hesap YAPMAZ —
yalnızca mevcut backend ViewModel/selector çıktısını sunar.

Kapsam (öneri, küçük diff'ler):
- Panel görünürlük + layout tercihlerinin kalıcılığı (localStorage; backend state
  değil) — `usePanelVisibility` zaten var, tutarlılaştır.
- Simple/Expert grid + collapsed `<details>` okunabilirlik cilası; `page.tsx`
  büyütülmez (registry + GridCell).
- Boş / yükleniyor / hata durumları + "VERİ YOK / SIMULATION / NO_EXECUTION /
  PAPER_ONLY" rozetlerinin tutarlılığı (tüm panellerde aynı dil).
- Erişilebilirlik/responsive küçük düzeltmeler (kontrast, mobil grid).

## Hard rules (değişmez)
- Backend FREEZE: packages/ + apps/api + worker'lar SIFIR diff (P0 hotfix hariç).
- PAPER_SAFE / NO_EXECUTION; RiskGate/DQS/KillSwitch/halt dokunulmaz.
- Frontend hesap yapmaz; selector kullanır; openapi/TS şeması değişmez (codegen
  drift yeşil kalır).
- Yeni data source / dashboard redesign / intelligence / trading logic YOK.

## Validation
- `cd apps/web && pnpm tsc --noEmit && pnpm build` (frontend asıl gate).
- `pytest -q` (backend regresyon yok — sıfır diff; izole runtime path env'leri).
- `ruff check packages apps/api apps/tick_worker apps/learning_worker tests/contract`
- codegen/contract drift yeşil.
- `make smoke` (çalışan API+web) — UX değişikliği SSR'ı bozmamalı.

## Opsiyonel (ayrı küçük task)
- A1 P1 hardening (H1–H5): 5 düşük-churn store atomik write · schema_version yay ·
  ARCHITECTURE.md çok-agent şemasını "vizyon" olarak işaretle · gerçek
  `openapi-typescript` codegen · `decide_all` test-only docstring notu.
