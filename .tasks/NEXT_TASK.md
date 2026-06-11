# NEXT TASK — G1 Real Providers

Implement real price providers and DQS visibility.

## Scope

- `PRICE_USE_MOCK=false` works
- YFinanceProvider
- CoinGeckoProvider
- FREDProvider
- MockProvider remains default for tests
- `fallback_used` / `verified` / DQS / error behavior
- snapshot endpoint can use live provider
- no live-network dependency in tests

## Dashboard parallel visibility

- DataQualityPanel
- ProviderStatusPanel
- SnapshotPanel
- MarketDataPanel
- selectors and panel-registry entries

## Rules

- `PAPER_SAFE / NO_EXECUTION`
- no broker
- no real order
- no decision/risk/paper redesign
- do not start G2 before G1 is complete
