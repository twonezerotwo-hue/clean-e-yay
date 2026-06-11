# Agent Changelog

## 2026-06-11
- Initialized persistent context protocol.
- Added docs for architecture, safety, roadmap, dashboard rules.
- Next task set to G1 real providers.
- G1 completed: CoinGecko/yfinance/FRED providers + orchestrator with
  mock fallback, provider_status tracker, `/api/v1/data/snapshot`
  endpoint, 4 dashboard panels (DataQuality / ProviderStatus / Snapshot
  / MarketData). 12/12 pytest, ruff green.
- Next task → G2 auto-weight trainer.
