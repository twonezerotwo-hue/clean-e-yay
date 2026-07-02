"""Learning worker — periyodik kalibrasyon + walk-forward + auto-weight proposal.

L1 — her koşu run metadata üretir (run_id / status / skipped_reason /
outcomes_seen / proposals_generated / calibration_status / errors). Boş veri →
NO_DATA; beklenmedik hata → COMPLETED_WITH_ERRORS (worker ASLA patlamaz).
active weights owner approval olmadan DEĞİŞMEZ.

Çalıştırma:
    python -m apps.learning_worker.main
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from packages.learning import auto_weight_trainer as trainer
from packages.learning import (
    calibration_trainer,
    edge_report,
    guard_safety,
    rebalance_store,
    run_store,
    tf_calibration,
    tf_target_rollback,
    tf_target_store,
    tf_target_trainer,
    tf_weight_trainer,
    threshold_trainer,
    weight_rollback,
)
from packages.learning import (
    outcomes as outcomes_mod,
)
from packages.learning.summary import build_summary
from packages.ops import heartbeat

log = logging.getLogger("learning_worker")

WORKER_NAME = "learning_worker"

# Learning run status → heartbeat status eşlemesi.
_HB_STATUS = {
    "COMPLETED": "OK",
    "COMPLETED_WITH_ERRORS": "DEGRADED",
    "NO_DATA": "NO_DATA",
}

OUT_PATH = Path(os.environ.get("LEARNING_OUT_PATH", "data/runtime/learning_summary.json"))
TF_CALIBRATION_OUT_PATH = Path(
    os.environ.get("TF_CALIBRATION_OUT_PATH", "data/runtime/tf_calibration.json")
)
TF_WEIGHT_PROPOSAL_OUT_PATH = Path(
    os.environ.get("TF_WEIGHT_PROPOSAL_OUT_PATH", "data/runtime/tf_weight_proposal.json")
)
TF_TARGET_PROPOSAL_OUT_PATH = Path(
    os.environ.get("TF_TARGET_PROPOSAL_OUT_PATH", "data/runtime/tf_target_proposal.json")
)
# Son tf_target çalışmasının dataset_size'ını burada tutuyoruz; bir sonraki
# döngüde yalnızca outcomes_seen bundan ≥ TF_TARGET_MIN_NEW kadar arttıysa
# trainer'ı tekrar çağırıyoruz (örnek-kapılı tetik). Periyodik kısım loop'un
# kendisi (her gecelik koşu).
TF_TARGET_TRIGGER_PATH = Path(
    os.environ.get("TF_TARGET_TRIGGER_PATH", "data/runtime/tf_target_trigger.json")
)
TF_TARGET_MIN_NEW = int(os.environ.get("TF_TARGET_MIN_NEW", "20"))


def _tf_target_edge_gate_on() -> bool:
    """CP4 slice 2 — edge-gate + rollback flag'i. Default OFF → geometri auto-apply
    eski davranışla (gate'siz) çalışır, bayt-aynı. AÇIK iken: band-içi nudge'lar yalnız
    `edge_report.safe_to_autotune` STABLE iken otomatik uygulanır + her auto-apply
    outcome-rollback ile izlenir (kötüleşirse geri alınır)."""
    return os.environ.get("TF_TARGET_EDGE_GATE", "0").strip().lower() not in {
        "0", "false", "no", "off", ""
    }
# CP1 — performans bütçesi: learning koşusu bu süreyi aşarsa WARN + run meta'da
# over_budget=True. Tick'e dokunmaz; yalnız off-tick learning loop'unu izler ki
# yeni öğrenici eklendikçe sistem sessizce AĞIRLAŞMASIN (ana kural).
LEARNING_BUDGET_MS = int(os.environ.get("LEARNING_BUDGET_MS", "60000"))


def _tf_target_should_run(outcomes_seen: int) -> tuple[bool, int]:
    """Örnek-kapılı tetik: son çalıştırmadan beri ≥TF_TARGET_MIN_NEW yeni outcome
    biriktiyse True. İlk çalıştırma (state yoksa) True. (gate, last_seen)."""
    try:
        if TF_TARGET_TRIGGER_PATH.exists():
            data = json.loads(TF_TARGET_TRIGGER_PATH.read_text(encoding="utf-8"))
            last = int(data.get("last_outcomes_seen", 0))
            return (outcomes_seen - last >= TF_TARGET_MIN_NEW, last)
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return True, 0


def _tf_target_save_trigger(outcomes_seen: int) -> None:
    try:
        TF_TARGET_TRIGGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        TF_TARGET_TRIGGER_PATH.write_text(
            json.dumps({"last_outcomes_seen": outcomes_seen,
                        "updated_at": datetime.now(UTC).isoformat()}, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def run_once() -> dict:
    """Tek learning koşusu; run metadata döner + run_store'a yazar."""
    run_id = uuid.uuid4().hex[:12]
    started_at = datetime.now(UTC).isoformat()
    t0 = time.monotonic()
    errors: list[str] = []
    proposals_generated = 0
    calibration_status = "UNKNOWN"
    tf_calibration_status = "UNKNOWN"
    tf_weights_trusted = False
    tf_weight_proposal_status = "UNKNOWN"
    skipped_reason: str | None = None
    rebalance_decision: str | None = None  # G3: auto_applied | pending_* | no_change
    rollback_status = "UNKNOWN"             # G3: no_active | monitoring | CONFIRMED | ROLLED_BACK
    guard_safety_status: dict = {}          # CP3: yön guard kasası (armed/rolled_back/...)

    try:
        outcomes_seen = len(outcomes_mod.outcomes_from_state())
    except Exception as exc:  # defensive — worker patlamamalı
        outcomes_seen = 0
        errors.append(f"outcomes:{type(exc).__name__}")

    # Özet (boş state'te de güvenli — total=0).
    try:
        summary = build_summary()
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        log.info(
            "learning_summary written: total=%s win_rate=%s sharpe=%s",
            summary.get("total_trades"),
            summary.get("win_rate"),
            summary.get("sharpe"),
        )
    except Exception as exc:  # defensive
        errors.append(f"summary:{type(exc).__name__}")

    # G6: confidence calibration. Yetersiz veri → identity (a=1, b=0).
    try:
        cal = calibration_trainer.train()
        calibration_status = str(cal.get("status", "UNKNOWN"))
        # F4-1 — per-TF Platt gözlemi: hangi TF'ler fit edildi (aktivasyon kanıtı).
        log.info(
            "calibration: %s n=%s tf_fitted=%s",
            calibration_status, cal.get("samples"), cal.get("tf_fitted") or [],
        )
    except Exception as exc:  # defensive
        errors.append(f"calibration:{type(exc).__name__}")

    # Step 8 — per-TF calibration + tf_weights trust gate. Derives per-timeframe
    # hit-rate/expectancy from VERIFIED outcomes and the trust verdict (PRIOR until a
    # TF has enough evidence). Persisted as a durable artifact so the trust gate reads
    # a stable as-of-last-run verdict. Attribution-based weight AUTO-TUNE stays deferred
    # (no faking): this lands the honest calibration + trust gate, not weight moves.
    try:
        tf_report = tf_calibration.calibration_report()
        tf_weights_trusted = bool(tf_report.get("tf_weights_trusted", False))
        tf_calibration_status = "TRUSTED" if tf_weights_trusted else "PRIOR"
        TF_CALIBRATION_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        TF_CALIBRATION_OUT_PATH.write_text(
            json.dumps(tf_report, indent=2, default=str), encoding="utf-8"
        )
        log.info(
            "tf_calibration: %s trusted_tfs=%s",
            tf_calibration_status,
            tf_report.get("calibrated_timeframes"),
        )
    except Exception as exc:  # defensive — worker patlamamalı
        errors.append(f"tf_calibration:{type(exc).__name__}")

    # Step 8 — tf_weights auto-tune PROPOSAL (trust-gated). Owner approves; live weights
    # are NEVER auto-moved here. Until a TF is calibrated this skips (the normal state).
    try:
        proposal = tf_weight_trainer.propose()
        if isinstance(proposal, tf_weight_trainer.TfWeightProposal):
            tf_weight_proposal_status = "PROPOSED"
            payload = tf_weight_trainer.proposal_to_dict(proposal)
        else:
            tf_weight_proposal_status = str(proposal.get("reason", "skipped"))
            payload = proposal
        TF_WEIGHT_PROPOSAL_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        TF_WEIGHT_PROPOSAL_OUT_PATH.write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        log.info("tf_weight proposal: %s", tf_weight_proposal_status)
    except Exception as exc:  # defensive — worker patlamamalı
        errors.append(f"tf_weight:{type(exc).__name__}")

    # TF-target trainer (Faz B): TF başına SL/TP geometri nudge önerisi. Hibrit
    # uygulama — tf_target_store dar bantta auto, dışında PENDING. Tetik örnek-
    # kapılı: son koşudan beri ≥TF_TARGET_MIN_NEW yeni outcome biriktiyse çalışır.
    tf_target_status = "SKIPPED"
    tf_target_decisions: dict[str, str] = {}
    try:
        should_run, last_seen = _tf_target_should_run(outcomes_seen)
        if not should_run:
            tf_target_status = (
                f"GATE_PENDING (have={outcomes_seen} last={last_seen} "
                f"need_new>={TF_TARGET_MIN_NEW})"
            )
            log.info("tf_target_trainer: %s", tf_target_status)
        else:
            tt_result = tf_target_trainer.train(
                store_overrides=tf_target_store.active_overrides()
            )
            if isinstance(tt_result, tf_target_trainer.TfTargetProposal):
                payload = tf_target_trainer.proposal_to_dict(tt_result)
                if tt_result.per_timeframe:
                    # Trainer önerdiyse store hibrit kapısından geçir.
                    baseline = {
                        tf: tf_target_trainer._baseline_for_tf(
                            tf, tf_target_store.active_overrides()
                        )
                        for tf in tt_result.per_timeframe
                    }
                    # CP4 slice 2 edge-gate: flag açıksa band-içi nudge'lar yalnız
                    # edge STABLE iken auto-apply edilir (UNSTABLE → gated_pending).
                    # Flag OFF (default) → allowed=True, eski davranış birebir.
                    gate_on = _tf_target_edge_gate_on()
                    auto_allowed = True
                    if gate_on:
                        auto_allowed = bool(edge_report.report().get("safe_to_autotune"))
                    rec = tf_target_store.submit_proposal(
                        payload, current_baseline=baseline,
                        auto_apply_allowed=auto_allowed,
                    )
                    tf_target_decisions = dict(rec.get("decisions") or {})
                    tf_target_status = "PROPOSED"
                    # Gate açık + gerçekten auto-apply olduysa rollback'e al (tek aktif
                    # izleme; mevcut izleme bitmeden yenisini başlatma).
                    applied = rec.get("applied_changes") or {}
                    if gate_on and applied and tf_target_rollback.get_active() is None:
                        base_n, base_exp = weight_rollback.pre_apply_expectancy()
                        tf_target_rollback.record_apply(
                            prev_overrides=applied,
                            applied_tfs=list(applied.keys()),
                            baseline_expectancy=base_exp,
                            baseline_n=base_n,
                        )
                else:
                    tf_target_status = "NO_NUDGE"
                TF_TARGET_PROPOSAL_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
                TF_TARGET_PROPOSAL_OUT_PATH.write_text(
                    json.dumps(payload, indent=2, default=str), encoding="utf-8"
                )
            else:
                tf_target_status = str(tt_result.get("status", "UNKNOWN"))
            _tf_target_save_trigger(outcomes_seen)
            log.info("tf_target_trainer: %s decisions=%s",
                     tf_target_status, tf_target_decisions)
    except Exception as exc:  # defensive — worker patlamamalı
        errors.append(f"tf_target:{type(exc).__name__}")

    # G2/G3: auto-weight trainer. Yeterli veri varsa proposal üretilir. G3 hibrit:
    # dar bant (|delta| ≤ REBALANCE_AUTO_APPLY_BAND) + auto-apply açık ise OTOMATİK
    # uygulanır; aksi halde PENDING (owner). API propose/approve yolu ETKİLENMEZ.
    # F3-2: WEIGHT_REGIME_FILTER açıkken hedef = en son kapanan verified
    # outcome'un rejimi (verisi en son değişen rejim); kapalıyken NEUTRAL (eski).
    try:
        train_regime = "NEUTRAL"
        if trainer.regime_filter_enabled():
            train_regime = trainer.latest_outcome_regime() or "NEUTRAL"
            log.info("regime-filtered training target: %s", train_regime)
        result = trainer.train(regime=train_regime)
        if isinstance(result, trainer.RebalanceProposal):
            # Baseline = apply öncesi EŞLEŞTİRİLMİŞ pencere (opened_at'e göre en son
            # N verified outcome) — post-apply penceresiyle aynı boyut/recency.
            # Ömür-boyu ortalama DEĞİL: rollback like-for-like kıyas yapabilsin.
            base_n, base_exp = weight_rollback.pre_apply_expectancy()
            decision = rebalance_store.maybe_auto_apply(
                trainer.proposal_to_dict(result),
                baseline_expectancy=base_exp,
                baseline_n=base_n,
            )
            rebalance_decision = str(decision.get("decision"))
            proposals_generated = 1
            log.info(
                "rebalance proposal %s: %s → %s (n=%s)",
                rebalance_decision,
                result.from_version,
                result.to_version,
                result.dataset_size,
            )
        else:
            skipped_reason = result.get("reason")
            log.info("rebalance trainer skipped: %s", result)
    except Exception as exc:  # defensive
        errors.append(f"trainer:{type(exc).__name__}")

    # G3: otomatik-uygulanan ağırlık için outcome-bazlı rollback denetimi. İzlenen
    # apply yoksa no_active; yeterli yeni outcome birikince CONFIRMED/ROLLED_BACK.
    try:
        rb = weight_rollback.check_rollback()
        rollback_status = str(rb.get("status", "UNKNOWN"))
        if rollback_status == "ROLLED_BACK":
            log.info(
                "weight ROLLBACK: %s → %s (post_exp=%s < baseline=%s)",
                rb.get("reverted_from"),
                rb.get("reverted_to"),
                rb.get("post_expectancy"),
                rb.get("baseline_expectancy"),
            )
        elif rollback_status == "CONFIRMED":
            log.info("weight auto-apply CONFIRMED: %s", rb.get("confirmed_version"))
    except Exception as exc:  # defensive — worker patlamamalı
        errors.append(f"rollback:{type(exc).__name__}")

    # CP4 slice 2: otomatik-uygulanan TF-target (SL/TP geometri) için outcome-bazlı
    # rollback. İzlenen apply yoksa no_active; yeterli yeni outcome birikince
    # geometri CONFIRMED ya da önceki değerine ROLLED_BACK olur.
    try:
        gb = tf_target_rollback.check_rollback()
        gb_status = str(gb.get("status", "UNKNOWN"))
        if gb_status == "ROLLED_BACK":
            log.info(
                "tf_target ROLLBACK: %s (post_exp=%s < baseline=%s)",
                gb.get("reverted_tfs"), gb.get("post_expectancy"),
                gb.get("baseline_expectancy"),
            )
        elif gb_status == "CONFIRMED":
            log.info("tf_target auto-apply CONFIRMED: %s", gb.get("confirmed_tfs"))
    except Exception as exc:  # defensive — worker patlamamalı
        errors.append(f"tf_target_rollback:{type(exc).__name__}")

    # CP4 (final): otonom eşik trainer. THRESHOLD_AUTOTUNE açıkken allowlist eşikleri
    # backtest-doğrulamayla dar-bant oto-uygular (edge STABLE + iyileşme şartı);
    # rollback ayrı denetlenir. Flag OFF → DISABLED (no-op). Rollback her koşuda.
    try:
        tt = threshold_trainer.train()
        if tt.get("status") == "APPLIED":
            log.info("threshold AUTO-APPLIED: %s", tt.get("evaluated"))
        tr = threshold_trainer.check_rollback()
        if tr.get("status") == "ROLLED_BACK":
            log.info("threshold ROLLBACK: %s (post_exp=%s < baseline=%s)",
                     tr.get("path"), tr.get("post_expectancy"), tr.get("baseline_expectancy"))
        elif tr.get("status") == "CONFIRMED":
            log.info("threshold auto-apply CONFIRMED: %s", tr.get("path"))
    except Exception as exc:  # defensive — worker patlamamalı
        errors.append(f"threshold_trainer:{type(exc).__name__}")

    # CP3: yön güvenlik kasası. Owner bir guard'ı canlıya aldıysa izlemeye alır;
    # yeterli yeni outcome birikince post-enable expectancy baseline'ın altına
    # düşerse guard'ı oto-kapatır (kill-override). Geçiş yoksa sessiz (no-op).
    try:
        guard_safety_status = guard_safety.run()
        if guard_safety_status.get("armed"):
            log.info("guard_safety ARMED: %s", guard_safety_status["armed"])
        if guard_safety_status.get("rolled_back"):
            log.info("guard_safety ROLLBACK: %s", guard_safety_status["rolled_back"])
    except Exception as exc:  # defensive — worker patlamamalı
        errors.append(f"guard_safety:{type(exc).__name__}")

    if errors:
        status = "COMPLETED_WITH_ERRORS"
    elif outcomes_seen == 0:
        status = "NO_DATA"
        skipped_reason = "no_closed_outcomes"  # net NO_DATA nedeni
    else:
        status = "COMPLETED"  # skipped_reason trainer'dan (örn. below_min_total)

    # CP1 — perf bütçesi denetimi (off-tick; sistem ağırlaşmasın diye erken uyarı).
    duration_ms = int((time.monotonic() - t0) * 1000)
    over_budget = duration_ms > LEARNING_BUDGET_MS
    if over_budget:
        log.warning(
            "learning run over budget: %dms > %dms (bütçe)", duration_ms, LEARNING_BUDGET_MS
        )

    run = {
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "status": status,
        "skipped_reason": skipped_reason,
        "outcomes_seen": outcomes_seen,
        "proposals_generated": proposals_generated,
        "rebalance_decision": rebalance_decision,  # G3
        "rollback_status": rollback_status,          # G3
        "guard_safety_status": guard_safety_status,  # CP3

        "calibration_status": calibration_status,
        "tf_calibration_status": tf_calibration_status,
        "tf_weights_trusted": tf_weights_trusted,
        "tf_weight_proposal_status": tf_weight_proposal_status,
        "tf_target_status": tf_target_status,
        "tf_target_decisions": tf_target_decisions,
        "duration_ms": duration_ms,        # CP1 — perf görünürlüğü
        "over_budget": over_budget,        # CP1 — bütçe aşımı bayrağı
        "errors": errors,
    }
    run_store.save(run)
    # O1 — heartbeat (system/health stale tespiti). Boş veri NO_DATA = "alive".
    heartbeat.record(
        WORKER_NAME,
        status=_HB_STATUS.get(status, "OK"),
        run_id=run_id,
        started_at=started_at,
        completed_at=run["completed_at"],
        last_error="; ".join(errors) if errors else None,
        learning_outcomes_seen=outcomes_seen,
        proposals_generated=proposals_generated,
        duration_ms=duration_ms,
    )
    return run


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run_once()
