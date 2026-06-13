# TASK RESULT

Date: 2026-06-13
Task: L1 — Learning Loop Finalization
Status: completed

## Prensip

Paper lifecycle (P1) sağlam ve audit edilebilir. L1 learning loop'u kapalı paper
trade outcome'larından **doğru, timeframe-aware, gate-aware ve owner-approval-safe**
öğrenecek hale getirdi. Yeni veri kaynağı / dashboard redesign / trading logic
**EKLENMEDİ**; RiskGate/DQS/KillSwitch/halt **sıfır diff**. PAPER_SAFE/NO_EXECUTION;
LLM karar vermez; active weights owner approval olmadan değişmez.

## LEARNING BASELINE (önce)

- Learning yalnızca `paper_state.Trade.recent_trades`'ten öğreniyordu (outcome=pnl);
  hepsi `data_verified=True` filtreli (DATA_POLICY).
- `summary` + `calibration` GLOBAL'di (timeframe ayrımı yok); `mistake_memory`
  full-fingerprint gruplayarak zaten timeframe-aware idi.
- Owner approval `rebalance_store.approve_current`'te (doğru); sample guard'lar
  (trainer MIN_TOTAL_TRADES=10/per_module=3, calibration MIN_SAMPLES, summary
  MIN_RELIABLE_TRADES=20) mevcuttu.
- Worker'da run metadata YOKTU.

### BUG
`auto_weight_trainer._parse_dominant_module` `fingerprint.split("|")[5]`
döndürüyordu. Legacy 6-parça için doğru (module=parts[5]); ama güncel **v2**
fingerprint (`asset|v2|tf|regime|dir|bucket|confluence|module`) için parts[5]=
**score_bucket** ("S55"), gerçek module **parts[7]** ("touche"). Trainer v2
trade'leri module yerine score bucket'a göre gruplayıp yanlış attribution
yapıyordu.

## IMPLEMENTED

### 1. Dominant module fix (`fingerprint.py`, `auto_weight_trainer.py`)
- `fingerprint.parse()` (v2 8-parça / legacy 6-parça / malformed-safe) +
  `dominant_module()` (v2→parts[7], legacy→parts[5], tanınmaz→None).
- `_parse_dominant_module` artık `fingerprint.dominant_module` kullanıyor.

### 2. Canonical outcome record (yeni `outcomes.py`)
- `CanonicalOutcome`: trade_id/symbol/timeframe/opened_at/closed_at/
  duration_seconds/direction/open_price/close_price/pnl/pnl_pct/open_reason/
  close_reason/fingerprint/regime/dominant_module/candidate_action/final_action/
  blocked_by/gates_applied/snapshot_id/decision_id/data_verified/source_quality/
  paper_only=True.
- `build_outcome(trade)` legacy + P1-enriched trade'den türetir; eksik alan
  default; bölme/parse hatalarında crash yok. P1 Trade gate attribution
  taşımadığından blocked_by/gates_applied=[], decision_id=None, candidate=final.

### 3. Timeframe-aware summary (`summary.py` additive)
- `breakdowns`: by_timeframe / by_symbol / by_regime / by_dominant_module /
  by_close_reason (bucket: trades/wins/losses/win_rate/total_pnl/avg_pnl/verified).
- outcomes_total / verified_outcomes / worker_last_run / proposal_status.
- Global win_rate/sharpe korundu; **15m outcome 1d bucket'ını etkilemez**.

### 4. Mistake memory + calibration
- Mistake memory full-fingerprint gruplaması (timeframe içerir) korundu →
  farklı timeframe = ayrı kayıt (test eklendi). Ağır rewrite yapılmadı.
- Calibration aktif davranışı (verified+predicted+MIN_SAMPLES → fit; aksi
  identity) **değişmedi**; mevcut testler korundu.

### 5. Auto-weight trainer
- Verified canonical outcome dağılımları (timeframe/regime/module) proposal
  audit + notes'a eklendi; min sample guard + owner approval korundu.

### 6. Learning worker metadata (yeni `run_store.py`, `learning_worker/main.py`)
- run_id/started_at/completed_at/status/skipped_reason/outcomes_seen/
  proposals_generated/calibration_status/errors; atomik yazım.
- Boş veri → NO_DATA (no_closed_outcomes); beklenmedik hata →
  COMPLETED_WITH_ERRORS. Worker ASLA patlamaz.

