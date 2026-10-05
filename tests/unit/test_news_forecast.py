"""Haber öngörüsü (owner kararı 2026-10-05) — ağa ÇIKMAZ, canlı data/runtime'a yazmaz."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.discovery import news_forecast as nf

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
DISC_CFG = {
    "commodities": {"items": {"COPPER": {"ticker": "HG=F", "label": "Bakır", "keywords": ["copper"]}}},
    "sector_rotation": {"sectors": {"XLK": {"label": "Teknoloji"}}},
    "news_forecast": {
        "window_hours": 72, "half_life_hours": 24, "snapshots_per_run": 3, "min_track_strength": 20,
        "resolve_hours": [4, 24],
        "web_search": {"max_assets_per_run": 2, "min_interval_hours": 6, "max_results": 3},
        "sector_keywords": {"XLK": ["chip stocks", "tech stocks"]},
    },
}
SCAN = {
    "crypto_universe": {"candidates": [
        {"symbol": "BTWUSD", "cg_id": "bitway", "name": "Bitway"},
        {"symbol": "NEARUSD", "cg_id": "near", "name": "NEAR Protocol"},
    ]},
    "commodity_universe": {"candidates": [{"symbol": "COPPER", "ticker": "HG=F"}]},
    "results": {
        "BTWUSD": {"symbol": "BTWUSD", "verdict": "WOULD_OPEN_LONG", "expected_value": 0.3,
                   "checked_at": NOW.isoformat(), "per_tf": {"1h": {"last_close": 2.0}}},
    },
}


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_FORECAST_PATH", str(tmp_path / "nf.json"))
    monkeypatch.setenv("NEWS_FORECAST_LEDGER_PATH", str(tmp_path / "nf_ledger.jsonl"))
    monkeypatch.setattr("packages.data.registry.assets.all_assets",
                        lambda: [SimpleNamespace(symbol="BTCUSD", label="BTC")])
    return tmp_path


def _assets():
    return nf.build_assets(SCAN, DISC_CFG, nf.config(DISC_CFG))


def test_matching_uses_word_boundaries_and_skips_common_word_tickers(paths):
    a = _assets()
    assert nf._matches(a["COPPER"], "Copper rallies to record on China demand")
    assert not nf._matches(a["COPPER"], "Copperhead Road rerelease tops charts")
    assert nf._matches(a["BTWUSD"], "Bitway (BTW) jumps 20% after exchange listing")
    assert nf._matches(a["BTWUSD"], "$BTW holders cheer")
    assert not nf._matches(a["NEARUSD"], "Gold NEAR record as dollar slips")   # stop-ticker
    assert nf._matches(a["NEARUSD"], "NEAR Protocol unveils AI chain upgrade")  # ad eşleşmesi
    assert nf._matches(a["XLK"], "Chip stocks surge on AI spending")


def test_source_weight_rewards_predictive_buckets():
    table = {"buckets": {"BBC|bearish": {"verdict": "PREDICTIVE", "hit_rate": 0.68},
                         "X|bullish": {"verdict": "NO_EDGE", "hit_rate": 0.48}}}
    assert nf.source_weight(table, "BBC", "bearish", "rss") == pytest.approx(1.36)
    assert nf.source_weight(table, "X", "bullish", "rss") == 0.8
    assert nf.source_weight(table, "Unknown", "bullish", "rss") == 1.0
    assert nf.source_weight(table, "BBC", "bearish", "web") == 0.7


def _h(title, hours_ago=1, sentiment="neutral", source="Reuters", impact=None):
    return {"title": title, "source": source, "origin": "rss", "sentiment": sentiment,
            "ts": (NOW - timedelta(hours=hours_ago)).isoformat(), "impact": impact or {}}


def test_forecast_direction_strength_and_decay(paths):
    a = _assets()["COPPER"]
    heads = [_h("Copper rallies as China stimulus lifts demand"),
             _h("Copper jumps to two-month high", hours_ago=2),
             _h("Copper slips on profit taking", hours_ago=60)]   # eski + zayıf ağırlık
    f = nf.forecast_for(a, heads, {}, NOW, 24)
    assert f["direction"] == "up" and f["n_headlines"] == 3 and 0 < f["strength"] <= 100
    assert f["evidence"][0]["direction"] == 1.0
    mixed = nf.forecast_for(a, [_h("Copper rallies"), _h("Copper slides")], {}, NOW, 24)
    assert mixed["direction"] == "neutral"
    assert nf.forecast_for(a, [_h("Gold edges higher")], {}, NOW, 24) is None


def test_registry_asset_uses_ingest_impact(paths):
    a = _assets()["BTCUSD"]
    f = nf.forecast_for(a, [_h("Bitcoin slides", impact={"BTCUSD": -1.0}), _h("Unrelated")], {}, NOW, 24)
    assert f["direction"] == "down" and f["n_headlines"] == 1


def _snap_doc(titles, price=2.0):
    return {"causal_reconstruction": {"headlines": [
                {"title": t, "source": "CoinDesk", "ts": (NOW - timedelta(hours=1)).isoformat(),
                 "sentiment": "bullish", "verified": True, "asset_impact": {}} for t in titles]},
            "data_snapshot": {"prices": [{"symbol": "BTCUSD", "price": 80000.0}]}}


def test_run_end_to_end_with_limited_web_search(paths):
    calls = []

    def fake_search(query, **kw):
        calls.append(query)
        hits = [SimpleNamespace(title="Bitway rallies after partnership", content="Bitway token climbs",
                                url="https://www.example.com/a", published_date=None)]
        return SimpleNamespace(error=None, results=hits if "Bitway" in query else [])

    out = nf.run(NOW, scan_artifact=SCAN, discovery_cfg=DISC_CFG, source_table={},
                 recent_snapshots=lambda n: [_snap_doc(["Copper rallies on supply cuts"])],
                 web_search=fake_search)
    assert out["status"] == "OK" and out["added_rss"] == 1 and out["added_web"] == 1
    assert calls[0].startswith("Bitway") and len(calls) == 2           # en çok 2 aday aranır
    state = json.loads((paths / "nf.json").read_text(encoding="utf-8"))
    assert state["forecasts"]["BTWUSD"]["direction"] == "up"
    assert state["forecasts"]["COPPER"]["direction"] == "up"
    calls.clear()
    nf.run(NOW + timedelta(hours=1), scan_artifact=SCAN, discovery_cfg=DISC_CFG, source_table={},
           recent_snapshots=lambda n: [], web_search=fake_search)
    assert "Bitway crypto price news" not in calls                     # 6 saat dolmadan tekrar aranmaz


def test_missing_web_key_stops_searching(paths):
    calls = []

    def no_key(query, **kw):
        calls.append(query)
        return SimpleNamespace(error="missing_api_key", results=[])

    out = nf.run(NOW, scan_artifact=SCAN, discovery_cfg=DISC_CFG, source_table={},
                 recent_snapshots=lambda n: [], web_search=no_key)
    assert len(calls) == 1 and out["web_errors"] == ["missing_api_key"]


def test_scorecard_resolves_tracked_forecasts(paths):
    def snaps(price_btw):
        return lambda n: [_snap_doc(["Bitway rallies on listing", "Bitway jumps again"])]

    scan = json.loads(json.dumps(SCAN))
    nf.run(NOW, scan_artifact=scan, discovery_cfg=DISC_CFG, source_table={},
           recent_snapshots=snaps(2.0), web_search=lambda q, **k: SimpleNamespace(error=None, results=[]))
    state = json.loads((paths / "nf.json").read_text(encoding="utf-8"))
    assert any(o["symbol"] == "BTWUSD" for o in state["open"])
    later = NOW + timedelta(hours=5)
    scan["results"]["BTWUSD"]["checked_at"] = later.isoformat()
    scan["results"]["BTWUSD"]["per_tf"]["1h"]["last_close"] = 2.2      # +%10 → isabet
    nf.run(later, scan_artifact=scan, discovery_cfg=DISC_CFG, source_table={},
           recent_snapshots=snaps(2.2), web_search=lambda q, **k: SimpleNamespace(error=None, results=[]))
    card = nf.scorecard()
    assert card["horizons"]["4h"]["all"]["hits"] >= 1
    assert card["horizons"]["4h"]["by_kind"]["crypto"]["hit_rate"] == 1.0


def test_stale_registry_impacts_are_reclassified_with_current_classifier(paths, monkeypatch):
    monkeypatch.setattr("packages.data.registry.assets.all_assets",
                        lambda: [SimpleNamespace(symbol="TEM", label="tem", asset_class="risk")])
    stale = {"title": "Gold prices rise after weak September jobs report", "source": "Gold Wire", "origin": "rss",
             "ts": NOW.isoformat(), "sentiment": "bearish", "impact": {"TEM": -1.0}}   # eski alt-dize etiketi
    (paths / "nf.json").write_text(json.dumps({"headlines": {"k1": stale}}), encoding="utf-8")
    out = nf.run(NOW, scan_artifact={}, discovery_cfg=DISC_CFG, source_table={}, recent_snapshots=lambda n: [],
                 web_search=lambda *a, **k: SimpleNamespace(error="missing_api_key", results=[]),
                 llm_headlines=lambda: [])
    assert out["reclassified"] == 1
    assert "TEM" not in nf.load_forecasts()                            # "Sep·tem·ber" artık TEM değil
