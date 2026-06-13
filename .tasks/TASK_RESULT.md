# TASK RESULT

Date: 2026-06-13
Task: P1 — Paper Lifecycle Finalization
Status: completed

## Prensip

Paper trading yaşam döngüsü backend'de **net, güvenli, audit edilebilir ve
öğrenmeye hazır** hale getirildi. Yeni veri kaynağı / dashboard redesign /
intelligence module / mimari katman **EKLENMEDİ**. Mevcut davranış korundu;
lifecycle açık state machine'e + audit trail'e + robust state'e kavuştu.

PAPER_SAFE / NO_EXECUTION: gerçek emir yok, broker yok, live execution yok;
fiyat yoksa **fake kapanış yok** (DATA_POLICY); RiskGate/DQS/KillSwitch/halt
yalnızca kısıtlayıcı, bypass yok; replay/backtest paper açmaz (sıfır diff).

## PAPER BASELINE (önce)

- Open: `lifecycle.open_position` (SL/TP + TF time-stop `valid_until`); aynı
  (symbol, timeframe) açıksa yeni açılmaz (router "hold zaten açık", worker
  `continue`) — yön fark etmez (opposite-dir same-tf de bloklu).
- Close: `tick` → SL_HIT/TP_HIT/TIME_STOP_EXIT (hepsi fiyat ister); `flatten_all`
  → KILL_SWITCH_EXIT. Fiyat yoksa pozisyon açık kalır, retry.
- State: `data/runtime/paper_state.json` non-atomik; corrupt → sessiz default
  (yedek/schema_version yok). Eksikler: lifecycle_status state machine,
  expired/pending etiketi, duplicate audit/uyarı, **audit log**, atomik/backup,
  Trade'de open_reason/snapshot_id.

## IMPLEMENTED

### 1. Lifecycle state machine (`packages/paper/lifecycle.py`, `state.py`)
- Position additive: `lifecycle_status` (OPEN / EXPIRED_PENDING_PRICE /
  EXIT_PENDING / ERROR_STATE), `time_stop_expired`, `pending_exit_reason`,
  `open_reason`, `snapshot_id`, `scale_in`. Trade additive: `lifecycle_status`
  (CLOSED / FORCE_CLOSED), `open_reason`, `snapshot_id`.
- `tick`: bozuk pozisyon → ERROR_STATE; time-stop dolu + fiyat yok →
  EXPIRED_PENDING_PRICE (geçişte audit); fiyat varsa TIME_STOP_EXIT close;
  fiyat gelince bekleyen kapanır; pending temizlenir.
- `flatten_all(reason=KILL_SWITCH_EXIT)`: fiyat yok → EXIT_PENDING; fiyat varsa
  FORCE_CLOSED close. `close_position` reason→lifecycle (FORCE_CLOSED seti:
  KILL_SWITCH_EXIT/RISK_REDUCE_EXIT/MANUAL) + audit.

### 2. Tek açılış yolu — duplicate/scale-in (`attempt_open`)
- `find_open`, `evaluate_open` (saf politika), `attempt_open` (denetim → blocked/
  opened + audit). Aynı (symbol, timeframe) **yön fark etmeksizin** bloklanır
  (no hedge/flip); farklı TF serbest; `scale_in=True` explicit → açılır; fiyat
  yok → OPEN_BLOCKED(no_price). tick_worker + paper router AYNI yoldan açar.

