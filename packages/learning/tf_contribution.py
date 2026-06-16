"""Per-TF signal-contribution attribution (closes the step-8 deferred path).

For each composed SymbolAgentView, we record HOW MUCH each timeframe pushed the
consensus toward its direction at decision time. This is the missing primitive that
lets `tf_weight_trainer` attribute a closed trade's realized PnL to the timeframes
that drove the entry — instead of crediting only the entry TF.

Pure math (no I/O). The contribution share for a timeframe is

    share[tf] = |direction_score[tf] - 50| * tf_weight[tf]   (normalized to sum=1)

i.e. the magnitude of each TF's pull toward a directional view, scaled by its
strategy weight when the weights are trusted. A NEUTRAL TF (direction~50) contributes
zero — it did not push the decision. Missing/insufficient TFs contribute zero. Shares
sum to 1.0 when at least one TF contributed; otherwise the snapshot is empty (no
contribution can be attributed → trainer falls back to entry-outcome).

EVIDENCE only — never opens a trade, never feeds the action; this is a measurement
that the learning layer reads at close time. DATA_POLICY: no fabricated value;
empty snapshot when nothing pushed.
"""
from __future__ import annotations

from typing import Any

# ConsensusSnapshot per-TF keys (contract naming).
TF_KEYS: tuple[str, ...] = ("m15", "h1", "h4", "d1", "w1")


def _tf_key_to_canonical(key: str) -> str:
    """m15→15m, h1→1h, h4→4h, d1→1d, w1→1w (config tf_weights uses canonical keys)."""
    return {"m15": "15m", "h1": "1h", "h4": "4h", "d1": "1d", "w1": "1w"}.get(key, key)


def _per_tf_direction(view: Any) -> dict[str, float | None]:
    """Pull per-TF direction_score from the agent's per_timeframe map (m15..w1)."""
    out: dict[str, float | None] = {}
    agent = getattr(view, "agent", None)
    per = getattr(agent, "per_timeframe", {}) or {}
    for k in TF_KEYS:
        res = per.get(k)
        score = getattr(getattr(res, "score_overview", None), "direction_score", None)
        out[k] = float(score) if score is not None else None
    return out


def compute_snapshot(
    view: Any, *, tf_weights: dict[str, float] | None = None
) -> dict[str, float]:
    """Per-TF contribution share for the view's decision (sum=1.0, or empty)."""
    pulls: dict[str, float] = {}
    for k, score in _per_tf_direction(view).items():
        if score is None:
            continue
        magnitude = abs(score - 50.0)  # NEUTRAL → 0 (no push)
        if magnitude <= 0.0:
            continue
        w = 1.0
        if tf_weights is not None:
            w = float(tf_weights.get(_tf_key_to_canonical(k), 0.0) or 0.0)
            if w <= 0.0:
                continue
        pulls[k] = magnitude * w
    total = sum(pulls.values())
    if total <= 0.0:
        return {}
    return {k: round(v / total, 4) for k, v in pulls.items()}


def attributed_pnl_per_tf(
    closed: list[dict],
    snapshots: list[dict],
) -> dict[str, dict[str, float]]:
    """Aggregate per-(strategy, TF) attributed PnL from closed trades + snapshots.

    Each `snapshots` record carries a `contributions[symbol]` mapping (per-TF shares),
    a `snapshot_id`, and a `recorded_at`. Each `closed` trade carries a `snapshot_id`,
    `symbol`, `pnl`, and an `entry_timeframe`. We match by (snapshot_id, symbol), then
    credit `pnl * share[tf]` to each timeframe, bucketed by the trade's strategy.

    Output: `{strategy: {timeframe_canonical: attributed_pnl}}`. Empty when there is
    no matchable data (no faking).
    """
    by_key: dict[tuple[str, str], dict[str, float]] = {}
    for snap in snapshots:
        sid = snap.get("snapshot_id")
        if not sid:
            continue
        contribs = snap.get("contributions") or {}
        for symbol, share_map in contribs.items():
            by_key[(sid, symbol)] = share_map
    out: dict[str, dict[str, float]] = {}
    for trade in closed:
        sid = trade.get("snapshot_id")
        symbol = trade.get("symbol")
        pnl = float(trade.get("pnl") or 0.0)
        strategy = trade.get("strategy")
        if not sid or not symbol or not strategy:
            continue
        share_map = by_key.get((sid, symbol))
        if not share_map:
            continue
        bucket = out.setdefault(strategy, {})
        for tf_key, share in share_map.items():
            canonical = _tf_key_to_canonical(tf_key)
            bucket[canonical] = round(bucket.get(canonical, 0.0) + pnl * float(share), 4)
    return out
