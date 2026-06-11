"""AI report narrative — şimdilik deterministik şablon."""
from __future__ import annotations

from packages.consensus.engine import ConsensusResult
from packages.regime.classifier import RegimeOutput


def build_narrative(
    cons_list: list[ConsensusResult],
    regime: RegimeOutput,
) -> tuple[str, str, list[str]]:
    """Returns (verdict, narrative, key_signals)."""
    bullish = [c for c in cons_list if c.direction == "bullish"]
    bearish = [c for c in cons_list if c.direction == "bearish"]
    if len(bullish) >= 2 * max(1, len(bearish)):
        verdict = "bullish"
    elif len(bearish) >= 2 * max(1, len(bullish)):
        verdict = "bearish"
    elif not bullish and not bearish:
        verdict = "no_trade"
    else:
        verdict = "neutral"

    parts = [
        f"Makro rejim {regime.label}.",
        f"{len(bullish)} bullish, {len(bearish)} bearish sinyal aktif.",
    ]
    if cons_list:
        top = max(cons_list, key=lambda c: abs(c.score - 50))
        parts.append(
            f"En güçlü kanaat: {top.symbol} {top.direction} ({top.score:.0f}); "
            f"dominant modül {top.dominant_module}."
        )
    narrative = " ".join(parts)
    key_signals = [
        f"{c.symbol}: {c.direction} {c.score:.0f}" for c in sorted(cons_list, key=lambda c: -abs(c.score - 50))[:5]
    ]
    return verdict, narrative, key_signals
