"""Haber güdümlü keşif (owner kararı 2026-10-05, ikinci tur) — ağa ÇIKMAZ, gerçek LLM çağırmaz."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.discovery import news_discovery as nd

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)

CFG = {
    "news_discovery": {"feed_refresh_min": 15, "headlines_per_call": 3, "calls_per_run": 1,
                       "max_new_resolutions_per_run": 8, "min_dollar_volume": 5_000_000},
    "commodities": {"items": {"COFFEE": {"ticker": "KC=F", "label": "Kahve"}}},
}
REGISTRY = {"XAUUSD": "XAUUSD", "GC=F": "XAUUSD", "BTCUSD": "BTCUSD", "BTC-USD": "BTCUSD"}

HEADS = [
    "Chile copper mine strike halts output at Escondida",
    "Frost hits Brazil coffee belt ahead of harvest",
    "Celebrity chef opens new restaurant",
]


def _bars(n=40, close=10.0, volume=2_000_000.0, step=0.01):
    return [SimpleNamespace(close=close * (1 + step) ** i, volume=volume) for i in range(n)]


CHARTS = {
    "FCX": ({"symbol": "FCX", "instrumentType": "EQUITY", "longName": "Freeport-McMoRan Inc.",
             "exchangeName": "NYQ"}, _bars(close=45.0)),
    "COPX": ({"symbol": "COPX", "instrumentType": "ETF", "longName": "Global X Copper Miners ETF"},
             _bars(close=40.0, volume=500_000.0)),
    "KC=F": ({"symbol": "KC=F", "instrumentType": "FUTURE", "shortName": "Coffee Dec 26"}, _bars(close=3.8)),
    "FXY": ({"symbol": "FXY", "instrumentType": "ETF", "longName": "Invesco CurrencyShares Japanese Yen Trust"},
            _bars(close=60.0)),
    "TINY": ({"symbol": "TINY", "instrumentType": "EQUITY", "longName": "Tiny Copper Corp"},
             _bars(close=1.0, volume=1000.0)),
    "^GSPC": ({"symbol": "^GSPC", "instrumentType": "INDEX", "longName": "S&P 500"}, _bars()),
}
SEARCH = {"Antofagasta": [{"symbol": "ANFGF", "type": "EQUITY", "exchange": "PNK", "name": "Antofagasta plc"}],
          "Freeport McMoRan": [{"symbol": "FCX", "type": "EQUITY", "exchange": "NYQ", "name": "Freeport-McMoRan Inc."}]}

GOOD = json.dumps({"e": [
    {"h": 1, "c": "Bakır arzı daralır", "a": [
        {"t": "HG=F", "n": "Copper", "d": "up", "k": "high"},
        {"t": "FCXX", "n": "Freeport McMoRan", "d": "up", "k": "med"},     # uydurma sembol → adla arama
        {"t": "GC=F", "n": "Gold", "d": "up", "k": "low"},                  # kayıtlı varlık → kanıt
    ]},
    {"h": 2, "c": "Kahve arzı düşer", "a": [{"t": "KC=F", "n": "Coffee", "d": "up", "k": "high"}]},
]})


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_DISCOVERY_PATH", str(tmp_path / "nd.json"))
    return tmp_path


class FakeClient:
    def __init__(self, text=GOOD):
        self.text, self.calls, self.prompts = text, 0, []

    def complete(self, system, user, max_tokens, temperature=0.2, *, json_mode=False):
        assert json_mode and "işlem emri değildir" in system
        self.calls += 1
        self.prompts.append(user)
        if self.text is None:
            return None
        return SimpleNamespace(text=self.text, model="qwen3:8b", source="ollama")


class Net:
    def __init__(self, heads=HEADS):
        self.heads, self.fetches, self.charts = heads, 0, []

    def group(self, feeds, *, geo=False, max_items=6):
        assert geo is False and max_items == 15
        self.fetches += 1
        return [SimpleNamespace(title=t, source=f"S{i}", ts=NOW - timedelta(minutes=10 + i))
                for i, t in enumerate(self.heads)], 3, None

    def chart(self, ticker):
        self.charts.append(ticker)
        return CHARTS.get(ticker)

    def search(self, query):
        return SEARCH.get(query, [])


def _run(client, net, now=NOW):
    return nd.run(now, discovery_cfg=CFG, client_factory=lambda: client, fetch_group=net.group,
                  fetch_chart=net.chart, search=net.search, registry=REGISTRY)


# ---------------- ayrıştırma ----------------

def test_parse_extraction_filters_and_salvages_truncated_json():
    text = ('{"e":[{"h":1,"c":"x","a":[{"t":"fcx","n":"Freeport","d":"up","k":"medium"}]},'
            '{"h":1,"c":"dup","a":[{"t":"COPX","n":"c","d":"up","k":"high"}]},'
            '{"h":9,"c":"range","a":[{"t":"X","n":"x","d":"up","k":"high"}]},'
            '{"h":2,"c":"bad dir","a":[{"t":"KC=F","n":"Coffee","d":"sideways","k":"high"}]},'
            '{"h":3,"c":"kesik","a":[{"t":"ZW=F","n":"Wh')  # kesik
    out = nd.parse_extraction(text, 3)
    assert out == [{"h": 1, "c": "x", "a": [{"t": "FCX", "n": "Freeport", "d": "up", "k": "med"}]}]
    assert nd.parse_extraction("model cevap veremedi", 3) is None


def test_name_match_and_symbol_naming():
    assert nd.name_matches("Coffee", "Coffee Dec 26", "KC=F")
    assert nd.name_matches("NVDA", "NVIDIA Corporation", "NVDA")              # sembolün kendisi ad
    assert not nd.name_matches("Fed Funds Rate", "Invesco CurrencyShares Japanese Yen Trust", "FXY")
    ct = {"KC=F": "COFFEE"}
    assert nd.symbol_for("KC=F", "future", ct) == "COFFEE"
    assert nd.symbol_for("CL=F", "future", ct) == "CL_F"                    # CLF hissesiyle çakışmaz
    assert nd.symbol_for("SOL-USD", "crypto", ct) == "SOLUSD"
    assert nd.symbol_for("EURUSD=X", "fx", ct) == "EURUSD"
    assert nd.symbol_for("BRK.B", "equity", ct) == "BRKB"


# ---------------- doğrulama ----------------

def _resolve(prop, state=None, budget=8):
    net = Net()
    state = state if state is not None else {}
    cfg = nd.config(CFG)
    out = nd.resolve(prop, state, cfg, NOW, registry=REGISTRY, commodity_by_ticker={"KC=F": "COFFEE"},
                     fetch_chart=net.chart, search=net.search, budget=[budget])
    return out, net, state


def test_resolve_valid_registry_and_rejections():
    out, _, _ = _resolve({"t": "FCX", "n": "Freeport-McMoRan", "d": "up", "k": "med"})
    assert out["status"] == "valid" and out["symbol"] == "FCX" and out["asset_type"] == "equity"
    assert out["chg_30d_pct"] is not None and out["avg_dollar_volume"] > 5_000_000
    assert _resolve({"t": "GC=F", "n": "Gold"})[0] == {"status": "registry", "symbol": "XAUUSD", "ticker": "GC=F",
                                                       "name": "Gold"}
    assert _resolve({"t": "FXY", "n": "Fed Funds Rate"})[0]["reason"] == "ad_uyusmuyor"
    assert _resolve({"t": "TINY", "n": "Tiny Copper"})[0]["reason"] == "likidite_dusuk"
    assert _resolve({"t": "^GSPC", "n": "S&P 500"})[0]["reason"].startswith("tur_uygun_degil")
    assert _resolve({"t": "TNTA", "n": "Antofagasta"})[0]["reason"] == "sembol_yok"   # arama sonucu ABD dışı/OTC


def test_resolve_falls_back_to_name_search_and_caches():
    out, net, state = _resolve({"t": "FCXX", "n": "Freeport McMoRan"})
    assert out["status"] == "valid" and out["ticker"] == "FCX"
    assert net.charts == ["FCXX", "FCX"]
    out2, net2, _ = _resolve({"t": "FCXX", "n": "Freeport McMoRan"}, state=state)
    assert out2["ticker"] == "FCX" and net2.charts == []                     # önbellek: ağ yok
    assert _resolve({"t": "COPX", "n": "Copper miners"}, budget=0)[0]["status"] == "deferred"


def test_commodity_future_maps_to_existing_commodity_symbol():
    out, _, _ = _resolve({"t": "KC=F", "n": "Coffee"})
    assert out["status"] == "valid" and out["symbol"] == "COFFEE" and out["asset_type"] == "future"


# ---------------- koşu ----------------

def test_run_end_to_end_builds_candidates_and_evidence(store):
    net, client = Net(), FakeClient()
    out = _run(client, net)
    assert out["status"] == "OK" and client.calls == 1 and out["screened"] == 3
    assert out["valid"] == 2 and out["registry"] == 1 and out["rejected"] == {"sembol_yok": 1}  # HG=F grafiği yok
    cands = {c["symbol"]: c for c in nd.all_candidates()}
    assert set(cands) == {"FCX", "COFFEE"} and cands["COFFEE"]["direction"] == "up"
    assert cands["COFFEE"]["strength"] > cands["FCX"]["strength"]           # high > med güven
    scan = nd.scanner_candidates(CFG)
    assert {c["symbol"] for c in scan} == {"FCX", "COFFEE"} and scan[0]["ticker"]
    ev = {h["title"]: h for h in nd.llm_headlines()}
    assert ev[HEADS[0]]["impacts"]["XAUUSD"] == {"d": 1.0, "k": "low"}       # kayıtlı varlığa kanıt
    assert nd.chain_for("COFFEE")[0]["consequence"] == "Kahve arzı düşer"
    vm = nd.viewmodel()
    assert vm["status"] == "OK" and len(vm["events"]) == 2 and vm["stats"]["calls_today"] == 1


def test_seen_headlines_are_not_resent_and_pool_is_cached(store):
    net, client = Net(), FakeClient()
    _run(client, net)
    out = _run(client, net, now=NOW + timedelta(minutes=5))
    assert net.fetches == 1 and out["pool"] == 3                            # 15 dk dolmadan akış yenilenmez
    assert client.calls == 1 and out["llm_calls"] == 0                      # hepsi görüldü


def test_llm_failure_keeps_headlines_for_retry_and_off_mode_skips(store):
    net = Net()
    out = _run(FakeClient(text=None), net)
    assert out["errors"] == ["llm_unavailable"] and out["screened"] == 0
    retry = FakeClient()
    _run(retry, net, now=NOW + timedelta(minutes=5))
    assert retry.calls == 1 and "Chile copper" in retry.prompts[0]
    off = nd.run(NOW, discovery_cfg=CFG, client_factory=lambda: None, fetch_group=net.group,
                 fetch_chart=net.chart, search=net.search, registry=REGISTRY)
    assert off["status"] == "LOCAL_LLM_OFF"


def test_candidates_decay_and_expire(store):
    net = Net()
    _run(FakeClient(), net)
    fresh = nd.all_candidates()[0]["strength"]
    _run(FakeClient(text='{"e":[]}'), Net(heads=["Another headline"]), now=NOW + timedelta(hours=30))
    later = {c["symbol"]: c for c in nd.all_candidates()}
    assert later["COFFEE"]["strength"] < fresh                               # yarı-ömürle zayıflar
    _run(FakeClient(text='{"e":[]}'), Net(heads=["Third"]), now=NOW + timedelta(hours=80))
    assert nd.all_candidates() == []                                        # 72 saatlik defter
