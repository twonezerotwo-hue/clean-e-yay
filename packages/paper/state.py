"""Paper trading state — JSON dosyası bazlı kalıcılık."""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import load_thresholds

STATE_PATH = Path(
    os.environ.get("PAPER_STATE_PATH", "data/runtime/paper_state.json")
)
_LOCK = threading.Lock()


@dataclass
class Position:
    id: str
    symbol: str
    side: str             # long / short
    entry_price: float
    current_price: float
    size_usd: float
    sl: float | None
    tp: float | None
    opened_at: str
    fingerprint: str | None = None
    data_verified: bool = False  # quote.verified at open; learning filters non-verified
    predicted_confidence: float | None = None  # calibrated p(win) at open
    raw_confidence: float | None = None        # pre-calibration p(win)
    confidence_source: str | None = None       # identity | fitted | insufficient
    timeframe: str = "1d"  # T0 additive — legacy kayıtlar default "1d" yüklenir
    # T2 — TF time-stop: dolunca TIME_STOP_EXIT. None → time-stop yok
    # (legacy kayıtlar None ile yüklenir; davranış değişmez).
    valid_until: str | None = None

    @property
    def unrealized_pnl_usd(self) -> float:
        if self.side == "long":
            return (self.current_price - self.entry_price) / self.entry_price * self.size_usd
        return (self.entry_price - self.current_price) / self.entry_price * self.size_usd


@dataclass
class Trade:
    id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    pnl_usd: float
    opened_at: str
    closed_at: str
    close_reason: str
    fingerprint: str | None = None
    data_verified: bool = False  # mirrors Position; learning trainer filters
    predicted_confidence: float | None = None
    raw_confidence: float | None = None
    confidence_source: str | None = None
    timeframe: str = "1d"  # T0 additive — legacy kayıtlar default "1d" yüklenir


@dataclass
class PaperState:
    equity_usd: float
    peak_equity_usd: float
    realized_pnl_usd: float = 0.0
    open_positions: list[Position] = field(default_factory=list)
    recent_trades: list[Trade] = field(default_factory=list)
    daily_pnl_usd: float = 0.0
    daily_anchor_date: str = ""

    def to_dict(self) -> dict:
        return {
            "equity_usd": self.equity_usd,
            "peak_equity_usd": self.peak_equity_usd,
            "realized_pnl_usd": self.realized_pnl_usd,
            "daily_pnl_usd": self.daily_pnl_usd,
            "daily_anchor_date": self.daily_anchor_date,
            "open_positions": [asdict(p) for p in self.open_positions],
            "recent_trades": [asdict(t) for t in self.recent_trades[-200:]],
        }

    @classmethod
    def from_dict(cls, d: dict) -> PaperState:
        return cls(
            equity_usd=float(d.get("equity_usd", 0)),
            peak_equity_usd=float(d.get("peak_equity_usd", 0)),
            realized_pnl_usd=float(d.get("realized_pnl_usd", 0)),
            daily_pnl_usd=float(d.get("daily_pnl_usd", 0)),
            daily_anchor_date=str(d.get("daily_anchor_date", "")),
            open_positions=[Position(**p) for p in d.get("open_positions", [])],
            recent_trades=[Trade(**t) for t in d.get("recent_trades", [])],
        )


def _initial_state() -> PaperState:
    th = load_thresholds()["paper_trading"]
    equity = float(th["initial_equity_usd"])
    return PaperState(equity_usd=equity, peak_equity_usd=equity)


def load() -> PaperState:
    with _LOCK:
        if not STATE_PATH.exists():
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            state = _initial_state()
            STATE_PATH.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
            return state
        try:
            return PaperState.from_dict(json.loads(STATE_PATH.read_text(encoding="utf-8")))
        except Exception:
            return _initial_state()


def save(state: PaperState) -> None:
    with _LOCK:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")


def utc_iso() -> str:
    return datetime.now(UTC).isoformat()
