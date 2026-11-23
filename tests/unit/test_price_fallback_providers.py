"""Yedek fiyat kaynakları (TwelveData, AlphaVantage, Finnhub): ağsız ayrıştırma testleri.

Gerçek yanıt biçimleri; hata yanıtı ya da eksik alan → None (zincirde sonrakine geçilir,
sahte fiyat yok). Anahtar yoksa ağ çağrısı yapılmaz.
"""
from __future__ import annotations

import io
import json

import pytest

from packages.data.providers import quota
from packages.data.providers.price import alphavantage, finnhub, twelvedata


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _serve(monkeypatch, mod, payload):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        return _Resp(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    mod._CACHE.clear()
    return seen


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_QUOTA_PATH", str(tmp_path / "quota.json"))
    for k in ("TWELVEDATA_API_KEY", "ALPHAVANTAGE_API_KEY", "FINNHUB_API_KEY"):
        monkeypatch.setenv(k, "test-key")


@pytest.mark.parametrize(
    ("mod", "symbol", "payload", "price"),
    [
        (twelvedata, "XAUUSD", {"price": "4061.25"}, 4061.25),
        (alphavantage, "BTCUSD", {"Realtime Currency Exchange Rate": {"5. Exchange Rate": "91234.5"}}, 91234.5),
        (finnhub, "ETHUSD", {"c": 3021.4, "h": 3100, "l": 2990}, 3021.4),
    ],
)
def test_parses_real_response_as_verified_fallback(monkeypatch, mod, symbol, payload, price):
    _serve(monkeypatch, mod, payload)
    q = mod.get_quote(symbol)
    assert q is not None and q.price == price and q.verified and q.fallback and q.source == mod.__name__.rsplit(".", 1)[-1]
    assert quota.usage()[q.source]["count"] == 1


@pytest.mark.parametrize(
    ("mod", "symbol", "payload"),
    [
        (twelvedata, "XAUUSD", {"code": 429, "status": "error", "message": "limit"}),
        (alphavantage, "BTCUSD", {"Note": "Thank you for using Alpha Vantage! rate limit"}),
        (finnhub, "ETHUSD", {"c": 0}),
    ],
)
def test_error_or_empty_response_returns_none(monkeypatch, mod, symbol, payload):
    _serve(monkeypatch, mod, payload)
    assert mod.get_quote(symbol) is None


@pytest.mark.parametrize("mod", [twelvedata, alphavantage, finnhub])
def test_missing_key_makes_no_network_call(monkeypatch, mod):
    monkeypatch.delenv(f"{mod.__name__.rsplit('.', 1)[-1].upper()}_API_KEY", raising=False)
    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ağ")))
    mod._CACHE.clear()
    assert mod.get_quote(sorted(mod.SUPPORTED)[0]) is None
