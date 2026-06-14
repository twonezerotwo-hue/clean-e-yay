"""Price sanity guard — absolute bounds + jump guard (config-driven).

Phase 2 port from e-yay-codex `paper_trading_service._is_price_sane`. When a data
source malfunctions, absurd prices contaminate across pairs (BTC→$7405, BRENT→$284,
gold/silver swaps). Config (`price_sanity`): `bounds[symbol] = [lo, hi]` and
`max_jump_pct`. Symbols without bounds get a positivity check only.

Two entry points:
  - `price_sane_reason` / `is_price_sane` — OPEN-time gate (absolute bounds; plus an
    optional jump check when a reference price is supplied).
  - `tick_price_usable` — manage/close gate for an *existing* position: usable if the
    price is absolutely in-bounds (a plausible real price — tolerates a stale
    reference) OR a small move from the last sane price. Contamination fails both
    (out of bounds AND a large jump), so it is rejected; we never close/manage on
    garbage.

Restrictive-only: this guard never opens/keeps a position — it only rejects bad
prices.
"""
from __future__ import annotations

from packages.data.registry.loader import load_thresholds


def _cfg() -> dict:
    return load_thresholds().get("price_sanity", {}) or {}


def _max_jump_pct() -> float:
    return float(_cfg().get("max_jump_pct", 30.0))


def _in_bounds(symbol: str, price: float) -> bool:
    """True if price is within the symbol's absolute bounds (or symbol is unbounded)."""
    bounds = (_cfg().get("bounds") or {}).get(symbol)
    if not bounds:
        return True
    lo, hi = float(bounds[0]), float(bounds[1])
    return lo <= price <= hi


def price_sane_reason(
    symbol: str,
    price: float | None,
    *,
    previous_price: float | None = None,
) -> str | None:
    """OPEN-time sanity: return None if sane, else a short machine-readable reason."""
    if price is None or price <= 0:
        return "non_positive_price"
    if not _in_bounds(symbol, price):
        bounds = (_cfg().get("bounds") or {}).get(symbol)
        return f"out_of_bounds[{float(bounds[0]):g},{float(bounds[1]):g}]"
    if previous_price is not None and previous_price > 0:
        pct = abs(price - previous_price) / previous_price * 100.0
        if pct > _max_jump_pct():
            return f"jump_{pct:.0f}pct_gt_{_max_jump_pct():g}pct"
    return None


def is_price_sane(
    symbol: str,
    price: float | None,
    *,
    previous_price: float | None = None,
) -> bool:
    return price_sane_reason(symbol, price, previous_price=previous_price) is None


def tick_price_usable(
    symbol: str,
    price: float | None,
    last_price: float | None = None,
) -> bool:
    """Manage/close gate for an existing position. See module docstring."""
    if price is None or price <= 0:
        return False
    if _in_bounds(symbol, price):
        return True
    if last_price and last_price > 0:
        return abs(price - last_price) / last_price * 100.0 <= _max_jump_pct()
    return False
