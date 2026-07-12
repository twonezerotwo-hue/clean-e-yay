"""GET /api/v1/learning/{summary, calibration, mistakes}
POST /api/v1/learning/calibration/retrain
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from packages.data.registry.loader import load_thresholds
from packages.decision import conflict_gate, conflict_gate_backtest
from packages.discovery import scanner as discovery_scanner
from packages.learning import (
    activation_watchdog,
    book_audit,
    calibration_audit,
    calibration_store,
    calibration_trainer,
    challenger_trainer,
    cohorts,
    dataset_health,
    edge_report,
    empirical_pwin,
    entry_exit_quality,
    evidence_bus,
    exit_backtest,
    exit_forensics,
    guard_safety,
    historical_edge,
    meta_gate,
    missed_opportunity,
    mistake_memory,
    monitoring_coverage,
    news_event_study,
    partial_tp_shadow,
    promotion_criteria,
    reflection,
    regime_risk_brake,
    source_selector,
    subsignal_scorecard,
    tf_calibration,
    tf_scoring_race,
    tf_scoring_shadow,
    tf_target_rollback,
    tf_target_store,
    tf_target_trainer,
    tf_weight_trainer,
    threshold_ab,
    threshold_trainer,
    zero_two_strategy,
    zone_chart,
    zone_plan_shadow,
    zone_proposer,
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


@router.get("/learning/activation-watchdog")
def get_activation_watchdog() -> dict:
    """F5-3 — owner-flag aktivasyon izleyicisi (read-only, yalnız-öneri).
    Hangi flag açık, izleme ilerlemesi, CONFIRMED/DEGRADED geçmişi."""
    return activation_watchdog.report()


@router.get("/learning/partial-tp-shadow")
def get_partial_tp_shadow() -> dict:
    """F4-3 — partial-TP shadow-vs-actual özeti (read-only). Owner
    `partial_tp.enabled` aktivasyon kararını bu kanıtla verir."""
    return partial_tp_shadow.summary()


@router.get("/learning/tf-weights")
def get_tf_weights() -> dict:
    """Step 8 — per-TF calibration + the trust-gated tf_weights proposal (read-only).

    Owner-facing view: which timeframes are validated (CALIBRATED) and what weight
    changes the verified outcomes suggest. Informational — live weights are never
    moved here (owner approval, never auto-apply)."""
    return tf_weight_trainer.report_viewmodel()


@router.get("/learning/exit-backtest")
def get_exit_backtest() -> dict:
    """Çıkış stop-verim backtest'i (read-only, PAPER_SAFE, SALT-ANALİZ). Gerçek
    OHLCV geçmişinde sabit SL × trailing (aktivasyon/mesafe) × partial_tp ızgarası
    → en verimli aralık + TF kırılımı. Canlı çıkış davranışına ASLA dokunmaz;
    owner çıkış config'ini (trail mesafesi, SL katı) bu kanıtla gözden geçirir.
    Ağır → haftalık interval-kapılı üretilir (SKIP_FRESH=taze artifact)."""
    return exit_backtest.viewmodel()


@router.get("/learning/zero-two-strategy")
def get_zero_two_strategy() -> dict:
    """0-2 tam-strateji gölge karnesi (read-only, PAPER_SAFE, SALT-ANALİZ). Owner'ın
    nihai LONG akışı (0.618 giriş + fib hedef + 0-2 trailing + sabit-bahis house-money
    re-giriş) arşiv+canlı barlarda ölçülür → TF×pivot hücrelerinde işlem sayısı, isabet,
    ilk-işlem ve house-money'li PnL. Canlı skora/karara ASLA dokunmaz; kanıt biriktirir.
    Sayılar flat-veri + örtüşen işlemlerle şişebilir → güven için ileri-veri şart."""
    return zero_two_strategy.viewmodel()


@router.get("/learning/zone-plan")
def get_zone_plan() -> dict:
    """Bölge-planı gölge karnesi (read-only, PAPER_SAFE, SALT-ANALİZ). Owner'ın
    el-çizimi kesişim bölgeleri (config/zone_plans.yaml — sistem bölge ÜRETMEZ)
    üzerinde dallı işlem planı gölge-yürütülür: parçalı çekirdek girişi, break-even
    kuralı, derin-katman ortalama düşürme + retest TP, kalıcı geri-alımda yüksek
    bakiye + %3 stop, LOG-fib çıkış merdiveni. Canlı karara ASLA dokunmaz."""
    return zone_plan_shadow.viewmodel()


@router.get("/learning/zone-proposer")
def get_zone_proposer() -> dict:
    """Aday bölge önerileri (read-only, PAPER_SAFE, SALT-ANALİZ). Owner'ın kesişim
    yöntemi makro evrende (rotasyon çekirdeği + yükselen ETF + keşif kısa listesi)
    mekanik geometriyle serilir: haftalık pivot → LOG-uzay trend çizgisi → log-fib
    kümesi → çizgi kesişimi → confluence skoru. Makine bölge SEÇMEZ, ADAY önerir;
    owner süzer, kabul edileni zone_plans.yaml'a taşır. Canlı karara ASLA dokunmaz."""
    return zone_proposer.viewmodel()


