"""G5 — Daily-loss / Max-DD halt store (file-backed).

Politika:
- Halt **sadece risk azaltıcıdır**: aktifken risk engine'e ek candidate
  ekler (DAILY_LOSS → KILL_SWITCH, MAX_DRAWDOWN → RISK_REDUCE; her ikisi de
  en az NO_POSITION_INCREASE'in üstünde). RiskGate'in mevcut hard
  gate'lerini **bypass etmez**, gevşetmez.
- Breach tespiti tick yollarında `sync(risk_input)` ile yapılır ve diske
  yazılır; `active_halts()` salt okur.
- **Otomatik reset yok** — aktif halt yalnızca owner reset
  (`POST /api/v1/risk/halts/reset`) ile kalkar. Gün dönümünde daily_pnl
  sıfırlansa bile halt sürer.
- PAPER_SAFE / NO_EXECUTION: broker yok; halt yalnızca paper karar
  akışını kısıtlar.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import load_thresholds

_LOCK = threading.Lock()

HALT_LEVELS = {
    "DAILY_LOSS": "KILL_SWITCH",
    "MAX_DRAWDOWN": "RISK_REDUCE",
}
MAX_HISTORY = 100


@dataclass
class HaltEvent:
    id: str
    type: str               # DAILY_LOSS | MAX_DRAWDOWN
    level: str              # KILL_SWITCH | RISK_REDUCE
    started_at: str
    reason: str
    evidence: list[str] = field(default_factory=list)
    active: bool = True
    cleared_at: str | None = None
    cleared_by: str | None = None   # owner_reset


@dataclass
class HaltState:
    events: list[HaltEvent] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"events": [asdict(e) for e in self.events[-MAX_HISTORY:]]}

    @classmethod
    def from_dict(cls, d: dict) -> HaltState:
        return cls(events=[HaltEvent(**e) for e in d.get("events", [])])


def _path() -> Path:
    # Env her çağrıda okunur (testler module reload gerektirmesin).
    return Path(os.environ.get("RISK_HALT_PATH", "data/runtime/risk_halts.json"))


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def load() -> HaltState:
    with _LOCK:
        p = _path()
        if not p.exists():
            return HaltState()
        try:
            return HaltState.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError):
            return HaltState()


def save(state: HaltState) -> None:
    with _LOCK:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")


def active_halts(state: HaltState | None = None) -> list[HaltEvent]:
    state = state if state is not None else load()
    return [e for e in state.events if e.active]


def metrics(inp) -> dict:
    """Gauge metrikleri — frontend hesap yapmaz, oranlar burada üretilir."""
    th = load_thresholds()["risk_gates"]
    daily_limit_usd = float(th["max_daily_loss_pct"]) * inp.equity_usd
    daily_loss_usd = max(0.0, -inp.daily_pnl_usd)
    dd = 0.0
    if inp.peak_equity_usd > 0:
        dd = max(0.0, (inp.peak_equity_usd - inp.equity_usd) / inp.peak_equity_usd)
    dd_limit = float(th["max_drawdown_pct"])
    return {
        "equity_usd": round(inp.equity_usd, 2),
        "peak_equity_usd": round(inp.peak_equity_usd, 2),
        "daily_pnl_usd": round(inp.daily_pnl_usd, 2),
        "daily_loss_limit_usd": round(daily_limit_usd, 2),
        "daily_loss_ratio": round(daily_loss_usd / daily_limit_usd, 4)
        if daily_limit_usd > 0
        else 0.0,
        "drawdown_pct": round(dd, 4),
        "max_drawdown_pct": dd_limit,
        "drawdown_ratio": round(dd / dd_limit, 4) if dd_limit > 0 else 0.0,
    }


def _breaches(inp) -> list[tuple[str, str, list[str]]]:
    """RiskInput'tan halt breach'leri — risk engine eşikleriyle birebir aynı."""
    th = load_thresholds()["risk_gates"]
    out: list[tuple[str, str, list[str]]] = []
    daily_limit = -float(th["max_daily_loss_pct"]) * inp.equity_usd
    if inp.daily_pnl_usd <= daily_limit:
        out.append(
            (
                "DAILY_LOSS",
                "Günlük zarar limiti aşıldı — halt",
                [f"daily pnl {inp.daily_pnl_usd:.0f} ≤ {daily_limit:.0f}"],
            )
        )
    if inp.peak_equity_usd > 0:
        dd = (inp.peak_equity_usd - inp.equity_usd) / inp.peak_equity_usd
        if dd >= float(th["max_drawdown_pct"]):
            out.append(
                (
                    "MAX_DRAWDOWN",
                    "Maksimum drawdown sınırı aşıldı — halt",
                    [f"DD {dd:.1%} ≥ {float(th['max_drawdown_pct']):.0%}"],
                )
            )
    return out


def sync(inp) -> list[HaltEvent]:
    """Breach varsa halt'i aktive et ve persist et; aktif halt'leri döndür.

    Aynı tipte zaten aktif halt varsa yenisi açılmaz (idempotent).
    Hiçbir halt otomatik kapanmaz — sadece owner reset.
    """
    state = load()
    active_types = {e.type for e in state.events if e.active}
    changed = False
    now = _utc_iso()
    for halt_type, reason, evidence in _breaches(inp):
        if halt_type in active_types:
            continue
        state.events.append(
            HaltEvent(
                id=f"{halt_type.lower()}-{now}",
                type=halt_type,
                level=HALT_LEVELS[halt_type],
                started_at=now,
                reason=reason,
                evidence=evidence,
            )
        )
        active_types.add(halt_type)
        changed = True
    if changed:
        save(state)
    return [e for e in state.events if e.active]


def owner_reset() -> list[HaltEvent]:
    """Owner reset — tüm aktif halt'leri kapatır; geçmiş korunur."""
    state = load()
    now = _utc_iso()
    cleared: list[HaltEvent] = []
    for e in state.events:
        if e.active:
            e.active = False
            e.cleared_at = now
            e.cleared_by = "owner_reset"
            cleared.append(e)
    if cleared:
        save(state)
    return cleared
