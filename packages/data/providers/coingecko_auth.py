"""CoinGecko ortak yetkilendirme — Demo API anahtarı.

Anahtar `COINGECKO_API_KEY` env'inden okunur (kökteki .env, apps/api/main.py
tarafından yüklenir). Varsa `x-cg-demo-api-key` header'ı eklenir → kimlik
doğrulamalı Demo planı (30 çağrı/dk, 10.000 çağrı/ay). Anahtar yoksa header
eklenmez; public uç sıkı rate-limit'e takılır (provider DEGRADED → mock YOK).

Env her çağrıda okunur (cache yok) ki test monkeypatch ve runtime override
doğru çalışsın.

Aylık kota dolunca (HTTP 429, hata kodu 10006) anahtarlı istek ay sonuna kadar
reddedilir; anahtarsız genel uç ise çalışmaya devam eder (2026-10-30 ölçümü).
Bu durumda anahtar 6 saat kullanılmaz, istekler genel uca gider; sonra yeniden
denenir (ay dönümünde kota açılır).
"""
from __future__ import annotations

import os
import threading
import time

_UA = "clean-e-yay/0.1"
_KEY_PAUSE_SEC = 6 * 3600.0
_KEY_PAUSED_UNTIL = 0.0
_LOCK = threading.Lock()


def api_key() -> str | None:
    key = os.environ.get("COINGECKO_API_KEY")
    return key.strip() if key else None


def key_paused() -> bool:
    with _LOCK:
        return time.monotonic() < _KEY_PAUSED_UNTIL


def note_http_error(code: int, body: str = "") -> bool:
    """Anahtarın aylık kotası dolduysa anahtarı duraklat; duraklattıysa True."""
    global _KEY_PAUSED_UNTIL
    if code != 429 or not api_key() or key_paused():
        return False
    text = body or ""
    if "10006" not in text and "calls limit" not in text:
        return False  # dakikalık sınır: anahtar geçerli, yalnız beklemek gerekir
    with _LOCK:
        _KEY_PAUSED_UNTIL = time.monotonic() + _KEY_PAUSE_SEC
    return True


def reset_key_pause() -> None:
    global _KEY_PAUSED_UNTIL
    with _LOCK:
        _KEY_PAUSED_UNTIL = 0.0


def headers() -> dict[str, str]:
    """User-Agent + (varsa ve duraklatılmadıysa) Demo anahtar header'ı."""
    h = {"User-Agent": _UA}
    key = api_key()
    if key and not key_paused():
        h["x-cg-demo-api-key"] = key
    return h


__all__ = ["api_key", "headers", "key_paused", "note_http_error", "reset_key_pause"]
