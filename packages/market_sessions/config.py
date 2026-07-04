"""Market-session config loader — `config/market_sessions.yaml` is the source.

Backend owns market-session meaning; this just types the YAML. No network, no
hardcoded holiday tables (holidays come from an optional exchange-calendar lib;
absent → deterministic weekday fallback marked holiday_verified=false).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "market_sessions.yaml"

MarketKind = str  # "exchange" | "continuous" | "futures_global"


@dataclass(frozen=True)
class MarketConfig:
    market_id: str
    label: str
    exchange: str
    timezone: str
    kind: MarketKind
    regular_open: str  # local HH:MM
    regular_close: str  # local HH:MM
    assets: tuple[str, ...] = ()


@dataclass(frozen=True)
class SessionThresholds:
    opening_pre_minutes: int = 15
    opening_post_minutes: int = 30
    closing_pre_minutes: int = 30
    pre_open_watch_minutes: int = 120
    # Hafta sonu boşluğu guard'ı: ilgili piyasaların SON açık seansı Cuma
    # kapanışına bu kadar dakika kala otomatik açılış manual_ready'e düşer.
    weekend_gap_pre_minutes: int = 120


@dataclass(frozen=True)
class MarketSessionsConfig:
    markets: tuple[MarketConfig, ...] = ()
    thresholds: SessionThresholds = field(default_factory=SessionThresholds)

    def markets_for_asset(self, asset_code: str) -> tuple[MarketConfig, ...]:
        a = asset_code.upper()
        return tuple(m for m in self.markets if a in {x.upper() for x in m.assets})

    def market_by_id(self, market_id: str) -> MarketConfig | None:
        return next((m for m in self.markets if m.market_id == market_id), None)


def load_config(path: Path | None = None) -> MarketSessionsConfig:
    """Load + type the YAML. Malformed/missing file → empty config (engine then
    reports unknown/diagnostics; it never invents market status)."""
    p = path or DEFAULT_CONFIG_PATH
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return MarketSessionsConfig()

    th = data.get("session_thresholds") or {}
    thresholds = SessionThresholds(
        opening_pre_minutes=int(th.get("opening_pre_minutes", 15)),
        opening_post_minutes=int(th.get("opening_post_minutes", 30)),
        closing_pre_minutes=int(th.get("closing_pre_minutes", 30)),
        pre_open_watch_minutes=int(th.get("pre_open_watch_minutes", 120)),
        weekend_gap_pre_minutes=int(th.get("weekend_gap_pre_minutes", 120)),
    )

    markets: list[MarketConfig] = []
    for market_id, cfg in (data.get("markets") or {}).items():
        cfg = cfg or {}
        markets.append(
            MarketConfig(
                market_id=str(market_id),
                label=str(cfg.get("label", market_id)),
                exchange=str(cfg.get("exchange", "")),
                timezone=str(cfg.get("timezone", "UTC")),
                kind=str(cfg.get("kind", "exchange")),
                regular_open=str(cfg.get("regular_open", "09:30")),
                regular_close=str(cfg.get("regular_close", "16:00")),
                assets=tuple(str(a) for a in (cfg.get("assets") or [])),
            )
        )
    return MarketSessionsConfig(markets=tuple(markets), thresholds=thresholds)
