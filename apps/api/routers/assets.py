"""GET /api/v1/assets — asset registry (config/assets.yaml tek kaynağı).

Tüm varlıklar + rolleri + türetilmiş evrenler (trade / snapshot / liquidity).
Frontend etiket/sepet bilgisini buradan dinamik okur.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.data.registry import assets as registry

router = APIRouter(tags=["assets"])


@router.get("/assets")
def get_assets() -> dict:
    return {
        "assets": [
            {"symbol": a.symbol, "label": a.label, "kind": a.kind, "roles": list(a.roles)}
            for a in registry.all_assets()
        ],
        "trade": registry.trade_symbols(),
        "snapshot": registry.snapshot_symbols(),
        "liquidity": [s for (s, _l, _k) in registry.liquidity_basket()],
    }
