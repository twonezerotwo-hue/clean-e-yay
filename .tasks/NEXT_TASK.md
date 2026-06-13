# NEXT TASK — P1 Paper Lifecycle Finalization

**R2 — Deterministic Rolling Backtest Runner** tamamlandı (bkz.
`.tasks/TASK_RESULT.md`): `packages/data/backtest.py` (saf `run_backtest()`),
`snapshot_store.all_docs()`, `GET /api/v1/replay/backtest(/{run_id})`; 15m/1h/4h/1d
horizon, hit_rate / false_positive / false_negative / avg_return / max_drawdown /
blocked_decision_accuracy + per_timeframe/per_symbol/per_horizon; look-ahead yok,
live refetch yok, paper açmaz. **375 pytest**, ruff CI-scope + tsc + pnpm build
yeşil, live smoke (`/replay/status`, `/replay/backtest`, `/dashboard/state`) OK.

> Backend bitirme modu — **yeni veri kaynağı / dashboard redesign / mimari katman
> EKLENMEZ.** Mevcut state'i doğru ve dürüst göster.

## P1 — Paper lifecycle finalization

Paper pozisyon yaşam döngüsünü deterministik olarak **kapat/sonlandır** ve
state'i dürüst raporla (PAPER_ONLY / NO_EXECUTION; broker yok, gerçek emir yok).

Amaç (kapsam taslağı — görev başında netleştir):
- Açık paper pozisyonların lifecycle durumu tek yerden okunur: open → time-stop
  ACTIVE/EXPIRED → close (realized PnL) — negatif geri sayım yok, çift kapanış yok.
- Kapanış nedenleri sınıflandırılır (time_stop / risk_flatten / kill_switch /
  manual) ve `paper_state_summary` + ilgili endpoint'lerde dürüst yüzeye çıkar.
- Equity/PnL/drawdown muhasebesi deterministik; replay/backtest ile tutarlı dil.
- Halt/kill-switch flatten yolu lifecycle ile çelişmemeli (RiskGate yalnızca
  kısıtlayıcı; bypass/gevşetme yok).

## Hard rules (değişmez)
- PAPER_SAFE / NO_EXECUTION; broker yok, gerçek emir yok, live execution yok.
- RiskGate / DQS / KillSwitch / halt yalnızca kısıtlayıcı; bypass/gevşetme yok.
- LLM karar vermez. Endpoint path + response alan adları sabit (additive ok).
- Runtime'da mock yok; testlerde live network yok. Look-ahead / sahte geçmiş yok.
- Yeni state → dashboard'da minimum görünürlük (selector + registry; page.tsx
  şişmez). PAPER_ONLY ruhu korunur.

## Validation
- `pytest -q` (narrow → full)
- ruff CI scope: `ruff check packages apps/api apps/tick_worker apps/learning_worker`
- `cd apps/web && tsc --noEmit && pnpm build`
- live smoke: `/paper-trading/state`, `/dashboard/state`, `/replay/backtest`
- codegen/contract drift yeşil
