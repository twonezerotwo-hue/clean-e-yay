# TASK RESULT

Date: 2026-06-11
Task: G4 — Correlation-aware sizing
Status: completed

## Files changed

- `packages/risk/correlation.py` (new) — pairwise rho: verified trade
  PnL serisinden 30g pencerede computed → config `correlation_baseline`
  → neutral fallback sırası; `cluster_exposure()` (aday için aynı yönlü
  cluster cap, hedge ayrımı), `open_clusters()` (union-find,
  OK/WARNING/BREACH).
- `packages/decision/engine.py` — mistake gate'ten sonra G4 cluster cap:
  cluster ≥ `max_cluster_pct` → hold; ≥ yarısı → size×0.5; asla artırmaz.
  TradeDecision `cluster_report`; `decide_all(open_positions=...)`.
- `apps/api/routers/risk.py` (new) — `GET /api/v1/risk/correlation`.
- `apps/api/main.py` — risk router kayıt.
- `apps/api/routers/paper_trading.py`, `apps/tick_worker/main.py` —
  decide_all'a `ps.open_positions` geçirir.
- `config/thresholds_v1.0.yaml` — `max_cluster_pct: 0.30`,
  `correlation_min_overlap_days: 5`, `correlation_baseline` bölümü.
- `contracts/openapi.yaml` — `/api/v1/risk/correlation` + CorrelationEntry
  / ExposureCluster / CorrelationState şemaları.
- `tests/unit/test_correlation.py` (new) — 14 test.
- Frontend: `components/panels/CorrelationPanel/` (new),
  `TradingPanel` (flagged cluster satırları),
  `lib/selectors/correlation.ts` (new), `lib/api/client.ts`,
  `lib/queries/{keys,hooks}.ts`, `lib/panel-registry.ts`
  (`correlation`), `types/generated/api.ts`, `app/page.tsx` (tek
  GridCell).
- Ayrıca: önceki oturumdan kalan **provenance mode block** işi ayrı
  commit olarak kaydedildi (989c932).

## Safety

- RiskGate bypass YOK: KILL_SWITCH→blocked, RISK_REDUCE/
  NO_POSITION_INCREASE→hold correlation'dan önce döner; DQS<55 →
  KILL_SWITCH → trade yok (testli).
- Correlation logic yalnızca küçültür: size_factor ∈ {1.0, 0.5, 0.0}.
- |rho| ≥ 0.7 aynı risk cluster; ters yön → hedge (cap'e girmez).
- Veri yetersiz → neutral fallback, adjustment yok,
  `insufficient_correlation_data` uyarısı.
- PAPER_SAFE / NO_EXECUTION korunuyor; live network bağımlılığı yok
  (sadece verified trade PnL + config baseline).

## Tests run

- `pytest -q` → **72/72 passed** (14 yeni G4).
- `ruff check packages apps/api apps/tick_worker apps/learning_worker`
  → All checks passed.
- `pnpm exec tsc --noEmit` → temiz; `pnpm build` → yeşil (4/4 static).

## Live verification

- API `GET /api/v1/risk/correlation` → 200: threshold 0.7, cap 0.30,
  4 sembol, BTC↔ETH baseline 0.75, neutral çiftler insufficient_pairs'te.
- Web `http://127.0.0.1:3000` → 200; SSR'de **26 panel**
  (`data-panel="correlation"` dahil), "Korelasyon" başlığı, HeroScene
  canvas, PAPER_ONLY banner. Web log temiz.
- Not: 3000 portunu eski E_YAY CODEX frontend'i (nohup artığı) kapmıştı;
  süreç kapatıldı, Clean E-yAy web yeniden bağlandı.

## Result

passed

## Next

- G5 — daily-loss / max-DD halt (DrawdownGuardPanel / KillSwitchTimeline).
