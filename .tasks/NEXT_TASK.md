# NEXT TASK — RC Freeze → UX Polish + Deployment/DevOps Checklist

**A1 — Final Backend Architecture Audit** tamamlandı → **BACKEND RELEASE CANDIDATE**
(bkz. `.tasks/TASK_RESULT.md` + `docs/CURRENT_STATE.md`). Audit: **PASS**, gerçek
P0 bug yok, sözleşme/runtime/TS drift yok, kritik test boşluğu yok. **Sıfır runtime
diff.** pytest 419/419, ruff/tsc/build yeşil, in-process smoke (10 GET 200 +
/chat bypass refusal). Commit: `docs(backend): mark backend release candidate after
final audit`.

P1 + L1 + O1 + A1 bitti. **Backend artık FREEZE.**

## Backend Freeze kuralı
- Backend'e **yalnızca P0 hotfix** girer (gerçek bug + testle kanıt).
- Yeni data source / dashboard redesign / intelligence module / trading logic /
  mimari katman **EKLENMEZ**.
- Endpoint path + response alan adları sabit (additive ok).
- PAPER_SAFE / NO_EXECUTION; RiskGate/DQS/KillSwitch/halt yalnızca kısıtlayıcı.

## Sıradaki iş (öncelik sırası)

### 1. UX Polish only (frontend; backend sıfır diff)
- Panel görünürlük tercihlerinin kalıcılığı (localStorage; backend state değil).
- Simple/Expert grid düzeni + collapsed `<details>` cilası; page.tsx büyütülmez.
- Boş/yükleniyor/hata durumları + "VERİ YOK / SIMULATION / NO_EXECUTION"
  rozetlerinin tutarlılığı. Frontend hesap YAPMAZ — selector kullanır.

### 2. Deployment / DevOps Checklist (gerçek dağıtım hazırlığı)
- `.env.example` tam mı (GROQ_API_KEY, FRED_API_KEY, *_PATH override'ları,
  SNAPSHOT_STORE_MAX, CORS, SSL_CERT_FILE).
- `data/runtime/` + `data/state/` gitignored (✓ doğrulandı) — prod volume mount.
- CI gate: pytest + ruff (CI scope) + codegen/contract drift + tsc + next build.
- Smoke runbook: izole port (eski `com.eyay.backend` LaunchAgent :8000 +
  port 3000 çakışması — `launchctl bootout` / 127.0.0.1).
- `docker-compose.dev.yml` → prod compose (api + tick_worker + learning_worker +
  web tek komut); healthcheck `/api/v1/health` + `/api/v1/system/health`.

### 3. (Opsiyonel) A1 P1 hardening — ayrı küçük task
- H1: `risk/halt.py` + `rebalance_store.py` + `calibration_store.py` +
  `agent/llm/budget.py` + `agent/llm/cache.py` → atomik temp+`os.replace`
  (snapshot/paper/run/heartbeat zaten kullanıyor; testle kanıtla).
- H2: store'lara `schema_version` (forward-uyumlu load zaten var).
- H3: `ARCHITECTURE.md` §4'ü gerçek (consensus + agent/llm) yapıya hizala —
  aspirasyonel çok-agent şemasını "gelecek vizyon" olarak işaretle.
- H4: gerçek `openapi-typescript` codegen'e geçiş (el-senkron drift'i kaldırır).
- H5: `decide_all` legacy tek-TF yoluna docstring notu (production decide_matrix).

## Hard rules (değişmez)
- PAPER_SAFE / NO_EXECUTION; broker yok, gerçek emir yok, live execution yok.
- RiskGate / DQS / KillSwitch / halt yalnızca kısıtlayıcı; bypass/gevşetme yok.
- LLM karar vermez. Runtime'da mock yok; testlerde live network yok.

## Validation (her değişiklikte)
- `pytest -q` (runtime state izole: RISK_HALT_PATH / PAPER_STATE_PATH /
  PAPER_AUDIT_PATH / SNAPSHOT_STORE_PATH / LEARNING_RUN_PATH / LEARNING_OUT_PATH /
  WORKER_HEARTBEAT_PATH temp dizine al).
- `ruff check packages apps/api apps/tick_worker apps/learning_worker tests/contract`
- `cd apps/web && pnpm tsc --noEmit && pnpm build`
- codegen/contract drift yeşil.
