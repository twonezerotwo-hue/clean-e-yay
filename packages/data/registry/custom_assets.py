"""Kullanıcı tarafından eklenen asset'lerin runtime overlay'i.

`config/assets.yaml` statik/salt-okunur tek kaynaktır. Kullanıcılar runtime'da
kendi varlıklarını ekleyebilir — bunlar `data/runtime/custom_assets.json`'a
yazılır ve provider/registry katmanlarında statik tanımların ÜSTÜNE eklenir
(additive-only, YAML değişmez). Eklenen asset, eklenme anında gerçek veri
çekilebildiği DOĞRULANMIŞ olmalı (DATA_POLICY: mock yok).

Dosya atomik yazılır. Okunamayan (bozuk) dosyaya ekleme/çıkarma REDDEDİLİR
(`CorruptCustomAssets`): eskiden bozuk dosya boş okunuyor ve sonraki ekleme bütün
özel varlıkları siliyordu. Okuma değişiklik zamanına bağlı önbellekli (guard_overrides
deseni): sağlayıcıların her sembol denetimi dosyayı yeniden çözmez.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from packages.ops.store import write_text_atomic

log = logging.getLogger(__name__)

_LOCK = threading.Lock()
# (path, mtime_ns, size) → çözülmüş sözlük; çağıranlar _LOCK altında erişir.
_CACHE: dict = {"key": None, "data": {}}

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


class CorruptCustomAssets(RuntimeError):
    """custom_assets.json okunamıyor; yazım reddedildi, dosya olduğu gibi korunur."""


def _parse(p: Path) -> dict[str, dict]:
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("custom_assets.json bir sözlük değil")
    return data


def _load_raw() -> dict[str, dict]:
    """Okuyucular için (çağıran _LOCK tutar). Bozuk dosya boş okunur ve bir kez loglanır."""
    p = _path()
    try:
        st = p.stat()
        key = (str(p), st.st_mtime_ns, st.st_size)
    except OSError:
        _CACHE["key"], _CACHE["data"] = None, {}
        return {}
    if _CACHE["key"] != key:
        try:
            data = _parse(p)
        except (OSError, ValueError) as exc:
            log.error("custom_assets okunamadı (%s): %s; özel varlıklar boş sayılıyor", p, exc)
            data = {}
        _CACHE["key"], _CACHE["data"] = key, data
    return _CACHE["data"]


def _load_for_write() -> dict[str, dict]:
    """Yazıcılar için taze okuma (çağıran _LOCK tutar). Bozuk dosya → reddet."""
    p = _path()
    if not p.exists():
        return {}
    try:
        return _parse(p)
    except (OSError, ValueError) as exc:
        raise CorruptCustomAssets(f"{p} okunamıyor ({exc}); dosya korunuyor, elle düzeltilmeli") from exc


def _save_raw(raw: dict[str, dict]) -> None:
    write_text_atomic(_path(), json.dumps(raw, ensure_ascii=False, indent=2))
    _CACHE["key"] = None


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
        raw = _load_for_write()
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
        raw = _load_for_write()
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
