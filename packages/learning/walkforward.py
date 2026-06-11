"""Walk-forward özet: 70/30 train/test bölünmesi, basit metrikler."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class WalkForwardSummary:
    train_window: int
    test_window: int
    test_win_rate: float
    test_sharpe: float


def _sharpe(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    if std == 0:
        return 0.0
    return round(mean / std * math.sqrt(252), 3)


def summarize(pnls: list[float]) -> WalkForwardSummary | None:
    if len(pnls) < 5:
        return None
    cut = max(1, int(len(pnls) * 0.7))
    test = pnls[cut:]
    if not test:
        return None
    wins = sum(1 for p in test if p > 0)
    return WalkForwardSummary(
        train_window=cut,
        test_window=len(test),
        test_win_rate=round(wins / len(test), 3),
        test_sharpe=_sharpe(test),
    )
