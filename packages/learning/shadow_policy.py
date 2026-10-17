"""Evidence-calibrated policy for learning shadows.

This is a single read-only inventory of which shadow loops may collect evidence
and which ones must remain observational. It does not enable broker execution,
alter consensus weights, or delete historical artifacts.
"""
from __future__ import annotations

import os
from typing import Any

_TRUE = {"1", "true", "yes", "on"}


def _enabled(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in _TRUE


def _threshold_bool(section: str, key: str) -> bool:
    try:
        from packages.data.registry.loader import load_thresholds

        return bool((load_thresholds().get(section) or {}).get(key, False))
    except (OSError, KeyError, TypeError, ValueError):
        return False


def evaluate() -> dict[str, Any]:
    """Return the current shadow policy without mutating any runtime state."""
    discovery = _enabled("DISCOVERY_SCAN_ENABLED")
    challenger = _enabled("BACKTEST_CHALLENGER_ENABLED")
    tf_shadow = _enabled("TF_SCORING_V2_SHADOW")
    return {
        "engine": "shadow_policy_v1",
        "live_activation": False,
        "paper_safe": True,
        "modules": {
            "causal_calibration": {
                "mode": "OBSERVE_WEEKLY",
                "enabled": True,
                "live_effect": False,
                "reason": "Yeterli doğrulama yok; haftalık kanıt biriktirir.",
            },
            "zone_proposer": {
                "mode": "OBSERVE_ONLY",
                "enabled": True,
                "live_effect": False,
                "reason": "Aday bölge üretir; owner kabulü olmadan karar zincirine girmez.",
            },
            "backtest_challenger": {
                "mode": "ACTIVE_SHADOW" if challenger else "DISABLED",
                "enabled": challenger,
                "live_effect": False,
                "reason": "Challenger kanıt üretir; terfi kriteri tamamlanmadı.",
            },
            "quantum_scorecard": {
                "mode": "FROZEN_GATED",
                "enabled": challenger,
                "live_effect": bool(
                    _threshold_bool("consensus", "quantum_v2")
                    and _threshold_bool("consensus", "quantum_regime_gate")
                ),
                "allowed_regimes": ["OFFENSIVE"],
                "reason": "Ters/yetersiz rejim kanıtı nedeniyle ağırlık artırılmaz; yalnız izinli rejimde gözlenir.",
            },
            "conflict_gate_learning": {
                "mode": "OBSERVE_ONLY",
                "enabled": True,
                "live_effect": False,
                "reason": "Doğrulama kaydı yok; yeni kural veya eşik açılmaz.",
            },
            "news_discovery": {
                "mode": "ACTIVE_SHADOW" if discovery else "DISABLED",
                "enabled": discovery,
                "live_effect": False,
                "reason": "Aktif tarama ve asset adayı üretimi açık; işlem evrenine otomatik ekleme yok.",
            },
            "tf_scoring_v4_race": {
                "mode": "ACTIVE_SHADOW_CANARY" if tf_shadow else "DISABLED",
                "enabled": tf_shadow,
                "live_effect": False,
                "reason": "V4 replay üstünlüğü yalnız canary olarak izleniyor.",
            },
        },
    }


__all__ = ["evaluate"]