class ZoneVerdictRequest(BaseModel):
    """Owner'ın bölge kararı: iptal | onay (varsayılan durum zaten onaylı)."""
    symbol: str
    low: float
    high: float
    action: str  # "iptal" | "onay"
    note: str = ""


@router.post("/learning/zone-proposer/verdict")
def post_zone_verdict(req: ZoneVerdictRequest) -> dict:
    """Owner bölge kararı (PAPER_SAFE — işlem açmaz/kapamaz). Öneri bölgeleri
    owner İPTAL EDENE KADAR onaylıdır; iptal edilen bölge zone_influence'a
    girmez (flag açık olsa bile). Karar tarihçesi kalibrasyon verisidir."""
    from packages.learning import zone_approval

    try:
        rec = zone_approval.record(req.symbol, req.low, req.high, req.action, req.note)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "status": "OK",
        "recorded": rec,
        "verdict": zone_approval.verdict_for(req.symbol, req.low, req.high),
    }


@router.get("/learning/zone-proposer/review", response_class=HTMLResponse)
def get_zone_proposer_review() -> HTMLResponse:
    """Aday bölge GÖRSEL incelemesi (read-only, PAPER_SAFE). Tüm evrenin gerçek
    haftalık grafikleri üzerine makinenin çizdikleri işaretlenir (trend çizgileri,
    fibler, kesişim, bölge bantları; owner planı varsa turkuaz bindirme) — owner
    gözüyle kontrol edip onay/ret verir. Hesap yapmaz; karar owner'da."""
    return HTMLResponse(zone_chart.review_html())


@router.get("/learning/zone-proposer/chart/{symbol}")
def get_zone_proposer_chart(symbol: str) -> Response:
    """Tek asset'in işaretli SVG grafiği (read-only, PAPER_SAFE). Veri yoksa 404."""
    svg = zone_chart.chart_svg(symbol.upper())
    if svg is None:
        raise HTTPException(404, f"{symbol}: haftalık bar verisi yok")
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/learning/reflection")
def get_reflection() -> dict:
    """Yansıma/hafıza döngüsü (read-only, PAPER_SAFE, SALT-GÖZLEM). Kapanan
    işlemlerden çıkarılan dersler (çapraz-sembol + per-sembol) — "ne oldu, kaça,
    hangi setup". Karar hattına BAĞLI DEĞİL (enjeksiyon ayrı owner adımı);
    dersler yalnız gerçekleşen outcome alanlarından türer (uydurma yok)."""
    return reflection.viewmodel()


