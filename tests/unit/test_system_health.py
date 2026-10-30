from packages.ops.system_health import (
    _effective_flags,
    _provider_summary,
    _registry_runtime_summary,
)


def test_secondary_provider_staleness_is_visible_without_degrading_decision_health():
    summary = _provider_summary(
        {
            "ohlcv_coingecko": {
                "status": "ok",
                "fallbacks": 8,
                "last_cache_age_seconds": 7200,
            },
            "kraken": {"status": "ok"},
        },
        decision_fallback_used=False,
    )
    assert summary["degraded_count"] == 0
    assert summary["observational_degraded_sources"] == ["ohlcv_coingecko"]
    assert summary["observation_degraded_count"] == 1
    assert summary["total"] == 2


def test_secondary_provider_fallback_used_remains_a_real_degraded_signal():
    summary = _provider_summary(
        {"ohlcv_coingecko": {"status": "ok", "fallbacks": 8, "last_cache_age_seconds": 7200}},
        decision_fallback_used=True,
    )
    assert summary["degraded_count"] == 1
    assert summary["degraded_sources"] == ["ohlcv_coingecko"]


def test_official_bls_observer_does_not_block_decision_health():
    summary = _provider_summary(
        {"macro_bls": {"status": "degraded"}, "yfinance": {"status": "ok"}},
        decision_fallback_used=True,
    )
    assert summary["degraded_count"] == 0
    assert summary["observational_degraded_sources"] == ["macro_bls"]


def test_registry_runtime_diff_is_explicit_and_read_only():
    report = _registry_runtime_summary({"yfinance": {"status": "ok"}})
    assert report["registry_sources"] > 0
    assert "yfinance" in report["runtime_providers"]
    assert report["status"] == "INCOMPLETE"


def test_registry_runtime_aliases_match_orchestrator_names():
    report = _registry_runtime_summary(
        {
            "ohlcv_coingecko": {}, "ohlcv_yfinance": {}, "ohlcv_kraken": {},
            "derivatives_binance": {}, "options_deribit": {},
            "macro_bls": {}, "macro_fred": {}, "macro_eia": {},
            "news": {}, "geo_news": {}, "calendar": {}, "calendar_web": {},
            "rotation": {}, "volatility": {},
        }
    )
    assert report["status"] == "OK"
    assert report["unknown_fetchers"] == []
    assert report["policy_only_fetchers"]


def test_registry_does_not_count_cold_optional_providers_as_runtime():
    report = _registry_runtime_summary(
        {
            "finnhub": {"status": "unknown", "calls": 0},
            "twelvedata": {"status": "unknown", "calls": 0},
            "ohlcv_yfinance": {"status": "ok", "calls": 1},
        }
    )
    assert "finnhub" not in report["runtime_providers"]
    assert "twelvedata" not in report["runtime_providers"]
    assert "ohlcv_yfinance" in report["runtime_providers"]


def test_effective_flags_never_claim_live_execution():
    flags = _effective_flags()
    assert flags["paper_safe"] is True
    assert flags["no_execution"] is True
    assert flags["causal_world_decision_apply"] is False
    assert flags["shadow_effective"]["manual_ready_only"] is True
    assert flags["shadow_effective"]["runtime_writes"] is False
    assert flags["shadow_effective"]["historical_read_only"] is True
    assert flags["shadow_effective"]["routed_to_paper"] is False
    assert flags["shadow_effective"]["paper_mutation"] is False

