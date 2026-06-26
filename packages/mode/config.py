"""Agent Mode Control config — spec §5.2/§40.1.

`shadow.ShadowConfig` ile aynı desen: dataclass + `load_config()`, config'ten
defansif okuma, muhafazakâr default'lar (her şeye izin verir — şu an hiçbir
karar zincirine bağlı olmadığı için varsayılan davranış değiştirmez).

Bu modül kendi başına hiçbir şeyi bloklamaz/açmaz — sadece config taşıyıcısı.
Filtreleme mantığı `packages/mode/filter.py`'dadır.
"""
from __future__ import annotations

from dataclasses import dataclass

from packages.data.registry.loader import load_thresholds

TRADE_PROFILES = ("SCALP", "INTRADAY", "TACTICAL", "SWING", "POSITION")


@dataclass(frozen=True)
class AgentModeConfig:
    enabled_trade_profiles: tuple[str, ...] = ()  # boş = hepsi serbest (allowlist değil)
    disabled_trade_profiles: tuple[str, ...] = ()
    focus_mode: str | None = None
    allow_counter_context_trades: bool = True
    allow_reversal_trades: bool = True
    allow_trend_follow_trades: bool = True
    allow_range_trades: bool = True
    allow_breakout_trades: bool = True
    watch_disabled_profiles: bool = True
    close_disabled_profile_positions: bool = False
    close_requires_riskgate_pass: bool = True


def load_config() -> AgentModeConfig:
    c = load_thresholds().get("agent_mode_control") or {}
    return AgentModeConfig(
        enabled_trade_profiles=tuple(c.get("enabled_trade_profiles") or ()),
        disabled_trade_profiles=tuple(c.get("disabled_trade_profiles") or ()),
        focus_mode=c.get("focus_mode"),
        allow_counter_context_trades=bool(c.get("allow_counter_context_trades", True)),
        allow_reversal_trades=bool(c.get("allow_reversal_trades", True)),
        allow_trend_follow_trades=bool(c.get("allow_trend_follow_trades", True)),
        allow_range_trades=bool(c.get("allow_range_trades", True)),
        allow_breakout_trades=bool(c.get("allow_breakout_trades", True)),
        watch_disabled_profiles=bool(c.get("watch_disabled_profiles", True)),
        close_disabled_profile_positions=bool(c.get("close_disabled_profile_positions", False)),
        close_requires_riskgate_pass=bool(c.get("close_requires_riskgate_pass", True)),
    )


__all__ = ["AgentModeConfig", "TRADE_PROFILES", "load_config"]