@router.get("/learning/payoff-readiness")
def get_payoff_readiness() -> dict:
    """Faz-A (EV kapısı) — per-hücre payoff EV hazırlık yüzeyi (read-only,
    PAPER_SAFE). Her hücrenin (tf|rejim) gerçekleşen-R örneği (win_r_n/loss_r_n)
    min_r_samples eşiğine karşı; payoff-ağırlıklı EV ancak iki yönde de eşik
    dolunca devreye girer. "10/10 = R-verisi birikince payoff EV" görünürlüğü;
    guard zaten canlı (yetersiz hücre dürüstçe sabit-RR'ye düşer)."""
    return empirical_pwin.payoff_readiness()


@router.get("/learning/calibration-fit")
def get_calibration_fit() -> dict:
    """Faz-A (Kalibrasyon) — per-TF Platt fit güven yüzeyi (read-only, PAPER_SAFE).
    Her TF'in kalibrasyon fit durumu (fitted / insufficient / identity + örnek
    sayısı) + outcome güveni (CALIBRATED/PRIOR) yan yana. "10/10 = TF başına
    yeterli örnekle fit doğrulanır" görünürlüğü; guard zaten canlı (yetersiz TF-fit
    global fit'e düşer). Hiçbir çıktı canlı ağırlığa/karara dokunmaz."""
    return tf_calibration.fit_confidence_report()


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
        # Denetim 2026-07-03 additive — TF-başı eğitim kapsamı: hangi TF'te
        # yeterli AUTO kanıtı var? 1d gibi eksikler dürüstçe UNTRAINED görünür
        # (kanıt havuzlama / eşik indirme YOK).
        "coverage": _tf_target_coverage(),
        "trainer_inputs": {
            "auto_only_enabled": tf_target_trainer.auto_only_enabled(),
            "forensics_nudge_enabled": tf_target_trainer.forensics_nudge_enabled(),
        },
    }


def _tf_target_coverage() -> dict:
    """TF-başı trainer kanıt sayımı (AUTO kohort vs verified).

    status trainer'ın FİİLEN kullandığı sayıya bakar: TF_TARGET_AUTO_ONLY
    açıkken auto_n, kapalıyken verified_n — gösterge makinenin gerçeğini söyler.
    """
    outs = outcomes_mod.outcomes_from_state()
    auto_only = tf_target_trainer.auto_only_enabled()
    cov: dict[str, dict] = {}
    for tf in ("15m", "1h", "4h", "1d"):
        items = [o for o in outs if o.timeframe == tf]
        auto_n = sum(1 for o in items if cohorts.classify(o) == cohorts.AUTO)
        verified_n = sum(1 for o in items if o.data_verified)
        n_used = auto_n if auto_only else verified_n
        cov[tf] = {
            "auto_n": auto_n,
            "verified_n": verified_n,
            "min_required": tf_target_trainer.MIN_TRADES_PER_TF,
            "status": (
                "TRAINED"
                if n_used >= tf_target_trainer.MIN_TRADES_PER_TF
                else "UNTRAINED"
            ),
        }
    return cov


@router.get("/learning/exit-forensics")
def get_exit_forensics() -> dict:
    """Çıkış Otopsisi — kötü çıkışın NEREDE ve tahmini KAÇA olduğu (read-only).

    AUTO kohort (fingerprint + verified); manuel/test şeffaflık sayacında.
    MFE/MAE yalnız pozisyon açıkken kaydedilir — kapanış-sonrası hiçbir şey
    hesaplanmaz; $ değerleri tahminidir. Worker snapshot'ının trend kuyruğu
    history_tail olarak eklenir (panel trend oku)."""
    rep = exit_forensics.report()
    tail: list = []
    try:
        snap_path = exit_forensics.snapshot_path()
        if snap_path.exists():
            snap = json.loads(snap_path.read_text(encoding="utf-8"))
            tail = list(snap.get("history") or [])[-10:]
    except (OSError, ValueError):
        tail = []  # snapshot bozuksa rapor yine döner (panel trendsiz kalır)
    rep["history_tail"] = tail
    return rep


