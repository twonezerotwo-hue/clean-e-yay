# NEXT TASK — seç (SOAK1 + FULL SYSTEM AUDIT sonrası)

**SOAK1 (production dry-run) + FULL SYSTEM AUDIT** tamamlandı (bkz.
`.tasks/TASK_RESULT.md` + `docs/CURRENT_STATE.md`). Sonuç: **release-ready**.
~25 dk soak temiz (snapshot 8→53, tick 6→51, stale yok, 0 log error, smoke 8/8 ×2),
13-başlık audit yeşil, **P0 yok / P1 yok**. pytest 419/419, ruff/tsc clean, build ✓,
contract+codegen drift yeşil. **Backend FREEZE korundu; KOD SIFIR DİFF (docs hariç).**
PAPER_SAFE / NO_EXECUTION yapısal; RiskGate KILL_SWITCH 20/20 hücreye uniform;
LLM explanatory-only; replay stored-only; weights owner-gated.

A1 + DEP1 + REL1 + UX2 + UX3 + UX4 + SOAK1 + AUDIT bitti. **Backend FREEZE** —
yalnızca P0 hotfix. Aşağıdaki üç yönden biri seçilir:

## Seçenek A — UX5 after real user feedback (önerilen)
Soak/gerçek oturumdan somut geri bildirim topla, sonra hedefli cila: panel görünürlük
tercih kalıcılığı (localStorage; backend state değil), AIReport compact mod, boş/
yükleniyor/hata tutarlılığı, mobil/tablet kırılma, kontrast/erişilebilirlik.
Frontend-only; backend SIFIR diff; openapi/TS şeması değişmez. Spekülatif değil —
yalnızca gözlemlenen sorun varsa.

## Seçenek B — Longer soak / overnight run
Owner halt reset (`/api/v1/risk/halts/reset` + `/api/v1/paper-trading/reset`) ile
taze paper baseline kur, learning'i zamanlayıcıya bağla (cron/launchd timer —
restart-always DEĞİL), gece boyu çalıştır. Gözle: halt-free paper lifecycle (open→
tick→SL/TP→close), learning dataset büyümesi (insufficient→sufficient), >1h sonrası
learning stale uyarısının scheduler ile temizlenmesi, snapshot ring buffer cap 500
davranışı, uzun-süreli memory/log profili.

## Seçenek C — only P0 backend hotfix mode
Yeni iş açma; backend dondurulmuş RC. Yalnızca gerçek P0 bug → minimal + testli
hotfix. Audit'te P0/P1 çıkmadı; opsiyonel A1 P1 hardening (store atomik write,
schema_version, gerçek openapi-typescript codegen) hâlâ açık ama acil değil.

## Hard rules (her seçenekte)
- Backend FREEZE: packages/ + apps/api + worker SIFIR diff (P0 hotfix hariç).
- PAPER_SAFE / NO_EXECUTION; RiskGate/DQS/KillSwitch/halt dokunulmaz.
- Yeni data source / dashboard redesign / intelligence / trading logic YOK.
- Frontend hesap yapmaz; openapi/TS şeması değişmez (codegen drift yeşil kalır).
- Eski `E_YAY CODEX` LaunchAgent kalıcı silme owner kararı; Clean E-yAy izole port.

## Validation (değişen katmana göre)
- Frontend: `cd apps/web && pnpm tsc --noEmit && pnpm build` + SSR smoke (`make smoke`
  veya izole port).
- Devops/soak: `bash -n scripts/*.sh` + `make prod-up`/`prod-status`/`prod-smoke`/
  `prod-down` (izole `API_PORT`/`WEB_PORT`).
- Backend dokunulursa (yalnızca P0): `pytest -q` (izole runtime path env'leri) +
  `ruff check packages apps/api apps/tick_worker apps/learning_worker tests/contract`
  + contract/codegen drift.
