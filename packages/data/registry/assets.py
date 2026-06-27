"""Asset registry — tek kaynak (config/assets.yaml).

Snapshot evreni, işlem evreni ve likidite sepeti BURADAN türetilir. assets.yaml'a
ekle/çıkar → sistem otomatik okur. (Yeni asset ayrıca provider+ticker ister;
tanımsızsa DATA_UNAVAILABLE — mock yok.)
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import yaml

from packages.data.registry import custom_assets
from packages.data.registry.loader import CONFIG_DIR


@dataclass(frozen=True)
class Asset:
    symbol: str
    label: str
    kind: str
    roles: tuple[str, ...]


@lru_cache(maxsize=1)
def _load_yaml() -> tuple[Asset, ...]:
    path = CONFIG_DIR / "assets.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: list[Asset] = []
    for sym, meta in (raw.get("assets") or {}).items():
        meta = meta or {}
        out.append(
            Asset(
                symbol=str(sym),
                label=str(meta.get("label", sym)),
                kind=str(meta.get("kind", "macro")),
                roles=tuple(meta.get("roles") or []),
            )
        )
    return tuple(out)


def _load() -> tuple[Asset, ...]:
    """YAML (statik, cache'li) + kullanıcı custom asset overlay (her çağrıda
    taze okunur) — yeni eklenen asset anında snapshot/işlem evrenine girer."""
    yaml_assets = list(_load_yaml())
    yaml_symbols = {a.symbol for a in yaml_assets}
    custom = [
        Asset(symbol=c.symbol, label=c.label, kind=c.kind, roles=c.roles)
        for c in custom_assets.all_custom()
        if c.symbol not in yaml_symbols
    ]
    return tuple(yaml_assets + custom)


def all_assets() -> list[Asset]:
    return list(_load())


def by_role(role: str) -> list[Asset]:
    return [a for a in _load() if role in a.roles]


def symbols_by_role(role: str) -> list[str]:
    return [a.symbol for a in by_role(role)]


def get(symbol: str) -> Asset | None:
    return next((a for a in _load() if a.symbol == symbol), None)


def snapshot_symbols() -> list[str]:
    """Snapshot evreni = trade + macro rollerindeki semboller (yaml sırasıyla)."""
    return [a.symbol for a in _load() if ("trade" in a.roles or "macro" in a.roles)]


def trade_symbols() -> list[str]:
    """İşlem evreni — otomatik pozisyon yalnızca bunlarda."""
    return symbols_by_role("trade")


def liquidity_basket() -> list[tuple[str, str, str]]:
    """(symbol, label, kind) — Küresel Likidite Rotasyon sepeti (yaml sırasıyla)."""
    return [(a.symbol, a.label, a.kind) for a in by_role("liquidity")]