### 7. API/sözleşme/frontend (additive)
- openapi LearningSummary L1 alanları; TS api.ts senkron (+OutcomeBucket/
  LearningWorkerRun). codegen drift + contract testleri yeşil.
- LearningPanel: timeframe ayrımı satırları + worker last run + proposal status
  (frontend hesap yapmaz; backend ViewModel).

## FILES CHANGED
- `packages/learning/fingerprint.py` (parse + dominant_module)
- `packages/learning/outcomes.py` (yeni)
- `packages/learning/run_store.py` (yeni)
- `packages/learning/auto_weight_trainer.py` (module fix + evidence)
- `packages/learning/summary.py` (additive breakdowns)
- `apps/learning_worker/main.py` (run metadata)
- `contracts/openapi.yaml` (LearningSummary additive)
- `apps/web/types/generated/api.ts` (LearningSummary + OutcomeBucket + LearningWorkerRun)
- `apps/web/components/panels/LearningPanel/index.tsx` (additive görünürlük)
- `tests/unit/test_learning_outcomes.py` (yeni, +14)
- docs + task dosyaları

## LEARNING GUARANTEES
- **verified-only**: trainer + calibration yalnızca data_verified=True closed outcome.
- **timeframe-aware**: 15m outcome 1d bucket'ını etkilemez (ayrı bucket + ayrı fp).
- **owner approval**: active weights yalnızca approve_current ile değişir (proposal PENDING).
- **insufficient sample guard**: trainer MIN_TOTAL_TRADES/per_module; calibration
  MIN_SAMPLES → identity; summary MIN_RELIABLE_TRADES.
- **no live execution**: yalnızca okuma/türetme; broker/emir yok; RiskGate bypass yok.

## TESTS RUN
- `pytest -q` (izole runtime path'leri: RISK_HALT/PAPER_STATE/PAPER_AUDIT/
  SNAPSHOT_STORE/LEARNING_RUN/LEARNING_OUT)
- `ruff check packages apps/api apps/tick_worker apps/learning_worker tests/contract`
- `cd apps/web && pnpm tsc --noEmit && pnpm build`

## RESULTS
- **pytest: 407/407 passed** (393 + 14 yeni; live network yok).
- **ruff: temiz** · **tsc: temiz** · **pnpm build: ✓**.
- Yeni testler: dominant_module v2/legacy/malformed; canonical outcome
  legacy+P1-enriched+garbage; 15m≠1d bucket; trainer v2 attribution (touche, S55
  değil); mistake memory by timeframe; worker empty NO_DATA + metadata yazımı;
  summary breakdowns yüzeyi.

## LIVE SMOKE (izole API 127.0.0.1:8021 + web SSR 3101 — temp runtime, 12 seed trade)
- API: /health 200 · /learning/summary 200 · /learning/rebalance/proposal 200 ·
  /cockpit/brief 200 (bayat 8000 sunucusunda 404'tü → fresh kod doğrulandı).
- Learning: outcomes_total=12, by_timeframe {15m:4, 1d:8} **ayrı**,
  by_dominant_module=**touche** (S55 değil — bug fix canlı), worker_last_run
  COMPLETED (proposals=1, calib=FITTED), proposal_status=PENDING.
- Rebalance: active_version=**1.0.0** (owner approval YOK → weights değişmedi),
  current PENDING→1.1.0, audit tf_distribution {15m:4,1d:8} + module {touche:12}.
- Web: SSR 200, "Öğrenme" paneli + PAPER_ONLY render. İzole server'lar kapatıldı.

## PAPER_SAFE CHECK
- broker none · real order none · live execution none · LLM karar none
- owner approval required (active weights değişmez) · RiskGate/DQS/KillSwitch/halt
  sıfır diff, bypass yok · runtime mock yok · live network yok (testler).

## SKIPPED / NEXT
- Calibration timeframe-aware fit eklenmedi (aktif davranış kırılmasın diye;
  summary breakdown yeterli). Gate/reason attribution Trade'e yazılmadı (P1 Trade
  taşımıyor → canonical outcome'da default; ileride paper close enrichment ile
  doldurulabilir).
- NEXT: **O1 — 7/24 worker reliability** veya **A1 — Final backend architecture audit**.

## COMMITS
- `feat(learning): finalize outcome learning loop`
