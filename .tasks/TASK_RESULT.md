# TASK RESULT

Date: 2026-06-13
Task: R2 — Deterministic Rolling Replay / Backtest Runner
Status: completed

## Prensip

Kayıtlı snapshot serisi üzerinde **deterministik** replay/backtest. Live
provider refetch **YOK**, sahte geçmiş **YOK**, look-ahead bias **YOK**: karar
yalnızca kendi snapshot'ının verisinden gelir (kayıtlı `decision_matrix`),
outcome yalnızca GERÇEKTEN var olan gelecek snapshot'larla (karar zamanından
sonraki İLK gözlem) ölçülür. Yeni veri kaynağı / dashboard redesign / mimari
katman **EKLENMEDİ** — store'a okuma helper'ı + bir saf runner + iki endpoint.

PAPER_SAFE / NO_EXECUTION: backtest emir üretmez, paper pozisyon açmaz,
RiskGate'i bypass etmez, decide_matrix'i yeniden çalıştırmaz, broker yok.

## IMPLEMENTED

### 1. Snapshot store okuma helper (`packages/data/snapshot_store.py`)
- `all_docs()` → tüm OKUNABİLİR snapshot'lar kronolojik (dosya adı = ts) sırada;
  bozuk dosya atlanır, live refetch yok. `__all__`'a eklendi.

### 2. Backtest runner (yeni `packages/data/backtest.py`, saf fonksiyon)
- `run_backtest()` — store'u okur, `(symbol, timeframe)` karar hücrelerini
  15m/1h/4h/1d horizon'da değerlendirir.
- **Outcome**: her cell için `target = decision_time + horizon`; `_future_price`
  ilk `epoch >= target` snapshot'ın fiyatını alır (o snapshot'ta fiyat yoksa
  ileri ATLAMAZ → cherry-pick yasak → insufficient_future_data). Base fiyat
  kendi snapshot'ından; ileri ölçüm gelecekten → look-ahead yok.
- **Sinyaller**: `action ∈ {open_long, open_short}` → yön; realize getiri yön
  bazlı. **Bastırılmış adaylar**: `candidate_action` açılışken final sinyal
  değilse (blocked/hold) counterfactual (blok doğru muydu?).
- **Metrikler**: `hit_rate`, `false_positive(+rate)`, `false_negative(+rate)`,
  `avg_return`, `max_drawdown` (kümülatif sinyal getirisi equity eğrisi),
  `blocked_decision_accuracy`; `per_timeframe`, `per_symbol`, `per_horizon`.
  Yetersiz örnekte oranlar **null** (uydurma 0 değil). `run_id` = sıralı
  snapshot kümesi + horizon + algo versiyonundan SHA-256 (deterministik).

### 3. Endpoint (`apps/api/routers/replay.py`)
- `GET /api/v1/replay/backtest` → tam sonuç.
- `GET /api/v1/replay/backtest/{run_id}` → eşleşmezse 404 + `current_run_id`
  (sahte/bayat run saklanmaz; backtest store üzerinde deterministik).
- Her ikisi de `/replay/{snapshot_id}` catch-all'undan **ÖNCE** tanımlandı
  (FastAPI kayıt sırasıyla eşler — "backtest" snapshot_id sanılmasın).
- Dürüst durum: boş store → `insufficient_snapshots`; ölçülebilir gelecek yok →
  `insufficient_future_data` (ikisi de 200, dürüst body).

### 4. Sözleşme (additive + drift-safe)
- openapi: `/replay/backtest` + `/replay/backtest/{run_id}` path; `ReplayBacktest`
  + `ReplayBacktestMetrics` şemaları (status enum: ok / insufficient_snapshots /
  insufficient_future_data; per_* additionalProperties → metrics).
- TS `apps/web/types/generated/api.ts` senkron: `ReplayBacktestStatus`,
  `ReplayBacktestMetrics`, `ReplayBacktest`. Codegen drift + contract testleri
  yeşil.

## TESTS RUN
- `pytest -q` (TEST_USE_MOCK=true)
- `ruff check packages apps/api apps/tick_worker apps/learning_worker`
- `cd apps/web && tsc --noEmit && pnpm build`

## RESULTS
- **pytest: 375/375 passed** (366 baseline + 9 yeni; live network yok).
- **ruff (CI-scope): temiz**. **tsc --noEmit: temiz**; **pnpm build: ✓ Compiled**
  (SSR prerender 4/4).
- Yeni testler (`tests/unit/test_backtest_replay.py`): empty → insufficient_snapshots;
  one snapshot → insufficient_future_data; multiple → metrikler hesaplanır
  (hit_rate 0.5 / fp 4 / fn 4 / blocked_acc 0.5 / avg 0.0 / mdd 0.2, per-symbol &
  per-horizon dürüst); no-look-ahead (son snapshot ölçülmez, ileri fiyatla ölçer);
  endpoint 200 + run_id roundtrip/404; live provider çağrılmaz (pipeline patlatıldı);
  paper pozisyon açılmaz.

## LIVE SMOKE (izole API 127.0.0.1:8010, gerçek store)
- `/replay/status` → active, snapshot_count 1.
- `/replay/backtest` → status `insufficient_future_data` (tek kayıt), run_id
  deterministik, metrik oranları null (uydurma 0 değil), coverage dürüst.
- `/dashboard/state` → 200. İzole server kapatıldı.

## PAPER_SAFE CHECK
- broker: none · real order: none · live execution: none · LLM karar: none
- RiskGate/DQS/KillSwitch/halt: sıfır diff, bypass yok (backtest yalnızca okur)
- replay paper position açmaz, decide_matrix yeniden çalışmaz

## SKIPPED / NEXT
- Frontend backtest paneli BU görevde eklenmedi (kapsam backend bitirme modu);
  endpoint + sözleşme hazır, ileride Uzman/Detaylar altına panel eklenebilir.
- NEXT: **P1 — Paper lifecycle finalization**.

## COMMITS
- `feat(replay): add deterministic rolling backtest runner`
