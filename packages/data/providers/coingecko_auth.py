"""CoinGecko ortak yetkilendirme — Demo API anahtarı.

Anahtar `COINGECKO_API_KEY` env'inden okunur (kökteki .env, apps/api/main.py
tarafından yüklenir). Varsa `x-cg-demo-api-key` header'ı eklenir → kimlik
doğrulamalı Demo planı (30 çağrı/dk, 10.000 çağrı/ay). Anahtar yoksa header
eklenmez; public uç sıkı rate-limit'e takılır (provider DEGRADED → mock YOK).

Env her çağrıda okunur (cache yok) ki test monkeypatch ve runtime override
doğru çalışsın.
"""
from __future__ import annotations

import os

_UA = "clean-e-yay/0.1"


def api_key() -> str | None:
    key = os.environ.get("COINGECKO_API_KEY")
    return key.strip() if key else None


def headers() -> dict[str, str]:
    """User-Agent + (varsa) Demo anahtar header'ı."""
    h = {"User-Agent": _UA}
    key = api_key()
    if key:
        h["x-cg-demo-api-key"] = key
    return h


__all__ = ["api_key", "headers"]