@router.get("/learning/discovery")
def get_discovery() -> dict:
    """K-3 — Keşif tarayıcısı görünümü (read-only, PAPER_SAFE).

    "Analiz sabit, varlık değişken": geniş evren (yükselen sektör ETF'leri +
    kripto top-50) canlı analiz zincirinin ÇEKİRDEĞİNDEN geçer ama işlem AÇILMAZ.
    Tablo = güncel "açılırdı" hükümleri + K-2 gölge karnesi (hipotetik TP/SL
    çözümleri). Dürüstlük satırı her zaman döner: hiçbiri gerçek işlem değil.
    Flag DISCOVERY_SCAN_ENABLED kapalıysa enabled=false + boş tablo."""
    return discovery_scanner.viewmodel()


@router.get("/learning/subsignal-scorecard")
def get_subsignal_scorecard() -> dict:
    """D5 — Sinyal karnesi (v2 sert cetvel, read-only). Worker'ın haftalık
    ürettiği izole artifact'ı sunar: sinyal × TF ileri-getiri ayrışımı
    (edge_ratio / taban-çizgisi / iki-yarı kararlılık / verdict). Artifact
    yoksa/bozuksa status=NO_DATA — sahte veri uydurulmaz. Canlı karara dokunmaz."""
    out: dict = {"enabled": subsignal_scorecard.enabled()}
    try:
        path = subsignal_scorecard.artifact_path()
        if not path.exists():
            return {**out, "status": "NO_DATA"}
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {**out, "status": "NO_DATA"}
    return {**out, "status": "OK", **data}


@router.get("/learning/tf-scoring-shadow")
def get_tf_scoring_shadow() -> dict:
    """R4 — tf_scoring_v2 gölge görünümü (read-only). Worker'ın her cycle
    ürettiği izole artifact'ı sunar: sembol başına hava (UP/DOWN + verimlilik),
    BİRİNCİL rejim-anahtarlı yön, KONTROL eski-harman yönü, sürücü sinyaller.
    Artifact yoksa/bozuksa status=NO_DATA. Canlı karara dokunmaz."""
    out: dict = {"enabled": tf_scoring_shadow.enabled()}
    try:
        path = tf_scoring_shadow.artifact_path()
        if not path.exists():
            return {**out, "status": "NO_DATA"}
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {**out, "status": "NO_DATA"}
    return {**out, "status": "OK", **data}


@router.get("/learning/tf-scoring-race")
def get_tf_scoring_race() -> dict:
    """R5 — tf_scoring_v2 gölge YARIŞ raporu (read-only). Gölge yönlerini
    gerçekleşen ileri-getiriyle puanlayan defterin raporu: yeni beyin vs eski
    harman vs taban (buy-hold) isabet/getiri + terfi kriteri (READY→owner paketi).
    Rapor yoksa/bozuksa status=NO_DATA. Canlı karara dokunmaz — KIRMIZI ÇİZGİ."""
    out: dict = {"enabled": tf_scoring_shadow.enabled()}
    try:
        path = tf_scoring_race.report_path()
        if not path.exists():
            return {**out, "status": "NO_DATA"}
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {**out, "status": "NO_DATA"}
    return {**out, "status": "OK", **data}


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


@router.get("/learning/promotion-criteria")
def get_promotion_criteria() -> dict:
    """F5-2 — champion/challenger terfi kriteri (read-only). Eşleşmiş karar
    hacmi + ayrışma kanıtı + Wilson CI ayrıklığı; READY olsa bile terfi
    otomatik DEĞİL — governor'daki owner onay paketi üzerinden yürür."""
    return promotion_criteria.evaluate()


@router.get("/learning/evidence-bus")
def get_evidence_bus() -> dict:
    """I1 — Kanıt Otobüsü (read-only, PAPER_SAFE). Tüm öğrenme ölçümlerini
    (sinyal kalitesi / edge / quantum karnesi / keşif gölgesi / TF kalibrasyon)
    TEK normalize kanıt listesine toplar. Kaynak damgalı (live/shadow/backtest).
    Salt-gözlem — hiçbir karara bağlı değil (I2/I3 bunun üstüne kurulur)."""
    return evidence_bus.viewmodel()


