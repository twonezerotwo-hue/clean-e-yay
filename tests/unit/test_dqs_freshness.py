"""DQS freshness follows provider cadence, not one universal five-minute clock."""

from datetime import UTC, datetime, timedelta

from packages.data.quality.dqs import _freshness
from packages.data.types import PriceQuote
from packages.decision.engine import is_execution_ready


def _quote(source: str, age: timedelta) -> PriceQuote:
    return PriceQuote(
        symbol=source.upper(),
        price=100.0,
        ts=datetime.now(UTC) - age,
        source=source,
        verified=True,
        status="OK",
    )


def test_macro_provider_is_not_marked_stale_by_intraday_window() -> None:
    # FRED daily/macro observations remain valid between updates.
    assert _freshness([_quote("fred", timedelta(hours=1))]) > 90.0


def test_unknown_provider_keeps_strict_default_window() -> None:
    assert _freshness([_quote("unknown", timedelta(minutes=10))]) == 0.0


def test_mixed_sources_are_scored_per_quote() -> None:
    score = _freshness(
        [
            _quote("fred", timedelta(hours=1)),
            _quote("unknown", timedelta(minutes=10)),
        ]
    )
    assert 40.0 < score < 60.0


def test_execution_ready_excludes_exploration_without_changing_action() -> None:
    class Decision:
        action = "open_long"
        actionable = True
        expected_value = -0.1
        blocked_by = ["paper_exploration:ev_gate"]

    assert is_execution_ready(Decision()) is False


def test_execution_ready_accepts_positive_ev_open_signal() -> None:
    class Decision:
        action = "open_short"
        actionable = True
        expected_value = 0.2
        blocked_by = ["sizing_layers"]

    assert is_execution_ready(Decision()) is True
