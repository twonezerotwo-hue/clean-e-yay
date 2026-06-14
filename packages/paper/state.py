"""Paper trading state — JSON dosyası bazlı kalıcılık.

P1 — robustness: atomik yazım (temp + os.replace), `schema_version`, corrupt
dosya → yedek + default (crash yok), legacy/forward-uyumlu yükleme (bilinmeyen
alanlar atlanır, eksik alanlar default'a düşer). PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import load_thresholds
from packages.paper import audit

SCHEMA_VERSION = 1

STATE_PATH = Path(
    os.environ.get("PAPER_STATE_PATH", "data/runtime/paper_state.json")
)
_LOCK = threading.Lock()


def _only_known(cls, d: dict) -> dict:
    """Yalnızca `cls` dataclass alanlarını süz — legacy/forward uyumlu yükleme.

    Bilinmeyen alanlar atlanır (yeni şemadan gelen ekstra alanlar eski kodu
    patlatmaz); eksik alanlar dataclass default'una düşer (legacy kayıtlar).
    """
    known = {f.name for f in fields(cls)}
    return {k: v for k, v in d.items() if k in known}


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
    # P1 — lifecycle state machine (additive; legacy kayıtlar default'a düşer).
    # OPEN → (EXPIRED_PENDING_PRICE | EXIT_PENDING | ERROR_STATE) → terminal Trade.
    lifecycle_status: str = "OPEN"
    time_stop_expired: bool = False
    pending_exit_reason: str | None = None  # neden exit bekliyor (fiyat yoksa)
    open_reason: str | None = None          # learning handoff: karar gerekçesi
    snapshot_id: str | None = None          # learning handoff: kaynak snapshot
    scale_in: bool = False                  # explicit scale-in (default: yok)

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
    # P1 — terminal lifecycle + learning handoff (additive).
    lifecycle_status: str = "CLOSED"   # CLOSED (normal) | FORCE_CLOSED (zorla)
    open_reason: str | None = None
    snapshot_id: str | None = None


@dataclass
class ManualReady:
    """Owner-approval candidate (DEFENSIVE/CRISIS regime → no auto-open)."""
    id: str
    symbol: str
    timeframe: str
    side: str               # long / short
    requested_at: str
    size_multiplier: float
    requested_price: float | None = None
    reason: str | None = None
    fingerprint: str | None = None
    snapshot_id: str | None = None
    rejected_at: str | None = None  # set when owner rejected (→ silent block)


@dataclass
class RejectedSignal:
    """Owner-rejected signal — silent-blocks the same symbol+side+timeframe."""
    symbol: str
    timeframe: str
    side: str
    rejected_at: str
    fingerprint: str | None = None


@dataclass
class PaperState:
    equity_usd: float
    peak_equity_usd: float
    realized_pnl_usd: float = 0.0
    open_positions: list[Position] = field(default_factory=list)
    recent_trades: list[Trade] = field(default_factory=list)
    daily_pnl_usd: float = 0.0
    daily_anchor_date: str = ""
    manual_ready: list[ManualReady] = field(default_factory=list)
    rejected_signals: list[RejectedSignal] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "equity_usd": self.equity_usd,
            "peak_equity_usd": self.peak_equity_usd,
            "realized_pnl_usd": self.realized_pnl_usd,
            "daily_pnl_usd": self.daily_pnl_usd,
            "daily_anchor_date": self.daily_anchor_date,
            "open_positions": [asdict(p) for p in self.open_positions],
            "recent_trades": [asdict(t) for t in self.recent_trades[-200:]],
            "manual_ready": [asdict(m) for m in self.manual_ready],
            "rejected_signals": [asdict(r) for r in self.rejected_signals],
        }

    @classmethod
    def from_dict(cls, d: dict) -> PaperState:
        # P1 — bilinmeyen alanları süz (forward uyumlu), eksikler default'a düşer
        # (legacy kayıtlar lifecycle/learning alanları olmadan yüklenir).
        return cls(
            equity_usd=float(d.get("equity_usd", 0)),
            peak_equity_usd=float(d.get("peak_equity_usd", 0)),
            realized_pnl_usd=float(d.get("realized_pnl_usd", 0)),
            daily_pnl_usd=float(d.get("daily_pnl_usd", 0)),
            daily_anchor_date=str(d.get("daily_anchor_date", "")),
            open_positions=[
                Position(**_only_known(Position, p))
                for p in d.get("open_positions", [])
                if isinstance(p, dict)
            ],
            recent_trades=[
                Trade(**_only_known(Trade, t))
                for t in d.get("recent_trades", [])
                if isinstance(t, dict)
            ],
            manual_ready=[
                ManualReady(**_only_known(ManualReady, m))
                for m in d.get("manual_ready", [])
                if isinstance(m, dict)
            ],
            rejected_signals=[
                RejectedSignal(**_only_known(RejectedSignal, r))
                for r in d.get("rejected_signals", [])
                if isinstance(r, dict)
            ],
        )


def _initial_state() -> PaperState:
    th = load_thresholds()["paper_trading"]
    equity = float(th["initial_equity_usd"])
    return PaperState(equity_usd=equity, peak_equity_usd=equity)


def _write_atomic(path: Path, payload: dict) -> None:
    """Atomik yazım: temp dosya + os.replace (yarım dosya asla görünmez)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _backup_corrupt(path: Path) -> str | None:
    """Bozuk state'i kenara al (üzerine yazma) → sonraki save temiz yazar."""
    try:
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        bak = path.with_name(f"{path.stem}.corrupt-{ts}.json")
        os.replace(path, bak)
        return str(bak)
    except OSError:
        return None


def load() -> PaperState:
    with _LOCK:
        if not STATE_PATH.exists():
            state = _initial_state()
            _write_atomic(STATE_PATH, state.to_dict())
            return state
        try:
            raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            return PaperState.from_dict(raw)
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
            # P1 — corrupt state: yedekle + temiz default yaz (crash YOK).
            bak = _backup_corrupt(STATE_PATH)
            state = _initial_state()
            try:
                _write_atomic(STATE_PATH, state.to_dict())
            except OSError:
                pass
            audit.record(
                "STATE_REPAIRED",
                reason=f"corrupt_paper_state:{type(exc).__name__}",
                backup=bak,
            )
            return state


def save(state: PaperState) -> None:
    with _LOCK:
        _write_atomic(STATE_PATH, state.to_dict())


def utc_iso() -> str:
    return datetime.now(UTC).isoformat()
