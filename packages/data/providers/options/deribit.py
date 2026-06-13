"""Deribit public options adapter — BTC/ETH options chain (v2.7 D3).

Public REST API, anahtar gerektirmez. Tek çağrı:
`/public/get_book_summary_by_currency?currency=BTC&kind=option` → her enstrüman
için `mark_iv` (yüzde puan), `open_interest`, `underlying_price` ve
`instrument_name` (örn. `BTC-27JUN25-60000-C`) döner. Strike / vade / call-put
enstrüman adından parse edilir.

Hata/timeout durumunda None döner; orchestrator DEGRADED snapshot üretir,
ASLA mock üretmez. PAPER_SAFE / NO_EXECUTION — yalnızca okuma; emir/işlem
uçları KULLANILMAZ.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime

DERIBIT = "https://www.deribit.com/api/v2"
TIMEOUT_SEC = 8.0

# Clean iç sembol → Deribit currency.
_SYMBOL_MAP = {
    "BTCUSD": "BTC",
    "ETHUSD": "ETH",
}

SUPPORTED = frozenset(_SYMBOL_MAP.keys())


@dataclass
class RawOptionQuote:
    expiry_ts: datetime
    strike: float
    option_type: str               # "call" | "put"
    mark_iv: float                 # annualize ondalık (0.55 = %55)
    open_interest: float = 0.0
    expiry_label: str = ""


@dataclass
class RawOptionsChain:
    underlying_price: float | None = None
    quotes: list[RawOptionQuote] = field(default_factory=list)


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "clean-e-yay/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            return json.loads(resp.read().decode("utf-8"))
    # Geniş yakalama (provider konvansiyonu): herhangi bir hata → None → DEGRADED.
    # Snapshot build asla crash etmez; testlerde live network gerektirmez.
    except Exception:
        return None


def _parse_instrument(name: str) -> tuple[datetime, float, str, str] | None:
    """`BTC-27JUN25-60000-C` → (expiry_ts@08:00 UTC, strike, type, expiry_label)."""
    parts = name.split("-")
    if len(parts) != 4:
        return None
    _ccy, expiry_label, strike_s, cp = parts
    try:
        expiry = datetime.strptime(expiry_label, "%d%b%y").replace(
            hour=8, tzinfo=UTC
        )
        strike = float(strike_s)
    except (ValueError, TypeError):
        return None
    if cp == "C":
        option_type = "call"
    elif cp == "P":
        option_type = "put"
    else:
        return None
    return expiry, strike, option_type, expiry_label


def fetch(symbol: str) -> RawOptionsChain | None:
    """Sembol için ham options chain. Veri yoksa/hatada None (asla mock)."""
    ccy = _SYMBOL_MAP.get(symbol)
    if ccy is None:
        return None
    data = _get_json(
        f"{DERIBIT}/public/get_book_summary_by_currency?currency={ccy}&kind=option"
    )
    rows = data.get("result") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        return None

    underlying: float | None = None
    quotes: list[RawOptionQuote] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("instrument_name")
        mark_iv = row.get("mark_iv")
        if not isinstance(name, str) or mark_iv is None:
            continue
        parsed = _parse_instrument(name)
        if parsed is None:
            continue
        try:
            iv = float(mark_iv) / 100.0     # Deribit mark_iv yüzde puan → ondalık
        except (TypeError, ValueError):
            continue
        if iv <= 0:
            continue
        oi = row.get("open_interest")
        try:
            oi_f = float(oi) if oi is not None else 0.0
        except (TypeError, ValueError):
            oi_f = 0.0
        up = row.get("underlying_price")
        if underlying is None and up is not None:
            try:
                underlying = float(up)
            except (TypeError, ValueError):
                underlying = None
        expiry, strike, option_type, label = parsed
        quotes.append(
            RawOptionQuote(
                expiry_ts=expiry,
                strike=strike,
                option_type=option_type,
                mark_iv=iv,
                open_interest=oi_f,
                expiry_label=label,
            )
        )

    if not quotes:
        return None
    return RawOptionsChain(underlying_price=underlying, quotes=quotes)
