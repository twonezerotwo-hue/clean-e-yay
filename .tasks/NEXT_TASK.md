# NEXT TASK — G4 Correlation-Aware Sizing

Aynı yöne çok korelasyonlu varlıkları aynı anda büyük boyutla açma.

## Scope

- `packages/risk/correlation.py` (yeni):
  - Closed trade verisinden (PnL serisi) sembol başına 30g rolling
    pencerede pairwise korelasyon hesapla; veri yetersiz olduğunda
    deterministic baseline kullan (örnek: BTC↔ETH=0.75, BTC↔QQQ=0.6,
    XAU↔DXY=-0.65 vs. — config'ten).
  - `cluster_exposure(open_positions, candidate) -> ClusterReport`:
    aynı yön + |ρ| > threshold pozisyonların toplam %equity'sini
    hesapla. Threshold thresholds.yaml `correlation_threshold` (mevcut).
- `packages/decision/engine.py`:
  - Aday open_long/open_short için cluster_exposure → eğer toplam ≥
    `max_cluster_pct` (örn. 0.30) → size_multiplier düşür veya 0.
  - Verdict TradeDecision'a `cluster_report` damgalı.
- **Hard kural**: correlation-aware sizing **RiskGate'i bypass etmez**.
  Sadece size küçültür; KILL_SWITCH/RISK_REDUCE her zaman önce çalışır.
  DQS BLOCKED → trade yok.
- Az veri varsa baseline + log uyarı (insufficient_correlation_data),
  size adjustment uygulanmaz (neutral fallback).
- `GET /api/v1/risk/correlation` endpoint: matris + cluster exposure.
- Dashboard `CorrelationPanel`: matrix heatmap (basit grid) + uyarı.

## Rules

- `PAPER_SAFE / NO_EXECUTION`
- Decision/risk threshold'larını gevşetme.
- DATA_POLICY: only verified trade PnL'leri korelasyon için kullanılır.
- Test offline (mock paper state seed).
