"""GET /api/v1/liquidity/rotation — Küresel Likidite Rotasyon Haritası.

Sabit sepet (BTC/Hisse/Altın/Gümüş/Brent/Tahvil/Nakit) için 1D/7D/30D flow
skoru + risk-on/off rejimi + çelişki uyarıları. Gözlemci; karar VERMEZ.
Veri yalnızca OHLCV cache'inden (close+volume). PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.liquidity import rotation

router = APIRouter(tags=["liquidity"])


@router.get("/liquidity/rotation")
def get_liquidity_rotation() -> dict:
    return rotation.compute()
