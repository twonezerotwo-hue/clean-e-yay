"""Keşif evreni (K-1) — aday kaynakları.

İki kaynak: (1) kripto top-50 (CoinGecko markets tek liste çağrısı —
ön-süzgeç + momentum kısa listesi; 50 coin'e kör OHLCV çekilmez, API bütçesi
discovery.yaml'da belgeli), (2) sıcak sektörler (K-0b sektör rotasyon
artifact'ından RISING ETF'ler). Veri gelmezse boş liste — mock aday YOK
(DATA_POLICY). İşlem açmaz; yalnız tarayıcıya (scanner) aday listesi verir.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime

from packages.data.providers import coingecko_auth
from packages.data.providers.ohlcv import coingecko as cg_ohlcv
from packages.data.registry import custom_assets
from packages.discovery import sector_rotation

MARKETS_API = "https://api.coingecko.com/api/v3/coins/markets"
TIMEOUT_SEC = 10.0

# Momentum harmanı: 30g baskın (kalıcılık), 7g tazelik — v1 LONG-only olduğu
# için yalnız POZİTİF momentum aday olur.
_W_30D, _W_7D = 0.6, 0.4

# Dışlanan CoinGecko id'leri: stablecoin'ler (fiyat keşfi değil peg takibi) +
# wrapped/staked dublörler (ana varlığın kopyası — ayrı "keşif" değildir; BTC/
# ETH zaten canlı evrende). Statik veri-temizliği listesi; nadiren değişir.
EXCLUDED_IDS = frozenset({
    # stablecoin
    "tether", "usd-coin", "dai", "first-digital-usd", "ethena-usde",
    "true-usd", "usdd", "frax", "paypal-usd", "binance-usd", "usds",
    "gemini-dollar", "usual-usd", "susds", "falcon-finance",
    # wrapped / liquid-staking dublörleri
    "wrapped-bitcoin", "coinbase-wrapped-btc", "wrapped-steth", "staked-ether",
    "wrapped-eeth", "weth", "rocket-pool-eth", "kelp-dao-restaked-eth",
    "solv-btc", "lombard-staked-btc", "binance-staked-sol", "wrapped-avax",
})

FetchJson = Callable[[str], list | dict | None]


def _default_fetch_json(url: str) -> list | dict | None:
    req = urllib.request.Request(url, headers=coingecko_auth.headers())
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def _existing_cg_ids() -> set[str]:
    """Canlı evrende zaten olan CoinGecko id'leri (statik harita + custom)."""
    ids = set(cg_ohlcv._SYMBOL_MAP.values())
    ids.update(
        a.ticker for a in custom_assets.all_custom() if a.provider == "coingecko"
    )
    return ids


def crypto_shortlist(cfg: dict, fetch_json: FetchJson | None = None) -> dict:
    """Top-N kripto listesinden momentum kısa listesi. TEK ağ çağrısı.

    Dönen dict tarayıcı artifact'ına gömülür (markets_ttl_sec boyunca yeniden
    çekilmez). Liste alınamazsa candidates=[] + status=UNAVAILABLE (mock yok).
    """
    top_n = int(cfg.get("top_n", 50))
    min_vol = float(cfg.get("min_total_volume_usd", 0))
    shortlist_n = int(cfg.get("shortlist_n", 5))
    fetched_at = datetime.now(UTC).isoformat()

    fetch = fetch_json or _default_fetch_json
    url = (
        f"{MARKETS_API}?vs_currency=usd&order=market_cap_desc"
        f"&per_page={top_n}&page=1&price_change_percentage=7d%2C30d"
    )
    rows = fetch(url)
    if not isinstance(rows, list) or not rows:
        return {
            "status": "UNAVAILABLE", "fetched_at": fetched_at,
            "universe_n": 0, "eligible_n": 0, "candidates": [],
        }

    existing = _existing_cg_ids()
    eligible: list[dict] = []
    for row in rows:
        try:
            cg_id = str(row["id"])
            sym = str(row["symbol"]).upper()
            vol = float(row.get("total_volume") or 0)
            chg7 = row.get("price_change_percentage_7d_in_currency")
            chg30 = row.get("price_change_percentage_30d_in_currency")
        except (KeyError, TypeError, ValueError):
            continue
        if cg_id in EXCLUDED_IDS or cg_id in existing or vol < min_vol:
            continue
        if chg7 is None or chg30 is None:
            continue  # momentum ölçülemiyor → aday değil (uydurma yok)
        momentum = _W_30D * float(chg30) + _W_7D * float(chg7)
        if momentum <= 0:
            continue  # v1 LONG-only: yalnız pozitif momentum
        eligible.append({
            "symbol": f"{sym}USD",
            "cg_id": cg_id,
            "name": str(row.get("name") or sym),
            "market_cap_rank": row.get("market_cap_rank"),
            "chg_7d_pct": round(float(chg7), 2),
            "chg_30d_pct": round(float(chg30), 2),
            "momentum": round(momentum, 4),
        })

    eligible.sort(key=lambda x: -x["momentum"])
    return {
        "status": "OK",
        "fetched_at": fetched_at,
        "universe_n": len(rows),
        "eligible_n": len(eligible),
        "candidates": eligible[:shortlist_n],
    }


def sector_candidates() -> list[dict]:
    """K-0b artifact'ından RISING sektör ETF'leri (güç sırasıyla) — v1'de
    aday = ETF'nin kendisi (owner kararı). Artifact yoksa boş liste."""
    art = sector_rotation._load_artifact()
    rising = [
        s for s in (art.get("sectors") or [])
        if s.get("verdict") == "RISING" and s.get("rank") is not None
    ]
    rising.sort(key=lambda s: s["rank"])
    return [
        {
            "symbol": str(s["sector"]),
            "kind": "sector_etf",
            "label": str(s.get("label") or s["sector"]),
            "sector_score": s.get("score"),
            "sector_rank": s.get("rank"),
        }
        for s in rising
    ]
