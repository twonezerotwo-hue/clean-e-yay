# Current State — Clean E-yAy

_Bu dosya kısa ve güncel tutulur. Her görev sonunda güncellenir._

## Last known status

- **G2 tamamlandı**: auto-weight trainer + owner-approved rebalance akışı.
  - `packages/learning/auto_weight_trainer.py` — closed verified trade'leri
    fingerprint'in `dominant_module` parçasına göre grupluyor, per-module
    `win_rate + avg_pnl` skoru üretiyor, `weights_v1.0.yaml`
    constraints'lerine (`max_delta_per_module`, `max_total_drift`,
    `min_module_floor`) uygun delta önerip versiyonu `1.x.0`'a bump
    ediyor.
  - `packages/learning/rebalance_store.py` — pending/approved/rejected
    proposals + history (file-backed `data/runtime/rebalance.json`).
  - `packages/data/registry/loader.py` — `load_active_weights()` +
    `weights_manifest_path()` + `active_weights_version()`; consensus
    engine artık aktif weights'i okuyor.
  - Endpoints: `GET /api/v1/learning/rebalance/proposal`,
    `POST /learning/rebalance/{propose,approve,reject}`.
  - Approve → `config/weights_v1.x.yaml` + manifest günceller →
    consensus yeni weights ile çalışır.
- **DATA_POLICY uyumlu**: `Position.data_verified` ve `Trade.data_verified`
  alanları eklendi; mock/data-unavailable trade'ler trainer dataset'ine
  alınmaz; runtime mock kullanılmıyor.
- `learning_worker` periyodik olarak `auto_weight_trainer.train()` çağırır,
  yeterli veri varsa pending proposal yazar (active weights değiştirilmez).
- Frontend yeni paneller: `WeightProposalPanel`, `WeightHistoryPanel`
  (selector + panel-registry + page.tsx).
- Pytest: **26/26** yeşil (8 yeni G2 testi: insufficient, propose/approve/
  reject akışı, verified filter, consensus active weights).
- Ruff (CI scope): yeşil.
- Web build: CI'da doğrulanacak.

## Next task

- **G6** — confidence calibration (Platt scaling tam entegrasyon)
  veya **G3** — mistake memory gate (bkz. `docs/ROADMAP.md`).
- `.tasks/NEXT_TASK.md` G6 için güncellenecek.
