# NEXT TASK — L1 Learning Loop Finalization

**P1 — Paper Lifecycle Finalization** tamamlandı (bkz. `.tasks/TASK_RESULT.md` +
`docs/CURRENT_STATE.md`): robust paper state (schema_version / atomik yazım /
corrupt→yedek+default / legacy load), append-only audit trail
(`packages/paper/audit.py`), lifecycle state machine (OPEN →
EXPIRED_PENDING_PRICE / EXIT_PENDING / ERROR_STATE → CLOSED / FORCE_CLOSED),
time-stop finalization (fiyat varsa TIME_STOP_EXIT, yoksa beklemeye alınır —
fake fiyat yok), tek açılış yolu `attempt_open` (duplicate/scale-in politikası,
router+worker ortak), learning handoff alanları, API/dashboard additive.
**393 pytest**, ruff CI-scope + tsc + pnpm build yeşil. Commit:
`feat(paper): finalize lifecycle and audit trail`.

> Backend bitirme modu — **yeni veri kaynağı / dashboard redesign / mimari katman
> EKLENMEZ.** Mevcut state'i doğru ve dürüst göster.

## L1 — Learning loop finalization

Paper lifecycle artık sağlam ve audit edilebilir. Şimdi learning loop'un gerçek
paper outcome'dan **dürüst** öğrenmeye hazır hale gelmesi gerekiyor.

Amaç (kapsam — görev başında baseline audit ile netleştir):
- **Outcome record normalization**: kapanan paper trade'lerden tek canonical
  outcome record (trade_id / symbol / timeframe / opened_at / closed_at /
  duration / open_price / close_price / pnl / pnl_pct / direction / open_reason /
  close_reason / fingerprint / regime / dominant_module / candidate_action /
  final_action / blocked_by-gates_applied / snapshot_id-decision_id /
  data_verified / source_quality / paper_only=true). Legacy kayıtlar default
  field'lerle çalışmalı.
- **Timeframe-aware learning**: 15m trade hatası 1d sistemini cezalandırmaz.
  Learning stats by symbol / timeframe / regime / dominant_module / close_reason /
  gate attribution.
- **Mistake memory**: outcome record'dan beslenir; benzer hataları same symbol /
  timeframe / regime-fingerprint üzerinden görür.
- **Calibration**: yeterli sample varsa kullanır, yoksa identity fallback;
  DQS/verified=false kayıtlar calibration'a girmez.
- **Auto-weight trainer**: yalnızca verified closed outcomes; minimum sample
  guard; **owner approval olmadan active weights değişmez**; timeframe/regime
  attribution kaybolmaz.
- **Learning worker**: düzenli çalışabilir (run_id / started_at / completed_at /
  status / generated_proposals / skipped_reason); boş veride crash yok.
- **API/dashboard additive**: sample sufficiency / outcomes by timeframe /
  mistake memory candidates / calibration status / weight proposal status /
  worker last run. Mevcut LearningPanel'e minimum additive; büyük redesign yok.

## Hard rules (değişmez)
- PAPER_SAFE / NO_EXECUTION; broker yok, gerçek emir yok, live execution yok.
- RiskGate / DQS / KillSwitch / halt yalnızca kısıtlayıcı; bypass/gevşetme yok.
- Learning, active weights'i **owner approval olmadan değiştirmez**.
- LLM karar vermez / karar motoruna bağlanmaz. Endpoint path + response alan
  adları sabit (additive ok).
- Runtime'da mock yok; testlerde live network yok. Look-ahead / sahte geçmiş yok.
- Unverified / DQS-false records öğrenmeye girmez.

## Tests (mutlaka)
- closed paper trade → canonical outcome
- 15m outcome 1d bucket'ını etkilemez
- unverified record ignored
- insufficient sample → no proposal
- enough verified samples → proposal generated
- owner approval required
- calibration identity fallback
- mistake memory by timeframe
- learning worker empty data no crash
- contract/codegen drift green
- no live network dependency

## Validation
- `pytest -q` (narrow → full; runtime state izole — `RISK_HALT_PATH` /
  `PAPER_STATE_PATH` / `PAPER_AUDIT_PATH` / `SNAPSHOT_STORE_PATH` temp dizine al,
  aksi halde live-smoke artığı halt testleri kırar)
- ruff CI scope: `ruff check packages apps/api apps/tick_worker apps/learning_worker tests/contract`
- `cd apps/web && pnpm tsc --noEmit && pnpm build`
- live smoke: `/health`, `/paper-trading/state`, `/learning/summary` (veya mevcut
  learning endpointleri), `/cockpit/brief`, web SSR 200
- codegen/contract drift yeşil

Commit (P1 commit'ine dokunma): `feat(learning): finalize outcome learning loop`
