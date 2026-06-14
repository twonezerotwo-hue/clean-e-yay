"""Paper-side handle for the canonical price-sanity guard.

Single source of truth lives in `packages.data.guards.price_sanity`; this module
re-exports it so paper code can import from `packages.paper.guards` without a
duplicate implementation.
"""
from __future__ import annotations

from packages.data.guards.price_sanity import (
    is_price_sane,
    price_sane_reason,
    tick_price_usable,
)

__all__ = ["is_price_sane", "price_sane_reason", "tick_price_usable"]
