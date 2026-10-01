from __future__ import annotations

from packages.agent.llm.client import LLMCompletion, MockLLMClient
from packages.agent.llm.world_report import build_world_brief


def _evidence():
    return {
        "headlines": [{"title": "Bab el-Mandeb shipping risk rises", "source": "fixture", "verified": True}],
        "world_state": {
            "geopolitical_events": [{
                "event_id": "geo-1",
                "event_type": "CHOKEPOINT_THREAT",
                "source_confidence": 0.8,
            }],
            "graph_context": {
                "graph_version": "world-graph-v1.0",
                "affected_assets": ["BRENT"],
                "factor_channels": ["shipping_risk"],
            },
            "physical_commodity": {
                "status": "INSUFFICIENT_DATA",
                "assessments": {"commodity:crude_oil": {"missing_inputs": ["inventory_release"]}},
            },
            "scenario_report": {"status": "OK", "events": []},
        },
        "causal_shadow": {"forecasts": [{
            "symbol": "BRENT", "horizon": "1d", "available": True,
            "directional_bias": "BULLISH", "current_price": 82.0,
            "p10": 80.0, "p50": 82.5, "p90": 85.0,
        }]},
        "portfolio_risk": {"status": "OK"},
        "risk_gate": {"action": "HOLD", "reason": "clear"},
        "dqs": {"status": "OK", "score": 90},
    }


def test_world_brief_is_deterministic_and_never_execution(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_MODE", "off")
    monkeypatch.setenv("LLM_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("LLM_BUDGET_PATH", str(tmp_path / "budget.json"))
    result = build_world_brief(**_evidence())
    assert result["status"] == "OK"
    assert result["source"] == "fallback"
    assert result["affected_assets"] == ["BRENT"]
    assert result["forecast_bands"][0]["p50"] == 82.5
    assert result["execution"] == "NO_EXECUTION"
    assert result["actionability"] == "OBSERVE_ONLY"
    assert "inventory_release" in result["missing_data"]


def test_world_brief_without_evidence_does_not_call_llm(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("LLM_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("LLM_BUDGET_PATH", str(tmp_path / "budget.json"))
    called = False

    def fail(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("no-event report must not call LLM")

    monkeypatch.setattr(MockLLMClient, "complete", fail)
    result = build_world_brief(
        headlines=[], world_state={}, causal_shadow={}, portfolio_risk={}, risk_gate={}, dqs={"status": "OK"}
    )
    assert result["status"] == "NO_EVENT"
    assert result["source"] == "fallback"
    assert called is False


def test_world_brief_llm_text_only_rewrites_narrative(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("LLM_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("LLM_BUDGET_PATH", str(tmp_path / "budget.json"))

    def structured(self, system, user, max_tokens):
        return LLMCompletion(
            text=(
                "TITLE: Model başlığı\nSUMMARY: Model özeti\n"
                "WHY_IT_MATTERS: Model gerekçesi\nWHAT_TO_WATCH:\n- Yeni doğrulama\n"
                "INVALIDATORS:\n- Resmi yalanlama"
            ),
            model="mock-llm", input_tokens=10, output_tokens=12, source="mock",
        )

    monkeypatch.setattr(MockLLMClient, "complete", structured)
    result = build_world_brief(**_evidence())
    assert result["source"] == "llm"
    assert result["summary"] == "Model özeti"
    # The model cannot replace backend-owned structured evidence.
    assert result["affected_assets"] == ["BRENT"]
    assert result["forecast_bands"][0]["p50"] == 82.5
    assert result["execution"] == "NO_EXECUTION"

    cached = build_world_brief(**_evidence())
    assert cached["llm"]["cached"] is True
