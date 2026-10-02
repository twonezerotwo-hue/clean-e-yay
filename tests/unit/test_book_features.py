from __future__ import annotations

from packages.data.types import (
    ConfirmationSignal,
    TechnicalDataQuality,
    TechnicalKeyLevels,
    TechnicalTimeframeResult,
    TechnicalTimeframeSummary,
)
from packages.knowledge.book_features import build_from_agent


class _Agent:
    def __init__(self, result: TechnicalTimeframeResult) -> None:
        self.per_timeframe = {"h1": result}


def test_book_features_are_shadow_only_and_replay_ready():
    result = TechnicalTimeframeResult(
        symbol="BTCUSD",
        timeframe="1h",
        data_quality=TechnicalDataQuality(status="OK", bars_used=300),
        key_levels=TechnicalKeyLevels(stop_reference=99.0, target_reference=103.0),
        confirmation_signals=[ConfirmationSignal(name="close", fired=True)],
        timeframe_summary=TechnicalTimeframeSummary(bias="BULLISH"),
    )
    out = build_from_agent(_Agent(result))
    cell = out["cells"][0]
    assert out["promotion_status"] == "shadow"
    assert out["promoted_to_decision"] is False
    assert out["applied"] is False
    assert cell["invalidation_ready"] is True
    assert cell["target_ready"] is True
    assert cell["evidence_only"] is True
