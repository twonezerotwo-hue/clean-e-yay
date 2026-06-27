"""Kullanıcı tarafından eklenen asset'lerin runtime overlay'i.

`config/assets.yaml` statik/salt-okunur tek kaynaktır. Kullanıcılar runtime'da
kendi varlıklarını ekleyebilir — bunlar `data/runtime/custom_assets.json`'a
yazılır ve provider/registry katmanlarında statik tanımların ÜSTÜNE eklenir
(additive-only, YAML değişmez). Eklenen asset, eklenme anında gerçek veri
çekilebildiği DOĞRULANMIŞ olmalı (DATA_POLICY: mock yok).
"""
from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

_LOCK = threading.Lock()

PROVIDERS = ("yfinance", "coingecko")


def _path() -> Path:
    p = Path(os.environ.get("CUSTOM_ASSETS_PATH", "data/runtime/custom_assets.json"))
    return p if p.is_absolute() else Path(__file__).resolve().parents[3] / p


@dataclass(frozen=True)
class CustomAsset:
    symbol: str
    label: str
    provider: str  # "yfinance" | "coingecko"
    ticker: str  # provider-spesifik sembol/id (örn. "NVDA", "solana")
    kind: str = "risk"
    roles: tuple[str, ...] = ("trade",)


def _load_raw() -> dict[str, dict]:
    p = _path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_raw(raw: dict[str, dict]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")


def all_custom() -> list[CustomAsset]:
    with _LOCK:
        raw = _load_raw()
    out: list[CustomAsset] = []
    for sym, meta in raw.items():
        out.append(
            CustomAsset(
                symbol=sym,
                label=str(meta.get("label", sym)),
                provider=str(meta.get("provider", "yfinance")),
                ticker=str(meta.get("ticker", sym)),
                kind=str(meta.get("kind", "risk")),
                roles=tuple(meta.get("roles") or ["trade"]),
            )
        )
    return out


def get(symbol: str) -> CustomAsset | None:
    return next((a for a in all_custom() if a.symbol == symbol), None)


def add(asset: CustomAsset) -> None:
    with _LOCK:
        raw = _load_raw()
        raw[asset.symbol] = {
            "label": asset.label,
            "provider": asset.provider,
            "ticker": asset.ticker,
            "kind": asset.kind,
            "roles": list(asset.roles),
        }
        _save_raw(raw)


def remove(symbol: str) -> bool:
    with _LOCK:
        raw = _load_raw()
        if symbol not in raw:
            return False
        del raw[symbol]
        _save_raw(raw)
    return True


def ticker_for(symbol: str, provider: str) -> str | None:
    asset = get(symbol)
    if asset is None or asset.provider != provider:
        return None
    return asset.ticker


class DynamicSymbolSet:
    """Statik `frozenset` + runtime custom overlay'i birleştiren `in`/iter
    destekli küme. Provider modüllerinin `SUPPORTED` alanı için kullanılır —
    her erişimde overlay dosyası taze okunur (yeni eklenen asset anında görünür).
    """

    def __init__(self, static: frozenset[str], provider: str) -> None:
        self._static = static
        self._provider = provider

    def _dynamic(self) -> set[str]:
        return {a.symbol for a in all_custom() if a.provider == self._provider}

    def __contains__(self, item: object) -> bool:
        return item in self._static or item in self._dynamic()

    def __iter__(self) -> Iterator[str]:
        return iter(self._static | self._dynamic())

    def __len__(self) -> int:
        return len(self._static | self._dynamic())