### 3. Audit trail (yeni `packages/paper/audit.py`)
- append-only `data/runtime/paper_audit.jsonl`; `record/read_recent/summary`.
- Aksiyonlar: OPEN_ATTEMPT / OPENED / OPEN_BLOCKED / TIME_STOP_EXPIRED /
  EXIT_PENDING / CLOSED / KILL_SWITCH_EXIT / RISK_REDUCE_EXIT / STATE_REPAIRED /
  ERROR. Best-effort (lifecycle'ı asla patlatmaz); okuma bozuk satırı atlar.

### 4. State robustness (`packages/paper/state.py`)
- `schema_version`, atomik yazım (temp + os.replace), corrupt → yedek
  (`paper_state.corrupt-<ts>.json`) + temiz default + STATE_REPAIRED audit
  (crash yok), `_only_known` ile legacy/forward-uyumlu yükleme.

### 5. API surface (additive — `apps/api/routers/paper_trading.py`)
- `/paper-trading/state`: `new_entries_disabled` (aktif halt'ten, read-only),
  `duplicate_warning`, `audit_summary`, `recent_audit_events`; Position/Trade
  lifecycle alanları (asdict). `/tick` açılışı attempt_open'a taşındı (yanıt
  etiketleri korundu). `/reset` → STATE_REPAIRED(manual_reset) audit.

### 6. Sözleşme + frontend (additive, drift-safe)
- openapi: `PaperLifecycleStatus` + `PaperAuditEvent` şemaları; Position/Trade/
  PaperTradingState additive alanlar. TS api.ts senkron. Codegen drift + contract
  testleri yeşil.
- PaperActionPanel: EXPIRED_PENDING_PRICE/EXIT_PENDING "fiyat bekleniyor",
  ERROR_STATE rozeti, duplicate uyarı bandı (selector/registry değişmedi).

## LIFECYCLE GUARANTEES

- **time-stop**: fiyat varsa TIME_STOP_EXIT (CLOSED); fiyat yoksa
  EXPIRED_PENDING_PRICE → sonraki tick fiyatla kapanır; negatif geri sayım yok;
  fake fiyat yok.
- **duplicate/scale-in**: aynı (symbol, timeframe) yön fark etmeksizin bloklanır
  (no hedge); farklı TF serbest; scale-in yalnızca explicit.
- **close reasons**: SL_HIT/TP_HIT/TIME_STOP_EXIT (CLOSED) · KILL_SWITCH_EXIT
  (FORCE_CLOSED). Geçmiş/learning uyumu için yeniden adlandırma YAPILMADI.
- **audit log**: her open/close/blocked/expired/repair olayı JSONL'e yazılır.
- **learning handoff**: Trade symbol/timeframe/opened_at/closed_at/open_reason/
  close_reason/pnl/fingerprint/snapshot_id/confidence/lifecycle_status taşır.
- **state robustness**: missing → default; corrupt → yedek+default (crash yok);
  legacy kayıt lifecycle alanları olmadan yüklenir; atomik yazım.

## TESTS RUN
- `pytest -q` (TEST_USE_MOCK=true)
- `ruff check packages apps/api apps/tick_worker apps/learning_worker tests/contract`
- `cd apps/web && pnpm tsc --noEmit && pnpm build`

## RESULTS
- **pytest: 393/393 passed** (375 baseline + 18 yeni; live network yok).
- **ruff (CI-scope + tests/contract): temiz**. **tsc: temiz**; **pnpm build: ✓**.
- Yeni testler (`tests/unit/test_paper_lifecycle.py`, +18): time-stop close/pending/
  pending→close, kill-switch force/pending, risk-reduce unchanged, duplicate &
  opposite-dir blocked, different-tf allowed, scale-in, no-price blocked, audit
  written + corrupt-line skip, learning fields present, corrupt-state backup/default,
  legacy migration, atomic save, state endpoint surface + no live refetch.

## LIVE DASHBOARD SMOKE (izole API 127.0.0.1:8010 + web SSR 3100 prod build)
- API: /health 200 · POST /paper-trading/tick 200 · /paper-trading/state 200 ·
  /dashboard/state 200 · /cockpit/brief 200.
- paper-state: new_entries_disabled=true (aktif halt), audit_summary gerçek
  olaylar (OPENED 30 / CLOSED 7 / KILL_SWITCH_EXIT 7 / EXIT_PENDING 4 /
  TIME_STOP_EXPIRED 2 / OPEN_ATTEMPT 16), recent_audit_events lifecycle akışını
  gösteriyor.
- Web SSR 200: "Paper Action State" + "PAPER_ONLY" render. Server'lar kapatıldı.

## PAPER_SAFE CHECK
- broker none · real order none · live execution none · LLM karar none
- fake price yok (fiyatsız exit beklemeye alınır) · RiskGate/DQS/KillSwitch/halt
  bypass yok · replay/backtest paper open üretmez · lifecycle gerçek emir üretmez

## SKIPPED / NEXT
- RISK_REDUCE_EXIT için ayrı flatten DAVRANIŞI eklenmedi (risk-reduce davranışı
  değişmesin diyerek); enum/parametre hazır, ileride owner kararıyla bağlanabilir.
- NEXT: **L1 — Learning loop finalization** (veya O1 — 7/24 worker reliability).

## COMMITS
- `feat(paper): finalize lifecycle and audit trail`
