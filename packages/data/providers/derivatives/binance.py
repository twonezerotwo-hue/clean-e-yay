"""Binance USDⓈ-M futures public adapter — funding rate + open interest (v2.7 D2).

Public REST API, anahtar gerektirmez. Hata/timeout durumunda None döner;
orchestrator DEGRADED snapshot üretir, asla mock üretmez.

Endpoints:
- premiumIndex   → `lastFundingRate` (8s funding rate, ondalık).
- openInterestHist (period=5m) → `sumOpenInterestValue` (USD notional) son iki
  gözlemden `oi_change_pct` türetilir.

PAPER_SAFE / NO_EXECUTION — yalnızca okuma. Emir/işlem uçları KULLANILMAZ.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

FAPI = "https://fapi.binance.com"
TIMEOUT_SEC = 6.0

# Clean iç sembol → Binance futures sembolü.
_SYMBOL_MAP = {
    "BTCUSD": "BTCUSDT",
    "ETHUSD": "ETHUSDT",
}

SUPPORTED = frozenset(_SYMBOL_MAP.keys())


@dataclass
class RawDerivatives:
    funding_rate: float | None = None
    open_interest_usd: float | None = None
    oi_change_pct: float | None = None


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "clean-e-yay/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            return json.loads(resp.read().decode("utf-8"))
    # Geniş yakalama (news/rss konvansiyonu): herhangi bir hata → None → DEGRADED.
    # Snapshot build asla crash etmez; testlerde live network gerektirmez.
    except Exception:
        return None


def _funding_rate(bsym: str) -> float | None:
    data = _get_json(f"{FAPI}/fapi/v1/premiumIndex?symbol={bsym}")
    if not isinstance(data, dict):
        return None
    try:
        return float(data["lastFundingRate"])
    except (KeyError, TypeError, ValueError):
        return None


def _open_interest(bsym: str) -> tuple[float | None, float | None]:
    """(open_interest_usd, oi_change_pct) — son iki 5m gözleminden."""
    data = _get_json(
        f"{FAPI}/futures/data/openInterestHist?symbol={bsym}&period=5m&limit=2"
    )
    if not isinstance(data, list) or not data:
        return None, None
    try:
        latest = float(data[-1]["sumOpenInterestValue"])
    except (KeyError, TypeError, ValueError, IndexError):
        return None, None
    change = None
    if len(data) >= 2:
        try:
            prev = float(data[-2]["sumOpenInterestValue"])
            if prev > 0:
                change = (latest - prev) / prev
        except (KeyError, TypeError, ValueError, IndexError):
            change = None
    return latest, change


def fetch(symbol: str) -> RawDerivatives | None:
    """Sembol için ham funding + OI. Veri yoksa/hatada None (asla mock)."""
    bsym = _SYMBOL_MAP.get(symbol)
    if bsym is None:
        return None
    funding = _funding_rate(bsym)
    oi_usd, oi_change = _open_interest(bsym)
    if funding is None and oi_usd is None:
        return None
    return RawDerivatives(
        funding_rate=funding,
        open_interest_usd=oi_usd,
        oi_change_pct=oi_change,
    )
