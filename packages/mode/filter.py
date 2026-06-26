"""Agent Mode Filter — spec §5.3/§5.6/§35.3 `mode_filter_result`. Saf fonksiyon.

`AgentModeConfig` + setup_type + trade_profile + is_countertrend girdilerini
deterministik bir `passed`/`blocked_reason` kararına indirger. Bu modül
HİÇBİR ŞEYİ kendi başına bloklamaz/açmaz — sadece Conflict Resolver'ın (veya
gözlem amaçlı shadow kaydının) okuyacağı bir karar nesnesi üretir.
"""
from __future__ import annotations

from dataclasses import dataclass

from packages.mode.config import AgentModeConfig

_STRATEGY_TYPE_BY_SETUP_PREFIX = {
    "REVERSAL_": "reversal",
    "TREND_": "trend_follow",
    "PULLBACK_": "trend_follow",
    "RANGE_": "range",
    "BREAKOUT_": "breakout",
}

_ALLOW_FLAG_BY_STRATEGY_TYPE = {
    "reversal": "allow_reversal_trades",
    "trend_follow": "allow_trend_follow_trades",
    "range": "allow_range_trades",
    "breakout": "allow_breakout_trades",
}


@dataclass(frozen=True)
class ModeFilterResult:
    passed: bool
    blocked_reason: str | None
    candidate_profile: str | None
    focus_mode: str | None
    watch_tracking_enabled: bool


def _strategy_type(setup_type: str) -> str | None:
    for prefix, stype in _STRATEGY_TYPE_BY_SETUP_PREFIX.items():
        if setup_type.startswith(prefix):
            return stype
    return None


def evaluate(
    *,
    setup_type: str,
    trade_profile: str | None,
    is_countertrend: bool,
    cfg: AgentModeConfig,
) -> ModeFilterResult:
    if setup_type == "NO_TRADE" or trade_profile is None:
        return ModeFilterResult(
            passed=False,
            blocked_reason="no_setup_or_profile",
            candidate_profile=trade_profile,
            focus_mode=cfg.focus_mode,
            watch_tracking_enabled=cfg.watch_disabled_profiles,
        )

    # enabled_trade_profiles boşsa allowlist YOK sayılır (hepsi serbest);
    # doluysa sadece listedekiler geçer.
    if cfg.enabled_trade_profiles and trade_profile not in cfg.enabled_trade_profiles:
        return ModeFilterResult(
            passed=False,
            blocked_reason=f"{trade_profile}_not_in_enabled_profiles",
            candidate_profile=trade_profile,
            focus_mode=cfg.focus_mode,
            watch_tracking_enabled=cfg.watch_disabled_profiles,
        )
    if trade_profile in cfg.disabled_trade_profiles:
        return ModeFilterResult(
            passed=False,
            blocked_reason=f"{trade_profile}_disabled",
            candidate_profile=trade_profile,
            focus_mode=cfg.focus_mode,
            watch_tracking_enabled=cfg.watch_disabled_profiles,
        )

    if is_countertrend and not cfg.allow_counter_context_trades:
        return ModeFilterResult(
            passed=False,
            blocked_reason="counter_context_trades_disabled",
            candidate_profile=trade_profile,
            focus_mode=cfg.focus_mode,
            watch_tracking_enabled=cfg.watch_disabled_profiles,
        )

    stype = _strategy_type(setup_type)
    if stype is not None:
        flag = _ALLOW_FLAG_BY_STRATEGY_TYPE[stype]
        if not getattr(cfg, flag):
            return ModeFilterResult(
                passed=False,
                blocked_reason=f"{stype}_trades_disabled",
                candidate_profile=trade_profile,
                focus_mode=cfg.focus_mode,
                watch_tracking_enabled=cfg.watch_disabled_profiles,
            )

    return ModeFilterResult(
        passed=True,
        blocked_reason=None,
        candidate_profile=trade_profile,
        focus_mode=cfg.focus_mode,
        watch_tracking_enabled=cfg.watch_disabled_profiles,
    )


__all__ = ["ModeFilterResult", "evaluate"]
