# TASK RESULT

Date: 2026-06-13
Task: O1 — 7/24 Worker Reliability
Status: completed

## Prensip

Clean E-yAy artık endpoint koleksiyonu değil, **gözlemlenebilir 7/24 agent
servisi**: worker heartbeat + stale tespiti + crash raporlama + system health.
Yeni data source / dashboard redesign / intelligence module / trading logic
**EKLENMEDİ**; RiskGate/DQS/KillSwitch/halt **sıfır diff**. PAPER_SAFE/
NO_EXECUTION; worker reliability hiçbir şekilde trade iznini artırmaz.

## WORKER BASELINE (önce)

- **tick_worker** (`apps/tick_worker/main.py`): 30sn `run()` döngüsü; `run_once()`
  her tick'te snapshot al → price_tick → halt sync → decide_matrix → attempt_open
  → paper save → snapshot_store.record. `run()` istisnayı logluyordu ama
  **heartbeat/last-tick YOK**; crash dışarıdan görünmüyordu.
- **learning_worker** (`apps/learning_worker/main.py`): L1'de run metadata
  (run_store) vardı ama **heartbeat / stale tespiti YOK**.
- **snapshot_store**: atomik write + count/status mevcut; "yazılıyor mu" izlemi YOK.
- **health endpoint** (`/health`): yalnızca uptime/version — worker durumunu
  BİLMİYORDU.
- provider_status / dqs / halt store mevcut ama tek "system health" yüzeyi yoktu.

## IMPLEMENTED

### 1. Heartbeat store (yeni `packages/ops/heartbeat.py`)
- File-backed `data/runtime/worker_heartbeats.json` (`{worker: WorkerHeartbeat}`).
  Atomik write (temp+os.replace); corrupt/missing → default (crash yok); env
  `WORKER_HEARTBEAT_PATH` (call-time). Fields: worker_name/run_id/started_at/
  completed_at/status/last_success_at/last_error/cycle_count/snapshots_written/
  decisions_generated/paper_actions/learning_outcomes_seen/proposals_generated/
  duration_ms.
- `record()`: cycle_count yalnızca terminal (OK/DEGRADED/FAILED/NO_DATA) artar;
  last_success_at OK/DEGRADED/NO_DATA'da güncellenir, FAILED/RUNNING'de korunur.

### 2. System health ViewModel (yeni `packages/ops/system_health.py`)
- Network-free (heartbeat + snapshot_store + halt + paper_audit). STALE/UNKNOWN
  **türetilir** (eşik `TICK_STALE_SEC`=120 / `LEARNING_STALE_SEC`=3600; FAILED
  stale olsa da görünür kalır). provider_summary, dqs_status,
  snapshot_store_status, risk_halt_status.
- Owner **warning** modeli (rapor — execution alert DEĞİL): worker_stale /
  stale_dashboard_state / provider_degraded / dqs_blocked / snapshot_store_empty /
  learning_worker_no_data / paper_audit_errors / active_halt.

### 3. System health endpoint (yeni `apps/api/routers/system.py`)
- `GET /api/v1/system/health` → api_status/paper_safe/no_execution/workers/
  stale_workers/last_successful_tick/last_learning_run/provider_summary/
  dqs_status/snapshot_store_status/risk_halt_status/warnings. `/health` korundu.

### 4. Tick worker reliability (`apps/tick_worker/main.py`)
- Her cycle: RUNNING heartbeat → iş → OK/DEGRADED (veri/sağlayıcı bozuk ya da
  aktif halt → DEGRADED). İstisnada **FAILED heartbeat** + log; `run_once` ASLA
  loop'u öldürmez. snapshots_written/decisions_generated/paper_actions sayılır.
  Worker gerçek emir üretmez (attempt_open paper-only, drift yok).

### 5. Learning worker reliability (`apps/learning_worker/main.py`)
- L1 run metadata heartbeat'e bağlandı: COMPLETED→OK / COMPLETED_WITH_ERRORS→
  DEGRADED / NO_DATA→NO_DATA. Boş veri crash değil (NO_DATA = "alive").

### 6. API/sözleşme/frontend (additive)
- openapi `SystemHealth` + `WorkerHealth` + `/system/health`; TS api.ts senkron
  (+useSystemHealth hook/key/client). codegen drift + contract yeşil.
