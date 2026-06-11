# NEXT TASK — G2 Auto-Weight Trainer

Consensus modül ağırlıklarını paper trading sonuçlarına göre öğren.

## Scope

- `packages/learning/auto_weight_trainer.py`:
  - Kapalı trade'leri fingerprint'e göre grupla.
  - Modül × sonuç (win/loss/PnL) tablosundan modül başına performans
    skoru üret.
  - Mevcut `weights_v1.0.yaml`'a göre yeni `weights_v1.x.yaml` öner
    (versiyon bump, audit notu).
- `learning_worker` periyodik trainer çağrısı (her N trade veya günde
  bir).
- Owner approval mekanizması — `RebalanceProposal` dosyaya yazılır;
  manuel `approve` olmadan canlı `weights` değiştirilmez.
- `GET /api/v1/learning/rebalance/proposal` ve
  `POST /api/v1/learning/rebalance/approve` endpoint'leri.

## Dashboard parallel visibility

- `WeightProposalPanel` — bekleyen rebalance önerisi, modül delta'ları,
  approve/reject aksiyonları (sadece görünüm, network çağrısı V2'de).
- `WeightHistoryPanel` — versiyon zaman çizelgesi.
- selector + panel-registry girişleri.

## Rules

- `PAPER_SAFE / NO_EXECUTION`
- Owner approval olmadan ağırlık güncellemesi yok.
- Decision / risk / paper paketlerinde redesign yok.
- Test offline (mock paper state ile).
- G1 tamamlanmış sayılır (real provider fallback davranışı stabil).
