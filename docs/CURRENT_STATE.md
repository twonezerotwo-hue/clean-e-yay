# Current State — Clean E-yAy

_Bu dosya kısa ve güncel tutulur. Her görev sonunda güncellenir._

## Last known status

- **G6 tamamlandı**: confidence calibration tam entegrasyon.
  - `packages/learning/calibration_store.py` — file-backed Platt (a, b)
    parametreleri; `predict_calibrated(raw_p)` → `(cal_p, source)`.
    Yetersiz veride identity döner.
  - `packages/learning/calibration_trainer.py` — sadece
    `data_verified=True` ve `predicted_confidence is not None` örnekleri
    kullanır; `MIN_SAMPLES=10` altında insufficient.
  - `packages/decision/engine.py` — her `TradeDecision` artık
    `confidence` (calibrated), `raw_confidence`, `confidence_source`
    taşır. **Calibrated confidence RiskGate'i bypass etmez** —
    KILL_SWITCH/RISK_REDUCE/NO_POSITION_INCREASE hard gate'ler önce
    çalışır; DQS < 55 zaten KILL_SWITCH üretir.
  - `Position`/`Trade` predicted/raw/source alanlarını taşır; open call
    site'ları (paper router + tick_worker) decision'dan geçirir.
  - Endpoints: `GET /api/v1/learning/calibration`,
    `POST /api/v1/learning/calibration/retrain`.
  - `learning_worker.run_once` calibration trainer'ı çağırır
    (auto-weight'ten önce).
  - `learning/summary.py` — 0.5 placeholder kaldırıldı; gerçek
    `predicted_confidence` örnekleri kullanılıyor (verified filter).
- Frontend: `CalibrationPanel` (Platt a/b + reliability bins + status)
  selector/registry/page'e bağlandı.
- Pytest: **36/36** yeşil (10 yeni G6 testi: insufficient/fit, verified
  filter, RiskGate bypass yok, DQS BLOCKED → trade yok).
- Ruff (CI scope): yeşil.
- Web build: CI'da doğrulanacak.

## Next task

- **G3** — mistake memory gate veya **G4** — correlation-aware sizing
  (bkz. `docs/ROADMAP.md`).
- `.tasks/NEXT_TASK.md` G3 için güncellenecek.
