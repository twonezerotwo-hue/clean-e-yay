# Agent Changelog

## 2026-06-11
- Initialized persistent context protocol.
- Added docs for architecture, safety, roadmap, dashboard rules.
- Next task set to G1 real providers.
- G1 completed: CoinGecko/yfinance/FRED providers + orchestrator with
  mock fallback, provider_status tracker, `/api/v1/data/snapshot`
  endpoint, 4 dashboard panels (DataQuality / ProviderStatus / Snapshot
  / MarketData). 12/12 pytest, ruff green.
- G1.1 completed: data policy enforced — runtime mock fallback removed.
  PriceQuote nullable price + verified/status/error; DQS BLOCKED status;
  test-only mock via TEST_USE_MOCK; runtime opt-in PRICE_USE_MOCK shows
  red banner. Frontend panels show "VERİ YOK" / BLOCKED states. 18/18
  pytest, ruff green. DATA_POLICY.md added.
- G2 completed: auto-weight trainer + owner-approved rebalance flow.
  Position/Trade carry data_verified; trainer filters non-verified.
  RebalanceProposal generated when ≥10 verified trades; constraints
  enforced; `/learning/rebalance/{proposal,propose,approve,reject}`.
  Approve writes weights_v1.x.yaml + manifest, consensus reads via
  load_active_weights(). 2 dashboard panels (WeightProposal,
  WeightHistory). 26/26 pytest, ruff green.
- G6 completed: confidence calibration tam entegrasyon. Decision engine
  raw → Platt-calibrated p(win) üretir; RiskGate'i bypass etmez.
  Position/Trade calibration trio taşır; trainer verified+predicted
  filter eder; MIN_SAMPLES=10 altında identity. New endpoints
  /learning/calibration[/retrain] + CalibrationPanel. 36/36 pytest,
  ruff green.
- Next task → G3 mistake memory gate or G4 correlation-aware sizing.
