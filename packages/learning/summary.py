"""Learning özetini paper state'ten üretir — API endpoint'i bunu döndürür."""
from __future__ import annotations

from dataclasses import asdict

from packages.data.registry.loader import active_weights_version, load_thresholds
from packages.learning import (
    benchmark,
    performance_readiness,
    rebalance_store,
    run_store,
    shadow_routing,
    signal_quality,
)
from packages.learning import cohorts as cohorts_mod
from packages.learning import outcomes as outcomes_mod
from packages.learning.calibration import reliability_bins
from packages.learning.walkforward import summarize as wf_summarize
from packages.paper import state as paper_state

# UX1 — Sharpe / win-rate gibi metrikler bu eşiğin altında istatistiksel
# olarak anlamlı değildir; frontend bunları büyük göstermez (LearningPanel
# "INSUFFICIENT SAMPLE" uyarısı). Frontend hesap yapmaz: karar backend'de.
MIN_RELIABLE_TRADES = 20


def _performance_snapshot(outcomes: list) -> dict:
    """Temiz/öğrenilebilir kohort için tek performans özeti.

    Eski üst seviye alanlar geriye dönük uyumluluk için tüm kapanışları göstermeye
    devam eder. Premium panel ve yeni raporlar bu snapshot'ı kullanır; anomaliler,
    çözülemeyen legacy kayıtlar ve eksik atıflar performansı kirletemez.
    """
    total = len(outcomes)
    wins = sum(1 for o in outcomes if o.pnl > 0)
    losses = sum(1 for o in outcomes if o.pnl < 0)
    breakeven = total - wins - losses
    decided = wins + losses
    pnls = [float(o.pnl) for o in outcomes]
    r_vals = [float(o.r_multiple) for o in outcomes if o.r_multiple is not None]
    mean = sum(pnls) / len(pnls) if pnls else 0.0
    if len(pnls) >= 2:
        var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
        sd = var**0.5
        sharpe = round((mean / sd) * (252**0.5), 3) if sd > 0 else 0.0
    else:
        sharpe = None
    result = {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "win_rate": round(wins / decided, 3) if decided else 0.0,
        "total_pnl": round(sum(pnls), 2),
        "expectancy_r": round(sum(r_vals) / len(r_vals), 4) if r_vals else None,
        "r_sample": len(r_vals),
        "verified": sum(1 for o in outcomes if o.data_verified),
        "sharpe": sharpe,
        "sample_sufficient": total >= MIN_RELIABLE_TRADES,
        "by_timeframe": outcomes_mod.bucketize(outcomes, lambda o: o.timeframe),
    }
    # Performans kanıtı (hedef 7. aşama): maliyet sonrası, düşüş ve al-tut kıyası.
    c = benchmark.cost_r()
    result["cost_r"] = c
    result["net_expectancy_r"] = (
        round(result["expectancy_r"] - c, 4) if result["expectancy_r"] is not None else None
    )
    result["max_drawdown_r"] = benchmark.max_drawdown_r(outcomes)
    try:
        equity0 = float(load_thresholds()["paper_trading"]["initial_equity_usd"])
    except (OSError, KeyError, ValueError, TypeError):
        equity0 = 0.0
    result["benchmark"] = benchmark.buy_and_hold(outcomes, equity0)
    return result


def _proposal_status() -> str:
    """Rebalance proposal durumu (additive yüzey) — PENDING/APPROVED/REJECTED/NONE."""
    cur = rebalance_store.get_pending()
    return str(cur.get("status")) if cur else "NONE"


