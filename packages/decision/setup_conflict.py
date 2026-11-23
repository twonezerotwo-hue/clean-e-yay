"""Kurulum sınıflandırıcı + çakışma çözücü girdisi — canlı çakışma kapısının tek kaynağı.

tick_worker her turda ajan matrisinin sembol görünümleri için `evaluate_symbol`
çağırır; dönen `setup_type` / `conflict_final_action` / `trade_profile`,
`decision.gates` içindeki çakışma kapısına (conflict_gate) girer.

Geçmiş: bu kod `decision/shadow.py` içindeydi. Gölge karşılaştırması (observe /
record / activation), Agent Mode ayarları ve uçları 22 Kasım 2026'da silindi
(gölge ve araştırma envanteri H1; arsiv/envanter-oncesi etiketinde). Agent Mode
filtresinin varsayılan ayarlardaki etkisi aynen korunur: kurulum ya da profil
yoksa çakışma çözücüye "agent_mode:no_setup_or_profile" engeli gider.

Salt-okuma: paper durumuna dokunmaz, işlem açmaz.
"""
from __future__ import annotations

import logging
from typing import Any

from packages.data.providers import ohlcv
from packages.decision import conflict_resolver
from packages.elliott import engine as elliott_engine
from packages.learning import historical_edge
from packages.liquidity import sweep as liquidity_sweep_engine
from packages.mode import profile_selector
from packages.scoring import exhaustion as exhaustion_engine
from packages.setup import classifier as setup_classifier
from packages.volume import engine as volume_engine
from packages.zones import engine as zone_engine

_log = logging.getLogger(__name__)

# ConsensusSnapshot/per_timeframe key naming (m15..w1) → entry timeframe label.
_KEY_BY_TF = {"15m": "m15", "1h": "h1", "4h": "h4", "1d": "d1", "1w": "w1"}


def _entry_tf_result(view: Any, entry_timeframe: str | None) -> Any | None:
    """view.agent.per_timeframe[key] için entry_timeframe karşılığı (yoksa None)."""
    key = _KEY_BY_TF.get(entry_timeframe or "")
    if key is None:
        return None
    per_tf = getattr(getattr(view, "agent", None), "per_timeframe", None) or {}
    return per_tf.get(key)


def evaluate_symbol(
    view: Any, *, fingerprint: str | None, risk_action: str | None, dqs_status: str
) -> dict:
    """Bir sembol görünümü için Setup Classifier + Conflict Resolver (spec v2.3 §19/§28).

    Yalnız hesaplanmış kanıtları okur (consensus, decision, economics, giriş TF
    teknik sonucu, Elliott, historical edge, hacim/likidite/tükenme/bölge).
    Her adım savunmacı: hesap patlarsa boş dict döner, tick çökmez.
    """
    try:
        consensus = getattr(view, "consensus", None)
        decision = getattr(view, "decision", None)
        economics = getattr(view, "economics", None)
        entry_tf = getattr(decision, "entry_timeframe", None)
        entry_result = _entry_tf_result(view, entry_tf)

        chart_patterns = getattr(entry_result, "chart_pattern_analysis", None)
        reversal = getattr(entry_result, "reversal_signals", None)
        trend = getattr(entry_result, "trend_strength", None)

        symbol = getattr(view, "symbol", None)
        tf = entry_tf or "1d"
        bars = ohlcv.get_bars(symbol, tf) or [] if symbol else []
        elliott = elliott_engine.analyze(bars, timeframe=tf)

        # Faz 4 — Faz 1/2 motorlarından (Volume/Liquidity-Sweep/Exhaustion/Zone)
        # kanıt üretip Setup Classifier'a besle.
        current_price = bars[-1].close if bars else None
        volume = volume_engine.analyze(bars, timeframe=tf)
        sweep = liquidity_sweep_engine.analyze(bars, timeframe=tf)
        exhaustion = exhaustion_engine.analyze(bars, timeframe=tf, volume=volume, sweep=sweep)
        zone = zone_engine.analyze(bars, timeframe=tf, current_price=current_price)

        setup_inputs = setup_classifier.SetupInputs(
            direction_score=getattr(consensus, "direction_score", None),
            alignment_status=getattr(consensus, "alignment_status", "CONFLICTED"),
            is_countertrend=bool(getattr(consensus, "is_countertrend", False)),
            entry_timeframe=entry_tf,
            volatility_regime=getattr(entry_result, "volatility_regime", "UNKNOWN"),
            trend_label=getattr(trend, "label", "UNKNOWN"),
            is_trending=bool(getattr(trend, "is_trending", False)),
            chart_pattern_names=tuple(
                p.name for p in (getattr(chart_patterns, "active_patterns", None) or [])
            ),
            reversal_bias=getattr(reversal, "bias", "NEUTRAL"),
            zone_location=zone.location if zone.validity != "unavailable" else None,
            elliott_scenario=elliott.primary_scenario,
            elliott_bias=elliott.bias,
            elliott_confidence=elliott.confidence,
            liquidity_sweep_bias=sweep.bias if sweep.validity != "unavailable" else "unknown",
            exhaustion_score=exhaustion.score if exhaustion.validity != "unavailable" else None,
            volume_state=volume.state if volume.validity != "unavailable" else None,
            volume_price_direction=volume.price_direction if volume.validity != "unavailable" else None,
        )
        setup_result = setup_classifier.classify(setup_inputs)

        edge_strong_negative = False
        if fingerprint:
            edge = historical_edge.compute_edge(fingerprint)
            edge_strong_negative = historical_edge.is_strong_negative(edge)

        trade_profile = profile_selector.select_profile(setup_result.setup_type, entry_tf)
        # Eski Agent Mode filtresinin varsayılan (her şeye izinli) ayarlardaki sonucu.
        mode_passed = setup_result.setup_type != "NO_TRADE" and trade_profile is not None
        mode_blocked_reason = None if mode_passed else "no_setup_or_profile"

        conflict_inputs = conflict_resolver.ConflictInputs(
            dqs_status="BAD" if dqs_status == "BLOCKED" else dqs_status,
            risk_gate_action=risk_action or "HOLD",
            trigger_confirmed=getattr(decision, "action", None) == "SCOUT_ALLOWED",
            sl_tp_rr_valid=bool(getattr(economics, "allow", False)) if economics is not None else False,
            setup_type=setup_result.setup_type,
            historical_edge_strong_negative=edge_strong_negative,
            size_multiplier=float(getattr(decision, "size_multiplier", 0.0) or 0.0),
            alignment_status=getattr(consensus, "alignment_status", "CONFLICTED"),
            elliott_scenario=elliott.primary_scenario,
            elliott_confidence=elliott.confidence,
            mode_filter_passed=mode_passed,
            mode_filter_blocked_reason=mode_blocked_reason,
            trade_profile=trade_profile,
        )
        resolution = conflict_resolver.resolve(conflict_inputs)

        return {
            "setup_type": setup_result.setup_type,
            "setup_reason": setup_result.reason,
            "setup_direction": setup_result.direction,
            "trade_profile": trade_profile,
            "mode_filter_passed": mode_passed,
            "mode_filter_blocked_reason": mode_blocked_reason,
            "conflict_final_action": resolution.final_action,
            "conflict_blocked_by": list(resolution.blocked_by),
            "conflict_path": list(resolution.conflict_resolution_path),
        }
    except Exception:
        _log.warning(
            "setup_conflict failed for %s — çakışma kapısı bu sembolde fail-open",
            getattr(view, "symbol", "?"),
            exc_info=True,
        )
        return {}


__all__ = ["evaluate_symbol"]
