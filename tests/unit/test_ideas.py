"""Fikir Panosu (owner kararı 2026-10-05) — ağa ÇIKMAZ, gerçek LLM çağırmaz."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.discovery import ideas

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)

ART = {
    "crypto_universe": {"candidates": [
        {"symbol": "BTWUSD", "name": "Bitway", "chg_7d_pct": 2.9, "chg_30d_pct": 163.0},
        {"symbol": "QNTUSD", "name": "Quant", "chg_7d_pct": 4.0, "chg_30d_pct": 20.0},
    ]},
    "commodity_universe": {"candidates": [{"symbol": "COPPER", "name": "Bakır", "chg_7d_pct": 1.0, "chg_30d_pct": 6.0}]},
    "rising_sectors": [],
    "results": {
        "BTWUSD": {"symbol": "BTWUSD", "verdict": "WOULD_OPEN_LONG", "entry_timeframe": "1h", "entry": 2.0,
                   "sl": 1.9, "tp": 2.2, "rr": 2.0, "expected_value": 0.34, "confidence": 0.37,
                   "per_tf": {"1h": {"ta": {"bias": "BULLISH"}}, "4h": {"ta": {"bias": "BULLISH"}}}},
        "QNTUSD": {"symbol": "QNTUSD", "verdict": "NO_SIGNAL", "per_tf": {"1d": {"direction_score": 50}}},
        "BTCUSD": {"symbol": "BTCUSD", "verdict": "WOULD_OPEN_LONG"},  # keşif evreninde değil → fikir değil
    },
}
SHADOW = {"BTWUSD": {"n_signals": 35, "resolved": 33, "missed_win": 21, "avoided_loss": 10, "avg_r": 0.93}}
FORECASTS = {
    "COPPER": {"direction": "up", "strength": 55, "n_headlines": 4, "evidence": []},
    "QNTUSD": {"direction": "up", "strength": 20, "n_headlines": 1, "evidence": []},  # zayıf → fikir değil
}

GOOD = """HÜKÜM: GÜÇLÜ
TEZ: Teknik sinyal ve gölge karne birbirini destekliyor.
LEHTE:
- karne %68
ALEYHTE:
- haber kanıtı yok
RİSKLER:
- 30 günde %163 yükseliş
NE_DEĞİŞTİRİR: Haber yönü aşağı dönerse."""


@pytest.fixture
def board(tmp_path, monkeypatch):
    monkeypatch.setenv("IDEA_BOARD_PATH", str(tmp_path / "ideas.json"))
    monkeypatch.setenv("NEWS_FORECAST_PATH", str(tmp_path / "nf.json"))
    monkeypatch.setenv("NEWS_FORECAST_LEDGER_PATH", str(tmp_path / "nf.jsonl"))
    monkeypatch.setenv("LLM_BUDGET_PATH", str(tmp_path / "budget.json"))
    return tmp_path


class FakeClient:
    def __init__(self, text: str | None = GOOD):
        self.text, self.calls = text, 0

    def complete(self, system, user, max_tokens, temperature=0.2):
        self.calls += 1
        assert "işlem emri DEĞİLDİR" in user and "Bitway" in user or "Bakır" in user or "Quant" in user
        if self.text is None:
            return None
        return SimpleNamespace(text=self.text, source="ollama", model="qwen3:8b", input_tokens=100, output_tokens=50)


def _run(client=None, now=NOW, pending=None):
    return ideas.run(now, scan_artifact=ART, shadow_cands=SHADOW, forecasts=FORECASTS,
                     pending=pending or {}, client_factory=(lambda: client) if client is not None else (lambda: None))


def test_candidate_set_and_scores(board):
    built = ideas.build_ideas(ART, SHADOW, FORECASTS, {"BTWUSD": "p1"})
    assert [i["symbol"] for i in built] == ["BTWUSD", "COPPER"]       # QNT zayıf haber, BTC evren dışı
    btw = built[0]
    assert btw["status"] == "AWAITING_APPROVAL" and btw["proposal_id"] == "p1"
    assert btw["components"]["technical"] == pytest.approx(33.6)      # 20 + 0.34*40
    assert btw["components"]["scorecard"] > 0                         # Wilson alt sınır > 0.3
    assert btw["components"]["risk"] == -10                           # 30g +%163
    assert any("163" in n for n in btw["risk_notes"])
    copper = built[1]
    assert copper["components"]["news"] == 13.8 and copper["technical"]["verdict"] == "NO_DATA"  # 55/100*25, 1 ondalık


@pytest.mark.parametrize("text,verdict", [
    (GOOD, "STRONG"),
    ("**Hüküm:** izle\nTez: belirsiz\nRiskler:\n- oynak", "WATCH"),
    ("HUKUM: ZAYIF\nTEZ: kanıt zayıf", "WEAK"),
])
def test_parse_evaluation_variants(text, verdict):
    ev = ideas.parse_evaluation(text)
    assert ev["verdict"] == verdict


def test_parse_evaluation_rejects_missing_or_ambiguous_verdict():
    assert ideas.parse_evaluation("Bu fikir bence iyi.") is None
    assert ideas.parse_evaluation("HÜKÜM: GÜÇLÜ | İZLE | ZAYIF") is None


def test_run_uses_llm_then_caches_by_fingerprint(board):
    client = FakeClient()
    out = _run(client)
    assert out["llm_calls"] == 2 and client.calls == 2                 # 2 fikir, turda en çok 2 çağrı
    saved = json.loads((board / "ideas.json").read_text(encoding="utf-8"))
    btw = next(i for i in saved["ideas"] if i["symbol"] == "BTWUSD")
    assert btw["ai"]["verdict"] == "STRONG" and btw["ai"]["source"] == "ollama"
    assert btw["ai"]["pros"] == ["karne %68"]
    client2 = FakeClient()
    _run(client2, now=NOW + timedelta(hours=1))
    assert client2.calls == 0                                          # parmak izi aynı → yeniden sorulmaz
    _run(client2, now=NOW + timedelta(hours=13))
    assert client2.calls == 2                                          # 12 saat dolunca tazelenir


def test_llm_unavailable_or_unparsed_falls_back(board):
    out = _run(FakeClient(text=None))
    assert out["llm_errors"]
    saved = json.loads((board / "ideas.json").read_text(encoding="utf-8"))
    assert {i["ai"]["source"] for i in saved["ideas"]} == {"deterministic"}
    _run(FakeClient(text="anlamsız cevap"), now=NOW + timedelta(minutes=5))
    saved = json.loads((board / "ideas.json").read_text(encoding="utf-8"))
    assert all(i["ai"]["verdict"] in {"STRONG", "WATCH", "WEAK"} for i in saved["ideas"])


def test_no_llm_mode_gives_deterministic_evaluation(board):
    out = _run(None)
    assert out["llm_calls"] == 0
    vm = ideas.viewmodel()
    assert vm["mode"] == "observe_only" and vm["ideas"][0]["ai"]["source"] == "deterministic"
    assert vm["news"]["scorecard"]["resolved_total"] == 0


def test_promotion_evidence_carries_ai_evaluation(board):
    from packages.discovery import promotion

    _run(FakeClient())
    ev = promotion._ai_evaluation("BTWUSD")
    assert ev["verdict_label"] == "GÜÇLÜ" and ev["source"] == "ollama"
    assert promotion._ai_evaluation("YOKUSD") is None


def test_compact_for_chat_lists_top_ideas(board):
    assert ideas.compact_for_chat()["top"] == []
    _run(FakeClient())
    top = ideas.compact_for_chat()["top"]
    assert [t["symbol"] for t in top] == ["BTWUSD", "COPPER"]
    assert top[0]["ai_verdict"] == "GÜÇLÜ" and top[0]["ai_source"] == "ollama"
    assert top[0]["status"] in ideas.STATUS_LABEL.values()
    assert top[1]["news"] == "up:55"
