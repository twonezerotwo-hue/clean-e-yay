"""GET /api/v1/analysis/asset/{symbol} — geçici (ephemeral) asset teknik analizi.

Desteklenen herhangi bir sembol için on-demand multi-TF teknik analiz (RSI/EMA/
skor + momentum). Gözlemci; işlem evrenine eklemez, otomatik işlem AÇMAZ.
Veri yoksa available=false (mock yok). PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.analysis.ephemeral import analyze_symbol

router = APIRouter(tags=["analysis"])


@router.get("/analysis/asset/{symbol}")
def get_asset_analysis(symbol: str) -> dict:
    return analyze_symbol(symbol)
