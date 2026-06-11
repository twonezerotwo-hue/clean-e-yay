# NEXT TASK — G5 Daily-Loss / Max-DD Halt

Günlük zarar veya max drawdown limiti aşıldığında sistem otomatik durur
ve durduğunu görünür şekilde raporlar.

## Scope

- `packages/risk/` — halt durumu kalıcı hale gelsin:
  - Mevcut risk engine KILL_SWITCH/RISK_REDUCE üretiyor; ek olarak halt
    event'leri (`halt_started_at`, `reason`, `evidence`) diske yazılsın
    (örn. `data/runtime/risk_halts.json`).
  - Halt aktifken yeni pozisyon açılmaz (tick_worker + paper tick);
    sadece mevcut pozisyonların SL/TP tetiklenebilir.
  - Günlük zarar halt'i gün dönümünde otomatik kalkar (daily anchor);
    max-DD halt'i owner onayı/explicit reset ister.
- `GET /api/v1/risk/halts` — aktif halt + son halt timeline'ı.
- Dashboard: `DrawdownGuardPanel` (aktif halt + DD/daily-loss durumu +
  KillSwitch timeline). Selector + panel-registry + tek GridCell.

## Rules

- `PAPER_SAFE / NO_EXECUTION`
- RiskGate threshold'larını gevşetme; halt sadece kısıtlayıcı.
- KILL_SWITCH / RISK_REDUCE / NO_POSITION_INCREASE öncelik sırası korunur.
- Frontend hesap yapmaz; backend state gösterir.
- Test offline (mock paper state seed): daily-loss halt, max-DD halt,
  halt aktifken open yok, gün dönümünde daily halt reset, endpoint 200.
