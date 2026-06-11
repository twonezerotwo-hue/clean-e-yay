# Current State — Clean E-yAy

_Bu dosya kısa ve güncel tutulur. Her görev sonunda güncellenir._

## Last known status

- **G3 tamamlandı**: mistake memory gate — sadece avoid/boost/warning/
  size_adjust üretir.
  - `packages/learning/mistake_memory.py` — verified+fingerprint'li
    closed trade'leri toplar; `Mistake` records + `MistakeVerdict`
    (AVOID / BOOST / WARNING / NEUTRAL).
  - Threshold'lar: `MIN_TRADES=3`, `AVOID_WIN_RATE=0.35`,
    `BOOST_WIN_RATE=0.65`, `WARNING_WIN_RATE=0.50`, `STREAK_AVOID=3`.
  - Size factor: AVOID=0.0 (hold), WARNING=0.7, NEUTRAL=1.0, BOOST=1.2.
  - `MIN_TRADES` altında → NEUTRAL (no_adjustment) fallback.
  - `packages/decision/engine.py` — consensus eşiği aşıldıktan sonra
    `evaluate(fp)` çağrılır. AVOID → hold; BOOST/WARNING → size×factor
    (1.5 cap'i korunur). TradeDecision `fingerprint` + `mistake_verdict`
    taşır.
  - **Hard kural**: mistake memory **RiskGate'i bypass etmez**.
    KILL_SWITCH→blocked, RISK_REDUCE/NO_POSITION_INCREASE→hold; DQS<55
    BLOCKED → trade yok (BOOST olsa bile).
  - `GET /api/v1/learning/mistakes` — kayıtlar + verdict'ler + threshold.
- **Frontend**: `MistakeMemoryPanel` — flagged fingerprint'ler + verdict
  + size adjustment + win_rate/streak/last_seen.
- Pytest: **47/47** yeşil (11 yeni G3 testi: aggregate, NEUTRAL/AVOID/
  BOOST/WARNING/streak, decision AVOID→hold, KILL_SWITCH/RISK_REDUCE
  bypass yok, DQS BLOCKED bypass yok, endpoint 200).
- Ruff (CI scope): yeşil.
- Web build: CI'da doğrulanacak.

- **Local live dev** hazır: `make dev` → API (8000) + web (3000) tek
  komut. Tüm 6 endpoint 200; web HTML SSR'de 25 panel render edildi
  (HeroScene canvas, PAPER_ONLY banner, 9 başlık doğrulandı).
  Docker alternatifi: `docker compose -f docker-compose.dev.yml up`.

## Next task

- **G4** — correlation-aware sizing (bkz. `docs/ROADMAP.md`).
- `.tasks/NEXT_TASK.md` G4 için hazır.