def build_summary() -> dict:
    s = paper_state.load()
    # B4 — başlık metrikleri de canonical outcome birleşiminden (recent_trades +
    # decision_log) türetilir. Eskiden yalnız `recent_trades` (volatile ~200
    # pencere) okunuyordu; bu yüzden başlık 12 trade gösterirken alt kırılımlar
    # 55 gösterip ÇELİŞİYORDU. Artık tek kaynak: outcomes_from_state.
    outcomes = outcomes_mod.outcomes_from_state(s)
    total = len(outcomes)
    wins = sum(1 for o in outcomes if o.pnl > 0)
    losses = sum(1 for o in outcomes if o.pnl < 0)
    breakeven = total - wins - losses
    # F1-2 — win_rate paydası kararlı trade'ler (wins+losses); başabaş
    # (time-stop BE çıkışı gibi) win_rate'i suni düşürmez, ayrı sayılır.
    decided = wins + losses
    win_rate = round(wins / decided, 3) if decided else 0.0

    pnls = [o.pnl for o in outcomes]
    sharpe = None
    if len(pnls) >= 2:
        mean = sum(pnls) / len(pnls)
        var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
        sd = var**0.5 if var > 0 else 0.0
        sharpe = round((mean / sd) * (252**0.5), 3) if sd > 0 else 0.0

    # G6: gerçek predicted_confidence (verified outcome'lardan). Placeholder
    # 0.5 baseline'ı kaldırıldı — DATA_POLICY: verified+predicted'a sahip
    # outcome'lar örneklere alınır. /learning/calibration endpoint'i ile aynı
    # kaynak → panel ile başlık tutarlı.
    # Kalibrasyon yalnızca öğrenmeye uygun kayıtlarla ölçülür; eski SL
    # anomalileri veya eksik atıf güven puanını bozmasın.
    learning_outcomes = outcomes_mod.learning_grade(outcomes, include_exploration=True)
    samples = [
        (float(o.predicted_confidence), o.pnl > 0)
        for o in learning_outcomes
        if o.data_verified and o.predicted_confidence is not None
    ]
    bins = [asdict(b) for b in reliability_bins(samples, n_bins=5)]

    wf = wf_summarize(pnls)
    walk = asdict(wf) if wf else None

    # L1 — timeframe-aware breakdown'lar (aynı canonical outcome listesinden).
    # 15m outcome 1d bucket'ını ETKİLEMEZ (her bucket ayrı).
    bd = outcomes_mod.breakdowns(outcomes)
    verified_outcomes = sum(1 for o in outcomes if o.data_verified)

    # F1-1 — R-bazlı expectancy (boyut-bağımsız edge): yalnız r_multiple taşıyan
    # outcome'lar (legacy/SL'siz girmez). USD metrikleri olduğu gibi sürer.
    r_vals = [o.r_multiple for o in outcomes if o.r_multiple is not None]
    expectancy_r = round(sum(r_vals) / len(r_vals), 4) if r_vals else None
    clean_performance = _performance_snapshot(learning_outcomes)
    provenance_incomplete = sum(
        1 for o in outcomes if not bool(getattr(o, "provenance_complete", True))
    )
    execution_anomalies = sum(1 for o in outcomes if outcomes_mod.is_execution_anomaly(o))
    legacy_outcomes = sum(1 for o in outcomes if getattr(o, "regime", None) == "UNKNOWN")

    result = {
        "total_trades": total,
        "breakeven_trades": breakeven,  # F1-2 additive — BE görünür, loss değil
        "expectancy_r": expectancy_r,   # F1-1 additive — R-katı ortalama
        "r_sample": len(r_vals),        # F1-1 additive — R hesaplanabilen outcome sayısı
        "min_sample": MIN_RELIABLE_TRADES,
        "sample_sufficient": total >= MIN_RELIABLE_TRADES,
        "win_rate": win_rate,
        "sharpe": sharpe,
        "sortino": sharpe,
        "max_dd_pct": round(
            max(0.0, (s.peak_equity_usd - s.equity_usd) / s.peak_equity_usd)
            if s.peak_equity_usd > 0
            else 0.0,
            4,
        ),
        "walk_forward": walk,
        "calibration": bins,
        "module_skew": {},
        # Aktif manifest'ten (approve sonrası güncellenir) — eskiden "1.0.0"
        # sabit kodluydu ve owner'a yanlış aktif versiyon gösteriyordu.
        "weights_version": active_weights_version(),
        # --- L1 additive (frontend hesap yapmaz; backend türetir) ---
        "outcomes_total": len(outcomes),
        "verified_outcomes": verified_outcomes,
        "by_timeframe": bd["by_timeframe"],
        "by_symbol": bd["by_symbol"],
        "by_regime": bd["by_regime"],
        "by_dominant_module": bd["by_dominant_module"],
        "by_close_reason": bd["by_close_reason"],
        # F1-3 additive — modül katkı vektörü attribution'u (kazanan vs kaybeden
        # trade'lerdeki ortalama katkı). Salt gözlem; F3 regresyonunun ham yüzeyi.
        "module_attribution": outcomes_mod.module_attribution(outcomes),
        # FAZ-4 additive — rejim başına modül KALİTE AYRIM karnesi (kazanan vs
        # kaybeden katkı ayrımı + hüküm). module_attribution'ın rejim-ayrık +
        # hükümlü hâli; WEIGHT_REGIME_FILTER aktivasyonu için kanıt kapısı.
        # Salt-gözlem — hiçbir karar/ağırlık beslemez.
        "signal_quality": signal_quality.regime_module_scorecard(outcomes),
        # Denetim 2026-07-03 additive — AUTO/MANUAL/EXCLUDED kohort ayrımı.
        # Mevcut alanlar (total_trades/win_rate/by_timeframe...) TÜM outcome'ları
        # saymaya devam eder (kırılım yok); auto sistemin gerçek performansı ve
        # manuel/test kirliliği bu blokta ayrı ayrı görünür.
        "cohorts": cohorts_mod.cohort_summary(outcomes),
        # Premium görünüm için temiz performans. Eski ham alanlar silinmez;
        # frontend artık karar kalitesi için bu alanı tercih eder.
        "performance": {
            **clean_performance,
            "excluded_from_learning": max(0, total - len(learning_outcomes)),
            "provenance_incomplete": provenance_incomplete,
            "provenance_quarantine": {
                "count": provenance_incomplete,
                "retained_for_audit": True,
                "included_in_learning": False,
            },
            "execution_anomalies": execution_anomalies,
            "legacy_outcomes": legacy_outcomes,
        },
        "worker_last_run": run_store.load(),
        "proposal_status": _proposal_status(),
        # Birleşik gölge kanıtı: yalnız gözlem, canlı karar/ağırlık/paper etkisi yok.
        "shadow_routing": shadow_routing.viewmodel(),
    }
    # Tek, additive performans karnesi: yalnız gözlem; canlı karar zincirine
    # bağlanmaz. Ham/legacy metrikler geriye dönük uyumluluk için korunur.
    result["performance_readiness"] = performance_readiness.evaluate(
        result["performance"], result
    )
    return result
