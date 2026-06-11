# TASK RESULT

Date: 2026-06-11
Task: T0 — Timeframe contracts + schema seeding
Status: completed

## Files changed (tamamı additive)

- `packages/data/types.py` — `Timeframe` Literal (15m/1h/4h/1d/1w) +
  `TIMEFRAMES`/`DEFAULT_TIMEFRAME`; `TechnicalSnapshot.timeframe` Literal
  genişledi (15m+1w); `CatalystImpact` Pydantic modeli (contract-only).
- `packages/data/providers/technical/__init__.py` — TF passthrough
  (önceden 15m/1w → "1d"e eziliyordu; bilinmeyen hâlâ "1d").
- `packages/data/ingestion/pipeline.py` — `MarketSnapshot.technicals_by_tf`
  opsiyonel alan (default None; T1 doldurur).
- `packages/paper/state.py` — `Position.timeframe` + `Trade.timeframe`
  (default "1d").
- `packages/decision/engine.py` — `TradeDecision.timeframe` (default "1d").
- `packages/learning/fingerprint.py` — **v2**: `asset|v2|tf|regime|
  direction|bucket|C|module`; `is_v2()` helper; default tf="1d".
- `config/thresholds_v1.0.yaml` — `timeframe_risk` politikası (role,
  risk_multiplier ≤1.0, paper_execution, time_stop_hours; 1w execution=false).
- `contracts/openapi.yaml` — `Timeframe` enum; Position/Trade'e additive
  `timeframe`; `CatalystImpact`, `TimeframeDecision`, `DecisionMatrix`
  şemaları (taslak — endpoint T2'de).
- `apps/web/types/generated/api.ts` — Timeframe/CatalystImpact/
  TimeframeDecision/DecisionMatrix tipleri; Position/Trade.timeframe?.
  Panel YOK (T2/T4).
- `tests/unit/test_timeframe_contracts.py` (new) — 9 test.
- Docs: ARCHITECTURE.md §17.5 "Timeframe = first-class dimension";
  ROADMAP yeni sıra (T0✓→T1→T2→v2.6; T3→v2.7); CURRENT_STATE; NEXT_TASK→T1.

## Backward compatibility garantileri

- Legacy `paper_state.json` kayıtları (timeframe alanı olmadan) default
  "1d" ile yüklenir — testli (`test_legacy_position_and_trade_load_default_1d`).
- Legacy fingerprint'ler v2 ile ASLA çakışmaz (v2 tag'i + segment sayısı);
  eski kayıtlar mistake memory'de kendi içinde çalışmaya devam eder,
  v2 lookup'ları MIN_TRADES altında NEUTRAL fallback alır — testli.
- `MarketSnapshot.technicals` (legacy 1d alanı) aynen korunur;
  `technicals_by_tf` None.
- OpenAPI değişiklikleri additive (yeni şema + opsiyonel property).
- Mevcut 85 testin tamamı değişmeden yeşil.

## Değişmeyen runtime logic

- RiskGate hard gate'leri, halt (G5), DQS veto, KILL_SWITCH — sıfır diff.
- Decision/consensus akışı — `timeframe` yalnızca default'lu alan;
  fingerprint formatı dışında karar yolu aynı.
- Correlation sizing (G4), mistake memory eşikleri, calibration — aynı.
- timeframe_risk yalnızca config'te durur; T2'ye kadar hiçbir kod okumaz.

## Tests run

- `pytest -q` → **94/94 passed** (9 yeni T0).
- `ruff check` → All checks passed.
- `pnpm exec tsc --noEmit` + `pnpm build` → yeşil.

## Result

passed

## Next

- T1 — OHLCV provider + gerçek multi-timeframe technicals
  (`.tasks/NEXT_TASK.md` hazır).
