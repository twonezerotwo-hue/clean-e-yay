"""Signal attribution — closed-trade decision log (append-only JSONL).

Phase 2d port from e-yay-codex signal attribution. When a paper trade closes, its
full decision trail is persisted for learning + audit: opening signal (fingerprint +
reason), exit reason, timeframe, source snapshot id, the RiskGate result and DQS at
open, calibrated confidence, verified-data flag, and the realized outcome.

This is a durable, append-only record separate from paper state (which only keeps a
recent_trades window). Mirrors packages/paper/audit.py: best-effort writes (never
crashes the caller), corrupt lines skipped on read.

PAPER_SAFE / NO_EXECUTION: only records; never opens/sizes/decides.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

DEFAULT_PATH = "data/runtime/decision_log.jsonl"
DEFAULT_MAX_READ = 200
EXECUTION_MODE = "PAPER"  # NO_EXECUTION contract — attribution is paper-only.

if TYPE_CHECKING:
    from packages.paper.state import Trade


def _path() -> Path:
    return Path(os.environ.get("DECISION_LOG_PATH", DEFAULT_PATH))


def _diagnostics(trade: Trade) -> list[str]:
    """Flag missing attribution metadata — logged as diagnostics, never invented.

    Covers source binding (snapshot/fingerprint), the risk-gate decision, DQS, and
    the open reason. Empty list means a fully-attributed close.
    """
    missing: list[str] = []
    if trade.snapshot_id is None:
        missing.append("snapshot_id_missing")
    if trade.fingerprint is None:
        missing.append("fingerprint_missing")
    if trade.open_dqs is None:
        missing.append("dqs_missing")
    if trade.open_risk_action is None:
        missing.append("risk_action_missing")
    if trade.open_reason is None:
        missing.append("open_reason_missing")
    return missing


def entry_for(trade: Trade) -> dict:
    """Build the attribution entry for a closed trade (pure; no I/O)."""
    won = trade.pnl_usd > 0
    return {
        # Deterministic id (replay-friendly): same trade → same record_id.
        "record_id": f"{trade.id}:{trade.closed_at}",
        "recorded_at": datetime.now(UTC).isoformat(),
        "trade_id": trade.id,
        "symbol": trade.symbol,
        "side": trade.side,
        "timeframe": trade.timeframe,
        "opening_signal": {
            "fingerprint": trade.fingerprint,
            "reason": trade.open_reason,
            "snapshot_id": trade.snapshot_id,
            "dqs": trade.open_dqs,
            "risk_gate": trade.open_risk_action,
            "predicted_confidence": trade.predicted_confidence,
            "raw_confidence": trade.raw_confidence,
            "confidence_source": trade.confidence_source,
            "data_verified": trade.data_verified,
        },
        "exit": {
            "reason": trade.close_reason,
            "lifecycle_status": trade.lifecycle_status,
        },
        "outcome": {
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "pnl_usd": trade.pnl_usd,
            "won": won,
        },
        "opened_at": trade.opened_at,
        "closed_at": trade.closed_at,
        "diagnostics": _diagnostics(trade),
        # Safety contract stamped on every record (audit/replay evidence).
        "execution_mode": EXECUTION_MODE,
        "paper_safe": True,
        "no_execution": True,
    }


def _warn_write_failure(trade: Trade, exc: Exception) -> None:
    """Best-effort audit warning when the decision log can't be persisted.

    The audit helper is itself best-effort (swallows its own I/O errors); we still
    guard the whole thing so attribution can NEVER break a trade close.
    """
    try:
        from packages.paper import audit

        audit.record(
            "ERROR",
            reason="decision_log_write_failed",
            trade_id=trade.id,
            error=type(exc).__name__,
        )
    except Exception:  # pragma: no cover — last-resort guard
        pass


def record_close(trade: Trade) -> dict:
    """Append a closed-trade attribution entry (best-effort; never raises)."""
    entry = entry_for(trade)
    try:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        # attribution ASLA lifecycle'ı kesmez — yine de iz bırakmaya çalış.
        _warn_write_failure(trade, exc)
    return entry


def read_recent(limit: int = DEFAULT_MAX_READ) -> list[dict]:
    """Son `limit` attribution kaydı (en yeni en sonda); bozuk satır atlanır."""
    p = _path()
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in lines[-max(1, limit):]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def summary(limit: int = DEFAULT_MAX_READ) -> dict:
    """Attribution özeti — kapanan trade sayısı + win/loss + son kayıt zamanı."""
    rows = read_recent(limit)
    wins = sum(1 for r in rows if (r.get("outcome") or {}).get("won"))
    return {
        "window_trades": len(rows),
        "wins": wins,
        "losses": len(rows) - wins,
        "last_recorded_at": rows[-1].get("recorded_at") if rows else None,
    }


__all__ = ["entry_for", "read_recent", "record_close", "summary"]
