# TASK RESULT

Date: 2026-06-13
Task: R1 — Real Snapshot Replay / Backtest Foundation
Status: completed

## Prensip

Replay önceden `reserved_not_active` olarak dürüstçe duruyordu (disk store yoktu).
R1 bunu **sahte backtest yapmadan**, gerçek kaydedilmiş snapshot/decision state
üzerinden çalışan minimal ve güvenilir replay foundation'a çevirdi. Replay =
**kaydedilmiş gerçek state'in incelenmesi** (stored state inspection). Uydurma
geçmiş performans YOK; yeterli snapshot yoksa dürüstçe `empty` /
`insufficient_snapshots` der.

PAPER_SAFE / NO_EXECUTION: replay hiçbir emir üretmez, yeni paper pozisyon açmaz,
RiskGate'i bypass etmez, LLM karar motoruna bağlanmaz, **live provider çağırmaz**
(yalnızca store'dan okur). Yeni mimari katman / yeni veri kaynağı / yeni dashboard
redesign / yeni intelligence module EKLENMEDİ.

## REPLAY BASELINE (önce)

- `apps/api/routers/replay.py`: status hardcode `reserved_not_active`,
  `available=False`; iki endpoint de `get_cached_snapshot()` (live) çağırıp yalnızca
  en son in-memory snapshot id'yi yansıtıyordu.
- Snapshot yalnızca in-memory (`pipeline._CACHE`, 30s TTL). Disk store YOK,
  `data/runtime/snapshots/` YOK, `snapshot_store.py` YOK (ARCHITECTURE §3'te tanımlı
  ama hiç yazılmamış).
- ReplayStatusPanel "REZERVE · AKTİF DEĞİL" + latest id + reason gösteriyordu.
- OpenAPI: `ReplayStatus` (enum reserved_not_active) + `ReplaySnapshotStatus`.

## IMPLEMENTED

### 1. Disk snapshot store (`packages/data/snapshot_store.py`, yeni)
- Atomik write: temp dosya + `os.replace` (yarım dosya asla görünmez).
- Bozuk/okunamaz dosya → crash yok (`_read` None döner, atlanır).
- `record(payload)` (aynı id en güncelse duplicate yazmaz; başarısızsa None),
  `latest()` (en yeni okunabilir), `get(id)`, `count()`, `list_ids()`, `status()`.
- Zaman-sıralı dosya adı `<ts>__<safe_id>.json` (path-traversal güvenli sanitize).
- Ring-buffer prune (`SNAPSHOT_STORE_MAX`, default 500). Dir env
  `SNAPSHOT_STORE_PATH` (default `data/runtime/snapshots/`; testte temp dir).
- Store SAF: decision/risk import etmez (cycle yok); yalnızca dict yazar/okur.

### 2. Producer (`apps/tick_worker/main.py`)
- `run_once()` sonunda matrix_view + state'i `snapshot_store.record(...)` ile yazar.
- Store yazımı try/except + log ile sarıldı — ASLA tick'i patlatmaz.
- Kayıt alanları: schema_version, snapshot_id, generated_at, mode (provenance),
  dqs, provider_status, data_snapshot (compact), decision_matrix (matrix_view tam),
  risk_state, paper_state_summary.

### 3. Replay endpoint'leri (`apps/api/routers/replay.py`, store'a bağlı)
- `GET /replay/status` → status (active/empty), available, mode
  (active_snapshot_replay / insufficient_snapshots / reserved_not_active),
  snapshot_count, latest_snapshot_id, latest_generated_at, schema_version, reason,
  execution=no_live_execution.
- `GET /replay/{id}` → kayıtlı snapshot zarfı; store'da yoksa **404 not_found**.
- `GET /replay/{id}/decision-trace` → kayıtlı decision_matrix'ten karar izi:
  snapshot_id, generated_at, mode, dqs, regime, suspended, risk_gate,
  top_candidates, final_decisions, blocked_by_reasons, paper_actions,
  paper_state_summary, provider_issues, deep_data (options/vol/türev/catalyst/
  event_risk). Yeni karar HESAPLAMAZ, live provider çağırmaz.

### 4. Sözleşme (additive + drift-safe)
- openapi: `ReplayStatus` güncellendi; `ReplaySnapshot` + `ReplayDecisionTrace`
  eklendi; `/replay/{id}/decision-trace` path; `ReplaySnapshotStatus` kaldırıldı.
- TS api.ts senkron: `ReplayStoreStatus`/`ReplayMode`/`ReplayExecution` enum
  literalleri + `ReplayStatus`/`ReplaySnapshot`/`ReplayDecisionTrace` tipleri.

### 5. Frontend (selector + mevcut panel pattern; page.tsx büyümedi)
- `lib/selectors/replay.ts`: active/count/mode rozeti.
- `ReplayStatusPanel`: store status + mode rozeti + snapshot_count + latest id/zaman
  + "NO LIVE EXECUTION" rozeti + "Replay does not execute trades" notu.

### 6. Tests
- `tests/unit/test_snapshot_replay.py` (+13): atomik+latest, by-id+missing,
  corrupted-skip (crash yok), dedup, prune, status empty/active, endpoint
  empty/active, found+404, decision-trace stored-matrix, "replay live refetch
  yapmaz" (pipeline boom guard), tick_worker producer (offline), corrupted-only
  store status, json roundtrip.
- `tests/contract/`: eski reserved 200 testi → 404 not_found testi + decision-trace
  404 testi. Contract + codegen drift yeşil.

## TESTS RUN
- `pytest -q`
- `ruff check packages apps/api apps/tick_worker apps/learning_worker tests/contract`
- `cd apps/web && tsc --noEmit && pnpm build`

## RESULTS
- **pytest: 349/349 passed** (334 baseline + 15 net yeni); live network yok.
- **ruff (CI-scope): temiz** (RUF022 `__all__` sort auto-fix).
- **tsc --noEmit: temiz**; **pnpm build: ✓ Compiled** (SSR prerender 4/4).

## LIVE DASHBOARD SMOKE (izole API 8011, gerçek veri + 1 gerçek snapshot seed)
- API: /health /data/snapshot /decision/matrix /dashboard/state → 200.
- Replay status: active · mode=active_snapshot_replay · count=1 ·
  latest=snap::4c0c1468aa28 · execution=no_live_execution.
  /replay/{id} 200 (decision_matrix dahil); /replay/{id}/decision-trace 200
  (regime NEUTRAL, risk_gate NO_POSITION_INCREASE, 8 top candidate, 20 final,
  blocked_by risk_gate:NO_POSITION_INCREASE, deep_data 5 anahtar); missing → 404.
- Web: SSR 200 (izole 3100), 32 panel + HeroScene canvas + PAPER_ONLY.
- Replay panel: replay_status paneli SSR'da mevcut (store status + mode + count).
- İzole server'lar kapatıldı; `data/runtime/` gitignore'lu (snapshot commit'lenmez).

## PAPER_SAFE CHECK
- broker: none
- real order: none
- live execution: none
- replay execution: none (replay yalnızca stored state okur; emir/karar üretmez)
- RiskGate/DQS/KillSwitch/halt: sıfır diff, bypass yok

## SKIPPED / NEXT
- Rolling/historical backtest runner BİLİNÇLİ yapılmadı (sahte geçmiş üretme yasağı).
  Replay foundation gerçek çalışıyor; yeni veri kaynağı gerekmez.
- NEXT: **UX1 Agent Operating Cockpit** veya **R2 deterministic rolling replay/
  backtest runner** (stored snapshot serisi üzerinde deterministik yeniden-üretim +
  drift tespiti; yeni live veri yok).

## COMMITS
- `feat(replay): add real snapshot replay foundation`
