"""OHLCV disk cache — live provider'ları rate-limit'ten korur.

- Yol: `OHLCV_CACHE_DIR` env (default `data/runtime/ohlcv/`).
- Dosya: `{symbol}_{tf}.json` → {"symbol","timeframe","fetched_at","bars"}.
- TTL TF'e orantılıdır (15m→5dk ... 1d→6sa). TTL geçmiş cache "stale"
  sayılır; orchestrator live fetch başarısızsa stale cache'e döner
  (gerçek ama eski veri — TF freshness kuralı DEGRADED işaretler).
- Sadece live path yazar; fixture/test modu cache'e dokunmaz.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from packages.data.types import OHLCVBar, Timeframe

CACHE_TTL_SEC: dict[Timeframe, int] = {
    "15m": 300,        # 5 dk
    "1h": 900,         # 15 dk
    "4h": 1800,        # 30 dk (derive edildiği için normalde yazılmaz)
    "1d": 21600,       # 6 sa
    "1w": 86400,       # 24 sa
}

_DEFAULT_DIR = "data/runtime/ohlcv"


def _cache_dir() -> Path:
    return Path(os.environ.get("OHLCV_CACHE_DIR", _DEFAULT_DIR))


def _path(symbol: str, timeframe: Timeframe) -> Path:
    return _cache_dir() / f"{symbol}_{timeframe}.json"


@dataclass
class CachedBars:
    bars: list[OHLCVBar]
    age_seconds: float

    @property
    def fresh(self) -> bool:
        tf = self.bars[0].timeframe if self.bars else "1d"
        return self.age_seconds < CACHE_TTL_SEC.get(tf, 900)


def load(symbol: str, timeframe: Timeframe) -> CachedBars | None:
    p = _path(symbol, timeframe)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(raw["fetched_at"])
        bars = [OHLCVBar.model_validate(b) for b in raw["bars"]]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not bars:
        return None
    age = (datetime.now(UTC) - fetched_at).total_seconds()
    return CachedBars(bars=bars, age_seconds=age)


def save(symbol: str, timeframe: Timeframe, bars: list[OHLCVBar]) -> None:
    if not bars:
        return
    p = _path(symbol, timeframe)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "symbol": symbol,
            "timeframe": timeframe,
            "fetched_at": datetime.now(UTC).isoformat(),
            "bars": [b.model_dump(mode="json") for b in bars],
        }
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        # Cache yazılamaması veri akışını durdurmaz.
        return
