"""Keşif evreni (K-1) — aday kaynakları.

Üç kaynak: (1) kripto top-50 (CoinGecko markets tek liste çağrısı —
ön-süzgeç + momentum kısa listesi; 50 coin'e kör OHLCV çekilmez, API bütçesi
discovery.yaml'da belgeli), (2) sıcak sektörler (K-0b sektör rotasyon
artifact'ından RISING ETF'ler), (3) emtia (Yahoo vadeli/ETF; momentum kısa
listesi, owner kararı 2026-10-05). Veri gelmezse boş liste — mock aday YOK
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


TickerBarsFn = Callable[[str, str, str], list | None]  # (ticker, symbol, tf)


def _pct_change(closes: list[float], n: int) -> float | None:
    if len(closes) <= n or not closes[-1 - n]:
        return None
    return (closes[-1] / closes[-1 - n] - 1.0) * 100.0


def commodity_shortlist(
    cfg: dict, fetch_bars: TickerBarsFn | None = None, now: datetime | None = None
) -> dict:
    """Emtia listesinden momentum kısa listesi (owner kararı 2026-10-05).

    Her emtia için TEK günlük bar çağrısı (Yahoo ticker); 30g/7g momentum harmanı
    kripto kısa listesiyle aynı (`_W_30D/_W_7D`, yalnız pozitif → LONG-only).
    Veri gelmeyen emtia atlanır; hiçbiri gelmezse status=UNAVAILABLE (mock yok).
    """
    from packages.data.providers.ohlcv import yfinance  # yalnız emtia dalında gerekir

    items = dict(cfg.get("items") or {})
    shortlist_n = int(cfg.get("shortlist_n", 4))
    fetched_at = (now or datetime.now(UTC)).isoformat()
    fetch = fetch_bars or yfinance.fetch_by_ticker

    eligible: list[dict] = []
    fetched = 0
    for symbol, meta in items.items():
        meta = dict(meta or {})
        ticker = str(meta.get("ticker") or "")
        if not ticker:
            continue
        bars = [b for b in (fetch(ticker, str(symbol), "1d") or []) if getattr(b, "verified", True)]
        closes = [float(b.close) for b in bars if b.close]
        if len(closes) < 31:
            continue  # 30g momentum ölçülemiyor → aday değil (uydurma yok)
        fetched += 1
        chg7, chg30 = _pct_change(closes, 7), _pct_change(closes, 30)
        if chg7 is None or chg30 is None:
            continue
        momentum = _W_30D * chg30 + _W_7D * chg7
        if momentum <= 0:
            continue
        eligible.append({
            "symbol": str(symbol),
            "ticker": ticker,
            "name": str(meta.get("label") or symbol),
            "chg_7d_pct": round(chg7, 2),
            "chg_30d_pct": round(chg30, 2),
            "momentum": round(momentum, 4),
        })

    if not fetched:
        return {"status": "UNAVAILABLE", "fetched_at": fetched_at,
                "universe_n": len(items), "eligible_n": 0, "candidates": []}
    eligible.sort(key=lambda x: -x["momentum"])
    return {
        "status": "OK",
        "fetched_at": fetched_at,
        "universe_n": len(items),
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
