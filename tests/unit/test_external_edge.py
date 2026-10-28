from datetime import UTC, datetime, timedelta

from packages.learning import external_edge


def _rows(n=120, sign=1.0):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        {
            "_as_of": start + timedelta(days=i),
            "_return": sign * 0.01,
            "symbol": "BTCUSD",
            "direction": "bullish",
            "regime_label": "OFFENSIVE",
        }
        for i in range(n)
    ]


def test_external_edge_is_chronological_and_not_ready_on_small_holdout(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTERNAL_EDGE_PATH", str(tmp_path / "edge.json"))
    report = external_edge.run(records=_rows(80), now=datetime(2026, 5, 1, tzinfo=UTC))
    assert report["status"] == "INSUFFICIENT"
    assert report["holdout"]["n"] == 24
    assert report["paper_safe"] is True
    assert report["no_execution"] is True


def test_external_edge_can_be_ready_only_on_positive_holdout(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTERNAL_EDGE_PATH", str(tmp_path / "edge.json"))
    report = external_edge.run(records=_rows(400), now=datetime(2027, 2, 1, tzinfo=UTC))
    assert report["status"] == "READY"
    assert report["holdout"]["avg_net_return"] > 0
    assert report["holdout"]["win_rate_wilson_lower_95"] > 0.5


def test_negative_holdout_is_not_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTERNAL_EDGE_PATH", str(tmp_path / "edge.json"))
    report = external_edge.run(records=_rows(400, sign=-1.0), now=datetime(2027, 2, 1, tzinfo=UTC))
    assert report["status"] == "UNPROVEN"