@router.get("/learning/source-selection")
def get_source_selection() -> dict:
    """I3 — Kaynak Seçici (read-only, PAPER_SAFE). Sinyal-kalitesi rejim-kapsaması:
    her rejimde canlı kanıt var mı / ince mi; `LEARNING_INCLUDE_SHADOW` açıksa
    ince/boş rejimlere AYRI DAMGALI backtest/shadow fallback (gerçek canlı sayı
    kirlenmez). Flag kapalıyken salt-canlı görünüm. Salt-gözlem — karara bağlı
    değil (terfi/yön I4/I5, owner-gated)."""
    return source_selector.viewmodel()


@router.get("/learning/monitoring-coverage")
def get_monitoring_coverage() -> dict:
    """I5 — İzleme kapsama (read-only, PAPER_SAFE). Canlıya dokunan her davranış
    flag'inin nasıl izlendiği (watchdog / kendi-rollback / girdi-hijyeni / tuning /
    shadow-muaf) + WATCHDOG'ların REGISTRY'de kayıtlı olduğu. 'İzlemesiz canlı-
    dokunuş yok' değişmezi test_monitoring_coverage ile guard'lı."""
    return monitoring_coverage.coverage_summary()


@router.get("/learning/regime-risk-brake")
def get_regime_risk_brake() -> dict:
    """Y-1 — Rejim risk freni (read-only, PAPER_SAFE). Rejim başına çift-kaynak
    kanıt (canlı AUTO kohort + backtest challenger) ve fren hükmü; `enabled`
    KAPALIYKEN salt-gözlem (engine kararlarda applied=False raporu taşır).
    Owner aktivasyon kararını bu kanıttan verir; geri-alma = flag false."""
    return regime_risk_brake.viewmodel()


@router.get("/learning/meta-gate")
def get_meta_gate() -> dict:
    """Y-5 — Meta-label kapısı (read-only, PAPER_SAFE, SALT-GÖLGE). Her açılış
    adayına damgalanan GİR/GİRME hükmünün kaynak tablosu (dominant×TF bariyer-
    kalite kovaları) + gölge seçicilik karnesi (TAKE kovası SKIP'ten iyi mi).
    Hüküm karara/boyuta ASLA uygulanmaz — aktivasyon ayrı dilim + owner kararı
    (kırmızı çizgi). `scorecard.selective` bile tek başına aktivasyon yapmaz."""
    return meta_gate.viewmodel()


@router.get("/learning/news-event-study")
def get_news_event_study() -> dict:
    """Y-6 — Haber olay-çalışması (read-only, PAPER_SAFE, SALT-GÖZLEM). Haber
    damgası sonrası N-bar ileri-getiri karnesi (kaynak × sentiment kovası):
    "haberin edge'i var mı". Kanıt bar-arşivi gibi zamanla birikir; yetersizse
    dürüst `global_verdict=UNPROVEN` ("news ağırlığı kanıtsız"). Hiçbir çıktı
    karara/ağırlığa dokunmaz — news görünürlüğü challenger'a AYRI owner kararı."""
    return news_event_study.viewmodel()


@router.get("/learning/backtest-challenger")
def get_backtest_challenger() -> dict:
    """B serisi — backtest-challenger kanıt görünümü (read-only, PAPER_SAFE).

    İZOLE/SHADOW: geçmiş backtest'ten türeyen quantum ayrım karnesi (rejim başına
    DISCRIMINATES/INVERSE/FLAT), challenger ağırlık önerileri (champion delta) ve
    B-4 terfi durumu. Canlı ağırlık/paper/karara ASLA dokunmaz. Flag
    BACKTEST_CHALLENGER_ENABLED kapalıysa enabled=false + boş görünüm."""
    return challenger_trainer.viewmodel()


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
