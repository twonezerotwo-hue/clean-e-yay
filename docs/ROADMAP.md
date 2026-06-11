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

- **G2** — auto-weight trainer
- **G6** — confidence calibration (Platt scaling tam entegrasyon)
- **G3** — mistake memory gate (geçmiş hatalar yeni kararları etkiler)
- **G4** — correlation-aware sizing
- **G5** — daily-loss / max-DD halt (otomatik durdurma)
- **v2.6** — LLM persona (Groq, narrative-only)
- **v2.7** — deep data (funding rate, options IV, realized vol, korelasyon)
- **operations** — runbook, monitoring, alerting

Bir görev başlamadan önceki görev tamamlanmadan bir sonrakine geçilmez,
aksi NEXT_TASK.md'de açıkça belirtilmedikçe.
