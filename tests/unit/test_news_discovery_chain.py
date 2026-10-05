"""Haber güdümlü keşif zinciri: keşif defteri → tarayıcı → haber öngörüsü → fikir (ağsız)."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from packages.data.types import OHLCVBar
from packages.discovery import ideas, news_discovery, scanner, universe
from packages.discovery import news_forecast as nf

T0 = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
NEWS_CANDS = [
    {"symbol": "FCX", "ticker": "FCX", "name": "Freeport-McMoRan Inc.", "asset_type": "equity",
     "chg_7d_pct": 3.0, "chg_30d_pct": 9.0, "news_strength": 52},
    {"symbol": "COCOA", "ticker": "CC=F", "name": "Kakao", "asset_type": "future",
     "chg_7d_pct": 1.0, "chg_30d_pct": 4.0, "news_strength": 30},   # emtia evreninde zaten var
]


def _bars(tf: str, n: int = 400) -> list[OHLCVBar]:
    step = {"1h": timedelta(hours=1)}.get(tf, timedelta(days=1))
    return [OHLCVBar(symbol="STUB", timeframe=tf, ts=datetime(2026, 1, 1, tzinfo=UTC) + i * step,
                     open=100 + i * 0.1, high=100 + i * 0.1, low=100 + i * 0.1, close=100 + i * 0.1,
                     source="test", verified=True) for i in range(n)]


def test_scanner_prioritises_news_candidates_and_skips_duplicates(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCOVERY_SCAN_PATH", str(tmp_path / "scan.json"))
    monkeypatch.setenv("DISCOVERY_SHADOW_PATH", str(tmp_path / "shadow.jsonl"))
    monkeypatch.setenv("SECTOR_ROTATION_PATH", str(tmp_path / "sector.json"))
    monkeypatch.setattr(scanner, "load_config", lambda: {
        "scan": {"interval_sec": 900, "per_run": 1, "min_bars": 60},
        "commodities": {"items": {"COCOA": {"ticker": "CC=F"}}, "shortlist_n": 1},
    })
    monkeypatch.setattr(scanner, "_regime_label", lambda: "NEUTRAL")
    monkeypatch.setattr(universe, "crypto_shortlist", lambda cfg, fetch_json=None: {
        "status": "OK", "fetched_at": T0.isoformat(), "candidates": [{"symbol": "AAAUSD", "cg_id": "aaa"}]})
    monkeypatch.setattr(universe, "commodity_shortlist", lambda *a, **k: {
        "status": "OK", "fetched_at": T0.isoformat(), "candidates": [{"symbol": "COCOA", "ticker": "CC=F"}]})
    monkeypatch.setattr(news_discovery, "scanner_candidates", lambda cfg=None: NEWS_CANDS)
    monkeypatch.setattr(scanner, "build_timeframe_result", lambda sym, tf, bars: SimpleNamespace(
        status="OK", score_overview=SimpleNamespace(direction_score=75.0), key_levels=SimpleNamespace(atr=1.0)))
    calls = []

    def fetch(ticker, symbol, tf):
        calls.append((ticker, symbol, tf))
        return _bars(tf)

    out = scanner.run_if_due(now=T0, get_bars=lambda s, tf: [], fetch_crypto_bars=lambda *a: None,
                             fetch_ticker_bars=fetch)
    assert out["scanned"] == ["FCX"]                                  # per_run=1 → haber adayı önce
    assert {t for t, s, _ in calls if s == "FCX"} == {"FCX"}           # doğrulanmış Yahoo ticker'ı
    art = json.loads(Path(os.environ["DISCOVERY_SCAN_PATH"]).read_text(encoding="utf-8"))
    assert [c["symbol"] for c in art["news_universe"]["candidates"]] == ["FCX"]   # COCOA tekrar edilmez
    assert art["results"]["FCX"]["kind"] == "news"
    assert scanner.viewmodel()["universe"]["news"] == {"status": "OK", "count": 1, "symbols": ["FCX"]}


def test_news_forecast_uses_llm_chain_for_registry_and_discovered_assets(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_FORECAST_PATH", str(tmp_path / "nf.json"))
    monkeypatch.setenv("NEWS_FORECAST_LEDGER_PATH", str(tmp_path / "nf.jsonl"))
    monkeypatch.setattr("packages.data.registry.assets.all_assets",
                        lambda: [SimpleNamespace(symbol="XAUUSD", label="Gold")])
    monkeypatch.setattr(nf, "_news_candidates", lambda: [{"symbol": "FCX", "ticker": "FCX",
                                                         "name": "Freeport-McMoRan Inc."}])
    rows = [{"title": "Chile copper mine strike halts output", "source": "Reuters", "ts": T0.isoformat(),
             "consequence": "Bakır arzı daralır",
             "impacts": {"FCX": {"d": 1.0, "k": "high"}, "XAUUSD": {"d": -1.0, "k": "low"}}}]
    out = nf.run(T0, scan_artifact={}, discovery_cfg={}, source_table={}, recent_snapshots=lambda n: [],
                 web_search=lambda *a, **k: SimpleNamespace(error="missing_api_key", results=[]),
                 llm_headlines=lambda: rows)
    assert out["added_llm"] == 1
    f = nf.load_forecasts()
    assert f["FCX"]["direction"] == "up" and f["FCX"]["evidence"][0]["origin"] == "llm"
    assert f["XAUUSD"]["direction"] == "down"                          # kayıtlı varlık: YZ zinciri kanıt
    assert f["FCX"]["strength"] > f["XAUUSD"]["strength"]              # yüksek güven > düşük güven


def test_idea_carries_news_chain_into_card_and_dossier():
    art = {"news_universe": {"candidates": [{**NEWS_CANDS[0], "kind": "news"}]},
           "results": {"FCX": {"symbol": "FCX", "verdict": "WOULD_OPEN_LONG", "entry_timeframe": "1h",
                               "expected_value": 0.2, "per_tf": {}}}}
    chain = [{"title": "Chile copper mine strike halts output", "source": "Reuters", "ts": T0.isoformat(),
              "consequence": "Bakır arzı daralır", "direction": "up", "confidence": "high"}]
    built = ideas.build_ideas(art, {}, {"FCX": {"direction": "up", "strength": 50, "n_headlines": 1}}, {},
                              chains={"FCX": chain})
    idea = built[0]
    assert idea["kind"] == "news" and idea["asset_type"] == "equity" and idea["news_chain"] == chain
    d = ideas.dossier(idea)
    assert d["varlik"]["tur"] == "equity"
    assert d["haber_zinciri"] == ["Reuters: Chile copper mine strike halts output → Bakır arzı daralır → up"]
