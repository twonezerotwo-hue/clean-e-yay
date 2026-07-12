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

from packages import discovery
from packages.discovery import sector_rotation
from packages.learning import (
    activation_watchdog,
    calibration_trainer,
    edge_report,
    empirical_pwin,
    exit_forensics,
    guard_safety,
    promotion_criteria,
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
from packages.learning import auto_weight_trainer as trainer
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
    promotion_status = "UNKNOWN"            # F5-2: terfi kriteri (READY/NOT_READY)
    activation_watchdog_status: dict = {}   # F5-3: owner-flag izleyici (yalnız-öneri)

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

    # F4-2 — ampirik p(win) tablosu: (tf|rejim) hit-rate artifact'ı. Karar
    # motoru okur (flag kapalıyken salt-gözlem alanları için).
    try:
        emp_table = empirical_pwin.write_table()
        log.info(
            "empirical_pwin: cells=%s sufficient=%s",
            emp_table.get("cell_count"), emp_table.get("sufficient_count"),
        )
    except Exception as exc:  # defensive — worker patlamamalı
        errors.append(f"empirical_pwin:{type(exc).__name__}")

    # Çıkış Otopsisi (denetim 2026-07-03) — kötü çıkışın nerede/kaça olduğu
    # (AUTO kohort, observe-only). Snapshot + trend geçmişi; panel/API okur.
    exit_forensics_status = "SKIPPED"
    try:
        ef = exit_forensics.write_snapshot()
        ef_latest = ef.get("latest") or {}
        exit_forensics_status = "OK"
        log.info(
            "exit_forensics: usable=%s buckets=%s top_costs=%s",
            ef_latest.get("usable"),
            len(ef_latest.get("buckets") or []),
            len(ef_latest.get("top_costs") or []),
        )
    except Exception as exc:  # defensive — worker patlamamalı
        exit_forensics_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"exit_forensics:{type(exc).__name__}")

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

    # F5-2 — champion/challenger terfi kriteri: her cycle değerlendirilir; READY
    # olursa governor defterine OWNER ONAY PAKETİ sunulur (dedupe'lu — tek PENDING).
    # Terfi otomatik DEĞİL (KIRMIZI ÇİZGİ); onay bile canlı config'i değiştirmez.
    try:
        promo = promotion_criteria.run()
        promotion_status = promo.get("status", "UNKNOWN")
        if promotion_status == "READY":
            log.info(
                "promotion_criteria READY — owner paketi sunuldu (proposal_id=%s)",
                promo.get("proposal_id"),
            )
    except Exception as exc:  # defensive — worker patlamamalı
        promotion_status = "UNKNOWN"
        errors.append(f"promotion_criteria:{type(exc).__name__}")

    # F5-3 — aktivasyon watchdog'u: owner-flag OFF→ON geçişlerini izler,
    # post-enable expectancy düşerse DEGRADED önerir (YALNIZ-ÖNERİ — hiçbir
    # flag'i oto-kapatmaz; yön guard'larının oto-kapatlı kasası yukarıda).
    try:
        aw = activation_watchdog.run()
        activation_watchdog_status = aw
        if aw.get("armed"):
            log.info("activation_watchdog ARMED: %s", aw["armed"])
        if aw.get("degraded"):
            log.info("activation_watchdog DEGRADED (öneri): %s", aw["degraded"])
    except Exception as exc:  # defensive — worker patlamamalı
        activation_watchdog_status = {}
        errors.append(f"activation_watchdog:{type(exc).__name__}")

    # K-0b — keşif: sektör rotasyon motoru (DISCOVERY_SCAN_ENABLED, default
    # OFF → tam no-op: ağa çıkmaz, dosya yazmaz, learning koşusu bayt-eşdeğer).
    # Açıkken saatte bir (interval_sec) 12 sektör ETF'sinin S&P'ye göreli gücünü
    # ölçer + karne damgası/çözümü; canlı karar zincirine dokunmaz (salt-gözlem).
    discovery_status = "DISABLED"
    try:
        if discovery.scan_enabled():
            sr = sector_rotation.run_if_due()
            discovery_status = str(sr.get("status", "UNKNOWN"))
            if discovery_status == "OK":
                log.info(
                    "sector_rotation: rising=%s unavailable=%s stamped=%s resolved_new=%s",
                    sr.get("rising"), sr.get("unavailable_n"),
                    sr.get("stamped"), sr.get("resolved_new"),
                )
    except Exception as exc:  # defensive — worker patlamamalı
        discovery_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"sector_rotation:{type(exc).__name__}")

    # K-1 — keşif tarayıcısı (aynı flag): kota kadar adayı (sıcak sektör ETF'leri
    # + kripto kısa listesi) gölge analiz eder, yalnız artifact yazar. İşlem
    # AÇMAZ; RiskGate'e girmez. Import lazy — flag kapalıyken decision-engine
    # bağımlılıkları hiç yüklenmez (bayt-eşdeğer koşu).
    discovery_scan_status = "DISABLED"
    try:
        if discovery.scan_enabled():
            from packages.discovery import scanner as discovery_scanner
            sc = discovery_scanner.run_if_due()
            discovery_scan_status = str(sc.get("status", "UNKNOWN"))
            if discovery_scan_status == "OK":
                log.info(
                    "discovery_scan: scanned=%s signals=%s candidates=%s shadow=%s",
                    sc.get("scanned"), sc.get("signals_n"),
                    sc.get("candidates_total"), sc.get("shadow"),
                )
    except Exception as exc:  # defensive — worker patlamamalı
        discovery_scan_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"discovery_scan:{type(exc).__name__}")

    # K-4 — keşif adayı TERFİ kriteri (aynı DISCOVERY_SCAN_ENABLED kapısı):
    # tarayıcı+defter tazelendikten SONRA aday gölge karnesini üç eşiğe (≥20
    # çözüm + ≥2 TF + Wilson alt sınırı > 0.5) vurur; geçen aday için governor
    # defterine STRATEGY_ENABLE paketi (add_custom_asset, dedupe'lu). Varlık
    # OTOMATİK EKLENMEZ — onay bile canlı evreni değiştirmez (KIRMIZI ÇİZGİ).
    discovery_promotion_status = "DISABLED"
    try:
        if discovery.scan_enabled():
            from packages.discovery import promotion as discovery_promotion
            dp = discovery_promotion.run()
            discovery_promotion_status = str(dp.get("status", "UNKNOWN"))
            if discovery_promotion_status == "READY":
                log.info(
                    "discovery_promotion READY — owner paketi sunuldu "
                    "(ready=%s proposal_ids=%s)",
                    dp.get("ready_symbols"), dp.get("proposal_ids"),
                )
    except Exception as exc:  # defensive — worker patlamamalı
        discovery_promotion_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"discovery_promotion:{type(exc).__name__}")

    # B-1 — geçmiş çok-modül yeniden-kurma sadakat (fidelity) kontrolü. Flag
    # BACKTEST_RECON_ENABLED OFF → tam no-op. SALT-ÖLÇÜM/İZOLE: canlı outcome
    # defterine/ağırlığa temas etmez, yalnız fidelity artifact'ı yazar. Import
    # lazy — flag kapalıyken decision/consensus bağımlılıkları yüklenmez.
    backtest_recon_status = "DISABLED"
    try:
        from packages.learning import backtest_recon
        if backtest_recon.enabled():
            fr = backtest_recon.fidelity_report()
            backtest_recon_status = str(fr.get("verdict", "UNKNOWN"))
            log.info(
                "backtest_recon: verdict=%s quantum_delta=%s",
                backtest_recon_status, fr.get("quantum_delta"),
            )
    except Exception as exc:  # defensive — worker patlamamalı
        backtest_recon_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"backtest_recon:{type(exc).__name__}")

    # B-2 — rejim-çeşitli outcome üretimi (İZOLE challenger kanalı). Flag
    # BACKTEST_CHALLENGER_ENABLED OFF → tam no-op. B-1 fidelity'den AYRI flag
    # (üretim ağır: 1-2 yıl yürür). INTERVAL-kapılı (her cycle değil). Canlı
    # outcome defterine/ağırlığa/paper'a ASLA yazmaz — yalnız challenger artifact.
    backtest_challenger_status = "DISABLED"
    try:
        from packages.learning import backtest_recon as _br_prod
        if _br_prod.challenger_enabled():
            bc = _br_prod.run_if_due()
            backtest_challenger_status = str(bc.get("status", "UNKNOWN"))
            if backtest_challenger_status == "OK":
                log.info(
                    "backtest_challenger: records=%s regimes=%s labels=%s fred_liq=%s",
                    bc.get("records"), bc.get("regime_histogram"),
                    bc.get("label_histogram"), bc.get("fred_liquidity"),
                )
    except Exception as exc:  # defensive — worker patlamamalı
        backtest_challenger_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"backtest_challenger:{type(exc).__name__}")

    # B-3 — challenger ağırlık eğitimi + quantum ayrım karnesi (cat 6). AYNI
    # BACKTEST_CHALLENGER_ENABLED kapısı (challenger boru hattı tek şey): B-2
    # üretiminden SONRA jsonl'i okur → rejim başına challenger ağırlık (canlı
    # trainer matematiği reuse) + quantum karnesi, İZOLE rapora. Canlı ağırlığa/
    # config'e ASLA yazmaz (owner terfi = B-4, kırmızı çizgi). Ucuz (jsonl okur).
    challenger_train_status = "DISABLED"
    try:
        from packages.learning import backtest_recon as _br_gate
        if _br_gate.challenger_enabled():
            from packages.learning import challenger_trainer
            ct = challenger_trainer.run()
            challenger_train_status = str(ct.get("status", "UNKNOWN"))
            if challenger_train_status == "OK":
                log.info(
                    "challenger_trainer: proposed_regimes=%s quantum=%s",
                    ct.get("proposed_regimes"),
                    (ct.get("quantum_scorecard") or {}).get("summary"),
                )
    except Exception as exc:  # defensive — worker patlamamalı
        challenger_train_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"challenger_trainer:{type(exc).__name__}")

    # B-4 — challenger ağırlık TERFİ kriteri (owner ÖNERİ; KIRMIZI ÇİZGİ). AYNI
    # BACKTEST_CHALLENGER_ENABLED kapısı: B-3 eğitimden SONRA challenger ağırlık
    # setlerini champion'a karşı EŞLEŞMELİ kıyaslar (kayıtları yeniden-harmanlar);
    # üç kriter tutarsa governor defterine STRATEGY_ENABLE paketi sunar (dedupe'lu,
    # tek PENDING). Ağırlık terfisi OTOMATİK DEĞİL — onay bile canlı ağırlığı
    # değiştirmez (owner-gated rebalance ayrı). Ucuz (jsonl okur + yeniden-harman).
    challenger_promotion_status = "DISABLED"
    try:
        from packages.learning import backtest_recon as _br_promo
        if _br_promo.challenger_enabled():
            from packages.learning import challenger_promotion
            cp = challenger_promotion.run()
            challenger_promotion_status = str(cp.get("status", "UNKNOWN"))
            if challenger_promotion_status == "READY":
                log.info(
                    "challenger_promotion READY — owner paketi sunuldu "
                    "(proposal_id=%s challenger_wins=%s/%s regimes=%s)",
                    cp.get("proposal_id"),
                    cp.get("challenger_wins"),
                    cp.get("challenger_wins", 0) + cp.get("champion_wins", 0),
                    cp.get("proposed_regimes"),
                )
    except Exception as exc:  # defensive — worker patlamamalı
        challenger_promotion_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"challenger_promotion:{type(exc).__name__}")

    # Y-1 — rejim risk freni tablosu (SALT-GÖZLEM üretim; uygulama engine'de
    # `regime_risk_brake.enabled` flag'iyle, DEFAULT OFF). Kanıt çift kaynak:
    # canlı AUTO kohort + backtest challenger (İKİSİ de negatif + min örnek →
    # fren). Ucuz (state + jsonl okur). Artifact bayatlarsa (max_age_hours)
    # fren sıcak yolda kendiliğinden düşer — öğrenme durursa tik bağımsız kalır.
    regime_brake_status = "ERROR"
    try:
        from packages.learning import regime_risk_brake as _rrb
        rb = _rrb.compute()
        regime_brake_status = "OK"
        if rb.get("braked_regimes"):
            log.info(
                "regime_risk_brake: braked=%s enabled=%s",
                rb.get("braked_regimes"), rb.get("enabled"),
            )
    except Exception as exc:  # defensive — worker patlamamalı
        regime_brake_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"regime_risk_brake:{type(exc).__name__}")

    # Y-5 — meta-label kapısı bariyer-tarihçe tablosu (SALT-GÖLGE; motor hükmü
    # karara uygulamaz). Off-tick: AUTO kohort outcome'larından dominant×TF
    # kovası kalite skoru (Y-2 barrier_label REUSE). Ucuz (state okur).
    meta_gate_status = "ERROR"
    try:
        from packages.learning import meta_gate as _mg
        mg = _mg.compute()
        meta_gate_status = "OK"
        log.info("meta_gate: buckets=%s", len(mg.get("buckets") or {}))
    except Exception as exc:  # defensive — worker patlamamalı
        meta_gate_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"meta_gate:{type(exc).__name__}")

    # Y-6 — haber olay-çalışması (SALT-GÖZLEM). Off-tick: o anki verified haberleri
    # damgala (dedupe) + olgunlaşan olaylar için N-bar ileri-getiri karnesi
    # (ohlcv.history REUSE). Kanıt bar-arşivi gibi haftayla büyür; karara dokunmaz.
    news_study_status = "ERROR"
    try:
        from packages.learning import news_event_study as _nes
        recorded = _nes.record_events()
        nt = _nes.compute()
        news_study_status = "OK"
        log.info("news_event_study: +%s events, matured=%s verdict=%s",
                 recorded, nt.get("matured"), nt.get("global_verdict"))
    except Exception as exc:  # defensive — worker patlamamalı
        news_study_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"news_event_study:{type(exc).__name__}")

    # Çıkış stop-verim backtest'i (SALT-ANALİZ). AĞIR (binlerce entry × ızgara) →
    # interval-kapılı (haftalık; durum = artifact yaşı). Sabit+trailing stop için
    # en verimli aralığı gerçek OHLCV'den ölçer; canlı çıkışa dokunmaz.
    exit_backtest_status = "ERROR"
    try:
        from packages.learning import exit_backtest as _eb
        eb = _eb.run_if_due()
        exit_backtest_status = str(eb.get("status", "UNKNOWN"))
        if exit_backtest_status == "OK":
            log.info("exit_backtest: %s entries taranıp güncellendi", eb.get("entries"))
    except Exception as exc:  # defensive — worker patlamamalı
        exit_backtest_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"exit_backtest:{type(exc).__name__}")

    # 0-2 karnesi (SALT-ANALİZ, flag YOK — exit_backtest deseni). Owner'ın
    # Elliott 0-2 yöntemi (fitil/kırılım işlemleri + dalga-1/3 değme filtresi)
    # arşiv+canlı barlarda haftalık yeniden ölçülür; canlı karara dokunmaz.
    zero_two_scorecard_status = "ERROR"
    try:
        from packages.learning import zero_two_scorecard as _zts
        zt = _zts.run_if_due()
        zero_two_scorecard_status = str(zt.get("status", "UNKNOWN"))
        if zero_two_scorecard_status == "OK":
            log.info(
                "zero_two_scorecard: scanned=%s skipped_flat=%s",
                zt.get("scanned"), zt.get("skipped_flat"),
            )
    except Exception as exc:  # defensive — worker patlamamalı
        zero_two_scorecard_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"zero_two_scorecard:{type(exc).__name__}")

    # Yansıma/hafıza döngüsü (SALT-GÖZLEM, flag YOK — ucuz). Kapanan işlemlerden
    # ders çıkarıp izlenebilir digest yazar; karar hattına BAĞLI DEĞİL (enjeksiyon
    # ayrı owner adımı). TradingAgents deseninden alınan hafıza döngüsünün üretici
    # yarısı — mistake_memory'nin sayısal vetosuna DİK (anlatısal ders).
    reflection_status = "ERROR"
    try:
        from packages.learning import reflection as _refl
        rf = _refl.write_digest()
        reflection_status = str(rf.get("status", "UNKNOWN"))
        if reflection_status == "OK":
            log.info("reflection: %s ders", rf.get("total_lessons"))
    except Exception as exc:  # defensive — worker patlamamalı
        reflection_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"reflection:{type(exc).__name__}")

    # 0-2 TAM-STRATEJİ karnesi (SALT-ANALİZ, flag YOK). Owner'ın nihai LONG akışı
    # (0.618 giriş + fib hedef + 0-2 trailing + house-money re-giriş) arşiv+canlı
    # barlarda haftalık ölçülür; canlı karara dokunmaz (kanıt biriktirir).
    zero_two_strategy_status = "ERROR"
    try:
        from packages.learning import zero_two_strategy as _zts2
        zs = _zts2.run_if_due()
        zero_two_strategy_status = str(zs.get("status", "UNKNOWN"))
        if zero_two_strategy_status == "OK":
            log.info(
                "zero_two_strategy: scanned=%s cells=%s",
                zs.get("scanned"), zs.get("cells"),
            )
    except Exception as exc:  # defensive — worker patlamamalı
        zero_two_strategy_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"zero_two_strategy:{type(exc).__name__}")

    # Bölge-planı gölge yürütücüsü (SALT-ANALİZ, flag YOK — zero_two_strategy
    # deseni). Owner'ın el-çizimi kesişim bölgeleri (config/zone_plans.yaml) +
    # dallı işlem planı (parçalı giriş / BE / derin-ortalama / reclaim + LOG-fib
    # çıkış merdiveni) günlük barlarda gölge-yürütülür; canlı karara dokunmaz.
    # Plan dosyası boşsa NO_PLANS (tam no-op).
    zone_plan_status = "ERROR"
    try:
        from packages.learning import zone_plan_shadow as _zps
        zp = _zps.run_if_due()
        zone_plan_status = str(zp.get("status", "UNKNOWN"))
        if zone_plan_status == "OK":
            log.info("zone_plan_shadow: plans=%s states=%s",
                     zp.get("plans"), zp.get("states"))
    except Exception as exc:  # defensive — worker patlamamalı
        zone_plan_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"zone_plan_shadow:{type(exc).__name__}")

    # Konsey karnesi (SALT-ANALİZ, flag YOK). Katmanlar-arası kombinasyon
    # analizi: modül yayılımları + ikili çiftler + rejim/güven kırılımları +
    # veriden-türetilen sanki-filtreler. Owner 2026-07-12 elle analizinin
    # kalıcı hâli; canlı karara dokunmaz. Veri hijyeni içerde (legacy hariç).
    council_status = "ERROR"
    try:
        from packages.learning import council_scorecard as _cs
        cs_rep = _cs.run_if_due()
        council_status = str(cs_rep.get("status", "UNKNOWN"))
        if council_status == "OK":
            log.info("council_scorecard: n=%s", cs_rep.get("n"))
    except Exception as exc:  # defensive — worker patlamamalı
        council_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"council_scorecard:{type(exc).__name__}")

    # Aday bölge önericisi (SALT-ANALİZ, flag YOK — zone_plan_shadow deseni).
    # Owner'ın kesişim yöntemini makro evrende (rotasyon çekirdeği + ETF + keşif
    # kısa listesi) mekanik geometriyle serer (pivot→log-çizgi→log-fib→kesişim→
    # confluence) → aday bölge listesi. Makine bölge SEÇMEZ, ADAY önerir; owner
    # süzer, kabul edileni zone_plans.yaml'a taşır. Canlı karara dokunmaz.
    zone_proposer_status = "ERROR"
    try:
        from packages.learning import zone_proposer as _zpr
        zpr = _zpr.run_if_due()
        zone_proposer_status = str(zpr.get("status", "UNKNOWN"))
        if zone_proposer_status == "OK":
            log.info("zone_proposer: assets=%s with_zones=%s",
                     zpr.get("assets"), zpr.get("with_zones"))
    except Exception as exc:  # defensive — worker patlamamalı
        zone_proposer_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"zone_proposer:{type(exc).__name__}")

    # D5 — sinyal karnesi (SUBSIGNAL_SCORECARD_ENABLED, default OFF → tam no-op).
    # INTERVAL-kapılı (haftalık; durum = artifact yaşı): 8 sinyal × 4 TF ileri-
    # getiri karnesi (v2 sert cetvel) yeniden ölçülür — bar arşivi büyüdükçe
    # pencere kendiliğinden uzar. SALT-GÖZLEM: canlı skora/karara/paper'a yazmaz.
    # Import lazy — flag kapalıyken sinyal/vwap bağımlılıkları hiç yüklenmez.
    subsignal_scorecard_status = "DISABLED"
    try:
        from packages.learning import subsignal_scorecard
        if subsignal_scorecard.enabled():
            sc_rep = subsignal_scorecard.run_if_due()
            subsignal_scorecard_status = str(sc_rep.get("status", "UNKNOWN"))
            if subsignal_scorecard_status == "OK":
                log.info(
                    "subsignal_scorecard: timeframes=%s", sc_rep.get("timeframes")
                )
    except Exception as exc:  # defensive — worker patlamamalı
        subsignal_scorecard_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"subsignal_scorecard:{type(exc).__name__}")

    # D6 — tf_scoring_v2 GÖLGE (TF_SCORING_V2_SHADOW, default OFF → tam no-op).
    # Karne kanıtıyla (kanıt-cap ağırlık) katmanlı v2 yön skorunu CANLI barlar
    # üstünde üretir → "v2 şu an ne derdi" izole artifact. SALT-GÖZLEM: canlı
    # skora/karara/paper'a yazmaz (D7 yarışın girdisi). Lazy import — flag
    # kapalıyken skorlama bağımlılıkları yüklenmez (bayt-eşdeğer koşu).
    tf_scoring_v2_shadow_status = "DISABLED"
    try:
        from packages.learning import tf_scoring_shadow
        if tf_scoring_shadow.enabled():
            v2s = tf_scoring_shadow.run()
            tf_scoring_v2_shadow_status = str(v2s.get("status", "UNKNOWN"))
            if tf_scoring_v2_shadow_status == "OK":
                log.info(
                    "tf_scoring_v2_shadow: symbols_scored=%s", v2s.get("symbols_scored")
                )
    except Exception as exc:  # defensive — worker patlamamalı
        tf_scoring_v2_shadow_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"tf_scoring_v2_shadow:{type(exc).__name__}")

    # R5 — tf_scoring_v2 YARIŞ DEFTERİ (gölgeyle AYNI kapı: TF_SCORING_V2_SHADOW).
    # Gölge yönünü fiyat damgasıyla deftere yazar, ufuk dolan barları gerçekleşen
    # ileri-getiriyle çözer, yeni beyni eskiye/tabana karşı puanlar. Kriter tutarsa
    # governor'a OWNER ONAY paketi sunar — terfi OTOMATİK DEĞİL (KIRMIZI ÇİZGİ).
    # SALT-GÖZLEM: canlı skora/karara/paper'a yazmaz.
    tf_scoring_race_status = "DISABLED"
    try:
        from packages.learning import tf_scoring_race
        if tf_scoring_shadow.enabled():
            r5 = tf_scoring_race.run()
            tf_scoring_race_status = str(r5.get("status", "UNKNOWN"))
            if tf_scoring_race_status == "OK":
                log.info(
                    "tf_scoring_race: appended=%s ledger_rows=%s resolved=%s race=%s",
                    r5.get("appended"), r5.get("ledger_rows"),
                    r5.get("resolved"), r5.get("race_status"),
                )
    except Exception as exc:  # defensive — worker patlamamalı
        tf_scoring_race_status = f"ERROR:{type(exc).__name__}"
        errors.append(f"tf_scoring_race:{type(exc).__name__}")

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
        "promotion_status": promotion_status,        # F5-2 (READY/NOT_READY)
        "activation_watchdog_status": activation_watchdog_status,  # F5-3

        "calibration_status": calibration_status,
        "tf_calibration_status": tf_calibration_status,
        "tf_weights_trusted": tf_weights_trusted,
        "tf_weight_proposal_status": tf_weight_proposal_status,
        "tf_target_status": tf_target_status,
        "tf_target_decisions": tf_target_decisions,
        "exit_forensics_status": exit_forensics_status,  # Çıkış Otopsisi (2026-07-03)
        "discovery_status": discovery_status,  # K-0b sektör rotasyonu (DISABLED=flag OFF)
        "discovery_scan_status": discovery_scan_status,  # K-1 tarayıcı
        "discovery_promotion_status": discovery_promotion_status,  # K-4 terfi kriteri (DISABLED=flag OFF)
        "backtest_recon_status": backtest_recon_status,  # B-1 fidelity (DISABLED=flag OFF)
        "backtest_challenger_status": backtest_challenger_status,  # B-2 üretim (DISABLED=flag OFF)
        "challenger_train_status": challenger_train_status,  # B-3 ağırlık+quantum karne (DISABLED=flag OFF)
        "challenger_promotion_status": challenger_promotion_status,  # B-4 terfi kriteri (DISABLED=flag OFF)
        "regime_brake_status": regime_brake_status,  # Y-1 rejim risk freni tablosu (gözlem; uygulama flag'le)
        "meta_gate_status": meta_gate_status,  # Y-5 meta-label kapısı tablosu (SALT-GÖLGE)
        "news_study_status": news_study_status,  # Y-6 haber olay-çalışması karnesi (SALT-GÖZLEM)
        "exit_backtest_status": exit_backtest_status,  # Çıkış stop-verim backtest (interval-kapılı; SKIP_FRESH=taze)
        "zero_two_scorecard_status": zero_two_scorecard_status,  # 0-2 karnesi (owner edge'i; interval-kapılı SALT-ANALİZ)
        "zero_two_strategy_status": zero_two_strategy_status,  # 0-2 tam-strateji karnesi (0.618+fib+trailing+house-money; SALT-ANALİZ)
        "zone_plan_status": zone_plan_status,  # Bölge-planı gölge yürütücüsü (owner çizer, makine disiplini uygular; NO_PLANS=dosya boş)
        "zone_proposer_status": zone_proposer_status,  # Aday bölge önericisi (makine ADAY önerir, owner süzer; SALT-ANALİZ)
        "council_status": council_status,  # Konsey karnesi (katmanlar-arası kombinasyon; SALT-ANALİZ)
        "reflection_status": reflection_status,  # Yansıma/hafıza döngüsü (kapanan işlem dersleri; SALT-GÖZLEM)
        "subsignal_scorecard_status": subsignal_scorecard_status,  # D5 sinyal karnesi (DISABLED=flag OFF)
        "tf_scoring_v2_shadow_status": tf_scoring_v2_shadow_status,  # D6 v2 gölge skoru (DISABLED=flag OFF)
        "tf_scoring_race_status": tf_scoring_race_status,  # R5 yarış defteri (DISABLED=flag OFF)
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
