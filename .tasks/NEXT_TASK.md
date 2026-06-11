# NEXT TASK — G3 Mistake Memory Gate

Geçmişte tekrarlanan kayıp paterni yeni kararı engellesin.

## Scope

- `packages/learning/mistake_memory.py`:
  - `Mistake` kaydı: `fingerprint`, `streak_losses`, `total_pnl`,
    `last_seen_at`.
  - Closed verified trade'lerden fingerprint başına aggregate.
  - Streak ≥ N veya win_rate < threshold → AVOID seviyesinde flag.
- Decision engine'de filter:
  - Aday TradeDecision için `fingerprint` üret (aynı `make_fingerprint`
    fonksiyonu).
  - Mistake memory `should_avoid(fp)` derse `action="blocked"` reason
    `"mistake_memory:<fp>"`.
- **Önemli**: mistake memory **RiskGate'i bypass etmez**; sadece olası
  trade'i bloklar. KILL_SWITCH/RISK_REDUCE zaten kazanır.
- DATA_POLICY: yalnızca `data_verified=True` kayıtlar memory'ye girer.
- `/api/v1/learning/mistakes` endpoint — flagged fingerprint listesi.
- Dashboard `MistakeMemoryPanel` — flagged fingerprint'ler + sebep.

## Rules

- `PAPER_SAFE / NO_EXECUTION`
- Decision/risk threshold'larını gevşetme.
- Sadece eklemeli filter; başka politikaları zayıflatma.
- Test offline (mock paper state seed).
