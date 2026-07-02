"""GET /api/v1/learning/{summary, calibration, mistakes}
POST /api/v1/learning/calibration/retrain
"""
from __future__ import annotations

import os
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
    edge_report,
    entry_exit_quality,
    guard_safety,
    historical_edge,
    missed_opportunity,
    mistake_memory,
    tf_target_rollback,
    tf_target_store,
    tf_target_trainer,
    tf_weight_trainer,
    threshold_ab,
    threshold_trainer,
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
    # Reliability bins — fit'le AYNI durable kaynak (recent_trades + decision_log)
    # ve AYNI girdi: raw_confidence (kalibrasyon öncesi ham güven). Fit'i tekrar
    # koşmaya gerek yok; sadece son örnekleri göster.
    samples = [
        (float(o.raw_confidence), bool(o.pnl > 0))
        for o in outcomes_mod.outcomes_from_state()
        if o.data_verified and o.raw_confidence is not None
    ]
    bins = [asdict(b) for b in reliability_bins(samples, n_bins=5)]
    return {
        "params": asdict(params),
        "min_required": calibration_store.MIN_SAMPLES,
        "samples_in_state": len(samples),
        "bins": bins,
        # F4-1 — TF başına fit + flag durumu: owner aktivasyon kanıtını
        # (TF örnek sayıları, fit ayrışması) buradan izler.
        "per_timeframe": {
            tf: asdict(p)
            for tf, p in calibration_store.load_per_timeframe().items()
        },
        "tf_platt_enabled": calibration_store.tf_platt_enabled(),
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


@router.get("/learning/edge-report")
def get_edge_report() -> dict:
    """CP2 — edge kanıt/stabilite özeti (observe-only). Biriken outcome'lar
    üstünde çok-katlı walk-forward stabilite (edge tutarlı mı) + missed
    opportunity counterfactual + tek-kelime verdict (STABLE/UNSTABLE/
    INSUFFICIENT). Mevcut backtest motorunu (replay/strategy-backtest) tekrar
    etmez; CP4 öz-ayar bir öneriyi uygulamadan önce güven tartmak için okur."""
    return edge_report.report()


@router.get("/learning/threshold-ab")
def get_threshold_ab(
    param_path: str,
    values: str,
    symbol: str = "BTCUSD",
    timeframe: str = "1d",
) -> dict:
    """CP4 — eşik A/B parametre-taraması (config-injection seam tüketicisi, on-demand).
    Bir eşik parametresinin (`param_path`, ör. `paper_trading.sl_pct`) virgülle
    ayrılmış `values` değerlerini MEVCUT backtest motoruyla geçmiş barlarda dener,
    win_rate/avg_return/profit_factor karşılaştırır + baseline'dan iyiyse öneri verir.
    Override yalnız backtest scope'unda enjekte edilir (threshold_override seam);
    canlı config + karar zinciri DEĞİŞMEZ. 'trainer öner → backtest doğrula' adımı."""
    try:
        parsed = [float(v) for v in values.split(",") if v.strip()]
    except ValueError:
        return {"error": "values virgülle ayrılmış sayılar olmalı", "values": values}
    return threshold_ab.sweep(param_path, parsed, symbol=symbol, timeframe=timeframe)


@router.get("/learning/threshold-autotune")
def get_threshold_autotune() -> dict:
    """CP4 (final) — otonom eşik trainer durumu (observe). Allowlist eşikleri,
    aktif runtime override'lar, izlenen apply (rollback), geçmiş + edge/flag durumu.
    Flag `THRESHOLD_AUTOTUNE` OFF iken hiçbir eşik oto-uygulanmaz (bayt-aynı); AÇIK
    iken trainer backtest-doğrulamalı + edge STABLE + rollback'li dar-bant oto uygular."""
    return threshold_trainer.status_viewmodel()


@router.get("/learning/entry-exit-quality")
def get_entry_exit_quality() -> dict:
    """CP4 (slice 1) — giriş/çıkış kalitesi öğrenicisi (observe-only). Biriken
    verified outcome'ların MAE/MFE excursion'ından, dominant_module × timeframe
    kovaları bazında üç dersi çıkarır: erken çıkış (kâr masada), dar stop (gürültüde
    tetikleniyor), erken giriş (önce eziliyor). TF-target trainer'ın yalnız-TF
    granülerliğindeki boşluğu kapatır; karar zincirine etkisi yoktur (önerileri
    otonom uygulama ayrı bir slice — rollback net'iyle, edge STABLE kapısından)."""
    return entry_exit_quality.report()


@router.get("/learning/guard-safety")
def get_guard_safety() -> dict:
    """CP3 — yön güvenlik kasası (observe view). Bağlı yön guard'ları (chop /
    exhaustion / reversion / self_conflict) için: ham config-enabled vs engine'in
    gördüğü efektif durum, aktif izleme ilerlemesi (baseline vs post-enable
    expectancy), kasa kill-override'ları ve son geçmiş. Kasa bir guard'ı canlıda
    izlerken expectancy baseline'ın altına düşerse oto-kapatır (CP4/CP5 ön-koşulu);
    bu endpoint yalnız o durumu raporlar, karar zincirine etkisi yoktur."""
    return guard_safety.report()


@router.post("/learning/guard-safety/adopt")
def post_guard_safety_adopt() -> dict:
    """CP3 — owner aksiyonu: zaten AÇIK ama izlenmeyen yön guard'larını "şu andan
    itibaren" izlemeye al (adopted/sürüklenme modu, yalnız-öneri — sessizce kapatmaz).
    Kanıtlı oto-kapat için guard'ı OFF→ON toggle etmek gerekir (transition modu)."""
    return guard_safety.adopt()


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
    # CP4 slice 2 — edge-gate + outcome-rollback durumu (observe). Gate flag açıksa
    # geometri auto-apply yalnız edge STABLE iken olur ve her apply izlenir.
    gate_on = os.environ.get("TF_TARGET_EDGE_GATE", "0").strip().lower() not in {
        "0", "false", "no", "off", ""
    }
    rb = tf_target_rollback.load()
    # CP4 slice 3 — öğrenilen per-TF trailing çarpanı (açılışta tier.trail_distance ×).
    trail = {
        "enabled": te.trail_autotune_enabled(),
        "guardrail": {
            "min": tf_target_store.GUARDRAIL["trail_mult"][0],
            "max": tf_target_store.GUARDRAIL["trail_mult"][1],
        },
        "per_timeframe": {
            tf: te.tf_trail_mult(tf) for tf in ("15m", "1h", "4h", "1d")
        },
    }
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
        "edge_gate": {
            "enabled": gate_on,
            "safe_to_autotune": bool(edge_report.report().get("safe_to_autotune")),
            "active_monitor": rb.get("active"),
            "rollback_history": list(rb.get("history") or [])[:5],
        },
        "trail_autotune": trail,
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