- SystemHealthBar: worker status + stale + last tick/learning + snapshot count +
  warning rozetleri + NO_EXECUTION badge (frontend hesap yapmaz; backend ViewModel).

## FILES CHANGED
- `packages/ops/__init__.py` (yeni)
- `packages/ops/heartbeat.py` (yeni)
- `packages/ops/system_health.py` (yeni)
- `apps/api/routers/system.py` (yeni)
- `apps/api/main.py` (router register)
- `apps/tick_worker/main.py` (heartbeat)
- `apps/learning_worker/main.py` (heartbeat)
- `contracts/openapi.yaml` (/system/health + SystemHealth + WorkerHealth)
- `apps/web/types/generated/api.ts` (SystemHealth + WorkerHealth)
- `apps/web/lib/api/client.ts` + `lib/queries/keys.ts` + `lib/queries/hooks.ts`
- `apps/web/components/panels/SystemHealthBar/index.tsx`
- `tests/unit/test_worker_reliability.py` (yeni, +11)
- docs + task dosyaları

## RELIABILITY GUARANTEES
- **heartbeat**: her worker cycle'ı kayıt altında (file-backed, atomik).
- **stale detection**: tick/learning eşik aşımı → STALE; hiç çalışmadı → UNKNOWN.
- **crash reporting**: tick istisnası → FAILED heartbeat (loop ölmez), last_error.
- **snapshot monitoring**: snapshot_store_status + snapshot_store_empty warning.
- **worker metadata**: cycle_count / last_success_at / duration / sayaçlar.
- **no execution**: yalnızca gözlem/rapor; broker yok, gerçek emir yok, RiskGate
  bypass yok.

## TESTS RUN
- `pytest -q` (izole runtime: WORKER_HEARTBEAT/RISK_HALT/PAPER_STATE/PAPER_AUDIT/
  SNAPSHOT_STORE/LEARNING_RUN/LEARNING_OUT)
- `ruff check packages apps/api apps/tick_worker apps/learning_worker tests/contract`
- `cd apps/web && pnpm tsc --noEmit && pnpm build`

## RESULTS
- **pytest: 419/419 passed** (407 + 11 yeni + 1 otomatik /system/health contract
  parametresi; live network yok).
- **ruff: temiz** · **tsc: temiz** · **pnpm build: ✓**.
- Yeni testler: heartbeat write/read/missing/corrupt/cycle_count+last_success,
  stale detection, fresh not-stale, paper_safe flags, tick success→OK/DEGRADED,
  tick exception→FAILED (loop ölmez), learning empty→NO_DATA, endpoint worker
  statüleri.

## LIVE SMOKE (izole API 127.0.0.1:8023 + web 3102 — temp runtime, seed: 1 tick + 1 learning run)
- API: /health · /system/health · /cockpit/brief · /learning/summary → **200**.
- system/health: tick_worker DEGRADED **stale=false** (cycle 1, age ~21s, 3 sağlayıcı
  degraded); learning_worker NO_DATA stale=false; last_successful_tick +
  last_learning_run dolu; dqs_status OK; provider_summary 8 ok/3 degraded/2 unknown;
  snapshot_count 1; risk_halt_status active=false; warnings
  [provider_degraded, learning_worker_no_data].
- Web: SSR 200, "Sistem Sağlığı" paneli + NO_EXECUTION + PAPER_ONLY. İzole
  server'lar kapatıldı, temp temizlendi.

## PAPER_SAFE CHECK
- broker none · real order none · live execution none · LLM karar none
- worker reliability trade iznini artırmaz · RiskGate/DQS/KillSwitch/halt sıfır
  diff, bypass yok · system/health yalnızca raporlar.

## SKIPPED / NEXT
- "dqs_blocked_too_long" süre-takibi yerine son snapshot dqs=BLOCKED (dqs_blocked)
  ile yaklaşıldı (snapshot geçmişi taraması maliyetli; cheap endpoint tercih edildi).
- tick_worker RUNNING-stuck detection heartbeat yaşına dayanıyor (ayrı watchdog yok).
- NEXT: **A1 — Final Backend Architecture Audit** (uçtan uca tutarlılık / ölü kod /
  sözleşme denetimi; yeni veri/feature yok).

## COMMITS
- `feat(ops): add worker reliability health`
