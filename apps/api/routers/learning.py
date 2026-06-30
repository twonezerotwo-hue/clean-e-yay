"""GET /api/v1/learning/{summary, calibration, mistakes}
POST /api/v1/learning/calibration/retrain
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from packages.data.registry.loader import load_thresholds
from packages.decision import conflict_gate, conflict_gate_backtest
from packages.learning import (
    book_audit,
    calibration_audit,
    calibration_store,
    calibration_trainer,
    dataset_health,
    historical_edge,
    missed_opportunity,
    mistake_memory,
    tf_target_store,
    tf_target_trainer,
    tf_weight_trainer,
)
from packages.learning import outcomes as outcomes_mod
from packages.learning.calibration import reliability_bins
from packages.learning.summary import build_summary
from packages.risk import trade_economics as te

router = APIRouter(tags=["learning"])


@router.get("/learning/summary")
def get_learning_summary() -> dict:
    return build_summary()


@router.get("/learning/calibration")
def get_calibration() -> dict:
    params = calibration_store.load()
    # Reliability bins — fit'le AYNI durable kaynak (recent_trades + decision_log).
    # Fit'i tekrar koşmaya gerek yok; sadece son örnekleri göster.
    samples = [
        (float(o.predicted_confidence), bool(o.pnl > 0))
        for o in outcomes_mod.outcomes_from_state()
        if o.data_verified and o.predicted_confidence is not None
    ]
    bins = [asdict(b) for b in reliability_bins(samples, n_bins=5)]
    return {
        "params": asdict(params),
        "min_required": calibration_store.MIN_SAMPLES,
        "samples_in_state": len(samples),
        "bins": bins,
    }


@router.post("/learning/calibration/retrain")
def post_retrain_calibration() -> dict:
    return calibration_trainer.train()


@router.get("/learning/tf-weights")
def get_tf_weights() -> dict:
    """Step 8 — per-TF calibration + the trust-gated tf_weights proposal (read-only).

    Owner-facing view: which timeframes are validated (CALIBRATED) and what weight
    changes the verified outcomes suggest. Informational — live weights are never
    moved here (owner approval, never auto-apply)."""
    return tf_weight_trainer.report_viewmodel()


@router.get("/learning/mistakes")
def get_mistakes() -> dict:
    mems = mistake_memory.summary()
    items = [asdict(m) for m in mems]
    # Verdict listesi (her fingerprint için)
    verdicts = []
    for m in mems:
        v = mistake_memory._verdict_for(m, m.fingerprint)
        verdicts.append(
            {
                "fingerprint": m.fingerprint,
                "action": v.action,
                "reason": v.reason,
                "size_factor": v.size_factor,
                "evidence": list(v.evidence),
            }
        )
    flagged = [v for v in verdicts if v["action"] in {"AVOID", "BOOST", "WARNING"}]
    return {
        "thresholds": mistake_memory.thresholds(),
        "records": items,
        "verdicts": verdicts,
        "flagged_count": len(flagged),
        "total_fingerprints": len(items),
    }


@router.get("/learning/dataset-health")
def get_dataset_health() -> dict:
    """CP1 — öğrenme veri-hazırlık özeti (observe-only). Biriken outcome'ların
    kapsama yüzdeleri (verified/confidence/excursion) + öğrenici-başı hazırlık
    (yeterli örnek var mı). 'Biriktirdiğimiz veri kullanılabilir mi' sorusunu
    yanıtlar; yeni veri toplamaz, karar zincirine etkisi yoktur."""
    return dataset_health.report()


@router.get("/learning/book-audit")
def get_book_audit() -> dict:
    """Açık kitap yapısal denetimi (observe-only). Canlı açık pozisyonları tarar;
    KAPANIŞ BEKLEMEDEN yapısal mantık hatalarını (aynı sembolde zıt yön, tek
    varlıkta yoğunlaşma, aynı sinyalin TF'lere kopyalanması, korelasyon kümesi,
    tek-yön kitap) kullanıcı-odaklı 'ders' olarak döndürür. mistake_memory yalnız
    KAPALI trade'leri öğrendiği için bu canlı-kitap boşluğunu kapatır. Karar
    zincirine etkisi yoktur — aktif self-conflict guard ayrı flag'le koşullu
    (book_audit.self_conflict_guard.enabled, shadow-first)."""
    return book_audit.summary_viewmodel()


@router.get("/learning/historical-edge")
def get_historical_edge(fingerprint: str) -> dict:
    """Fuzzy-similarity historical edge — verilen fingerprint'e benzer geçmiş
    trade'lerin winrate/avg_pnl özeti. Read-only; karar zincirini etkilemez
    (mistake_memory exact-match gate'inin tamamlayıcısı, ondan ayrı)."""
    result = historical_edge.compute_edge(fingerprint)
    return {
        "similarity_weights": historical_edge.active_similarity_weights(),
        "result": historical_edge.edge_to_dict(result),
    }


@router.get("/learning/tf-targets")
def get_tf_targets() -> dict:
    """Faz B — TF-bazlı SL/TP geometri öğrenmesinin durumu (read-only).

    Aktif değerleri (config defaults + store override) TF başına gösterir;
    bekleyen owner-onayını ve son trainer önerisinin özetini taşır. Live
    geometri compute_tf_targets'tan üretilir — bu sadece görüntü."""
    store_data = tf_target_store.load()
    current = store_data.get("current") or {}
    effective: dict[str, dict[str, float]] = {}
    for tf in ("15m", "1h", "4h", "1d"):
        effective[tf] = te._tf_params(tf)
    return {
        "enabled": te.tf_targets_enabled(),
        "auto_apply_band_pct": tf_target_store.AUTO_APPLY_BAND_PCT,
        "guardrail": {
            k: {"min": v[0], "max": v[1]}
            for k, v in tf_target_store.GUARDRAIL.items()
        },
        "effective": effective,
        "store_current": dict(current),
        "pending": store_data.get("pending"),
        "history": list(store_data.get("history") or [])[:10],
    }


@router.post("/learning/tf-targets/approve")
def post_tf_targets_approve() -> dict:
    """Bekleyen TF-target önerisini onayla → store'a yazılır, compute_tf_targets
    bir sonraki açılışta yeni değerleri kullanır."""
    rec = tf_target_store.approve_pending()
    return {"approved": rec is not None, "record": rec}


@router.post("/learning/tf-targets/reject")
def post_tf_targets_reject() -> dict:
    """Bekleyen TF-target önerisini reddet → değişiklik uygulanmaz."""
    rec = tf_target_store.reject_pending()
    return {"rejected": rec is not None, "record": rec}


@router.post("/learning/tf-targets/retrain")
def post_tf_targets_retrain() -> dict:
    """Trainer'ı manuel tetikle (örnek-kapısı bypass; gözlem için)."""
    result = tf_target_trainer.train(
        store_overrides=tf_target_store.active_overrides()
    )
    if isinstance(result, tf_target_trainer.TfTargetProposal):
        return tf_target_trainer.proposal_to_dict(result)
    return result


@router.get("/learning/conflict-gate-validation")
def get_conflict_gate_validation() -> dict:
    """Faz 9A — retrospektif rapor: gerçekleşmiş trade'ler, açıldıkları anda
    kaydedilmiş shadow gözlemindeki Conflict Resolver verdict'iyle eşleştirilip
    trade_profile bazında route (open/open_reduced/manual_ready/block) başına
    gerçek win-rate/avg_pnl gösterir. Read-only; karar zincirini etkilemez —
    profil aktivasyon kararına (conflict_gate.enabled) veri sağlar."""
    return conflict_gate_backtest.validation_report()


@router.get("/learning/missed-opportunities")
def get_missed_opportunities() -> dict:
    """Faz 2 — Missed Opportunity özeti (read-only). Açılmayan valid setup'ların
    (CANDIDATE_OPEN ama canlı açmadı) TTL sonucu: missed_win / avoided_loss /
    expired, trade_profile bazında. PAPER_SAFE — paper'a dokunmaz, yalnızca
    izleme logundan sayar. Faz 4 (conflict-gate genişletme) kararına veri."""
    return missed_opportunity.summary_viewmodel()


@router.get("/learning/calibration-jumps")
def get_calibration_jumps() -> dict:
    """Calibration jump ledger özeti (read-only/observe). Platt kalibrasyonunun
    ham consensus güvenini ne kadar şişirdiğini (raw → fitted) ve sürükleyen
    faktörleri (score/dominant/regime/tier/size) gösterir. `guardrail` bloğu
    otomatik kısma flag'inin durumudur — açıkken zayıf sinyal aşırı şişemez."""
    cfg = load_thresholds().get("calibration_guardrail") or {}
    return {
        "guardrail": {
            "enabled": bool(cfg.get("enabled", False)),
            "max_inflation_delta": float(cfg.get("max_inflation_delta", 0.25)),
        },
        **calibration_audit.summary_viewmodel(),
    }


@router.get("/learning/conflict-gate-status")
def get_conflict_gate_status() -> dict:
    """Faz 8 — Conflict Gate'in şu anki config durumu (enabled + profil bazlı
    mod tablosu). Read-only; sadece config'i yansıtır, karar zincirine etkisi
    yoktur (etki zaten enabled flag'i ile koşullu — bkz. packages/decision/gates.py)."""
    cfg = conflict_gate.load_config()
    return {"enabled": cfg.enabled, "profile_modes": cfg.profile_modes}
