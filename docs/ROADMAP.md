# Roadmap — Clean E-yAy

## Current

- Mock veriyle uçtan uca yeşil.
- CI: `python` + `web` jobs yeşil.
- Dashboard 17 panel ile bağlı (mock data).
- Paper trading mock veriyle çalışıyor (open → tick → SL/TP close → PnL).

## Next

- **G1** — gerçek provider + DQS + snapshot + dashboard visibility
  (bkz. `.tasks/NEXT_TASK.md`)

## Then (sıra ile)

- ~~**G2** — auto-weight trainer~~ ✓
- ~~**G6** — confidence calibration~~ ✓
- ~~**G3** — mistake memory gate~~ ✓
- ~~**G4** — correlation-aware sizing~~ ✓
- ~~**G5** — daily-loss / max-DD halt~~ ✓
- ~~**T0** — timeframe contracts + schema seeding~~ ✓
- **T1** — OHLCV provider + gerçek multi-timeframe technicals
- **T2** — timeframe consensus + decision + paper (time-stop) +
  TimeframeMatrixPanel
- **v2.6** — LLM persona (Groq, narrative-only) — T2 sonrasına ertelendi
- **v2.7** — deep data (funding rate, options IV, realized vol, gerçek
  haber feed'i + **T3 catalyst half-life motoru**)
- **operations** — runbook, monitoring, alerting

Bir görev başlamadan önceki görev tamamlanmadan bir sonrakine geçilmez,
aksi NEXT_TASK.md'de açıkça belirtilmedikçe.
