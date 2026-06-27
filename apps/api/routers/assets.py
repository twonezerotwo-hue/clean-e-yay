"""GET /api/v1/assets — asset registry (config/assets.yaml tek kaynağı).

Tüm varlıklar + rolleri + türetilmiş evrenler (trade / snapshot / liquidity).
Frontend etiket/sepet bilgisini buradan dinamik okur.

POST/DELETE /assets/custom — kullanıcının kendi eklediği varlıklar
(`data/runtime/custom_assets.json` overlay, YAML'a dokunmaz). Eklerken
gerçek veri çekilebildiği DOĞRULANIR (DATA_POLICY: mock yok) — ticker
yanlışsa veya provider veri döndürmezse 422 ile reddedilir.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from packages.data.providers.ohlcv import coingecko as ohlcv_coingecko
from packages.data.providers.ohlcv import yfinance as ohlcv_yfinance
from packages.data.registry import assets as registry
from packages.data.registry import custom_assets

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
        "custom": [c.symbol for c in custom_assets.all_custom()],
    }


class CustomAssetRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    label: str = Field(min_length=1, max_length=40)
    provider: str  # "yfinance" | "coingecko"
    ticker: str = Field(min_length=1, max_length=40)
    kind: str = "risk"


@router.post("/assets/custom")
def add_custom_asset(body: CustomAssetRequest) -> dict:
    symbol = body.symbol.strip().upper()
    provider = body.provider.strip().lower()
    if provider not in custom_assets.PROVIDERS:
        raise HTTPException(422, f"provider must be one of {custom_assets.PROVIDERS}")
    if registry.get(symbol) is not None:
        raise HTTPException(409, f"{symbol} zaten kayıtlı (statik veya custom)")

    # Doğrulama: gerçek bar çekilebiliyor mu? (mock yok — başarısızsa reddet)
    bars = _probe_with_ticker(provider, symbol, body.ticker)
    if not bars:
        raise HTTPException(
            422,
            f"{body.ticker} ({provider}) için gerçek veri çekilemedi — "
            "ticker'ı kontrol et (mock/varsayım üretilmez)",
        )

    custom_assets.add(
        custom_assets.CustomAsset(
            symbol=symbol,
            label=body.label.strip(),
            provider=provider,
            ticker=body.ticker.strip(),
            kind=body.kind.strip() or "risk",
            roles=("trade",),
        )
    )
    return {"ok": True, "symbol": symbol, "bars_probed": len(bars)}


def _probe_with_ticker(provider: str, symbol: str, ticker: str) -> list:
    """Henüz overlay'e kaydedilmemiş bir ticker'ın gerçek veri döndürüp
    döndürmediğini dener (yan etkisi yok — `_SYMBOL_MAP`'i değiştirmez)."""
    probe_module = ohlcv_coingecko if provider == "coingecko" else ohlcv_yfinance
    return probe_module.fetch_by_ticker(ticker, symbol, "1d") or []


@router.delete("/assets/custom/{symbol}")
def remove_custom_asset(symbol: str) -> dict:
    ok = custom_assets.remove(symbol.strip().upper())
    if not ok:
        raise HTTPException(404, f"{symbol} custom listede yok")
    return {"ok": True, "symbol": symbol.strip().upper()}
