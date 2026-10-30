"""Tick'in karar matrisi — API, brifing ve YZ bağlamı için tek kaynak.

Supervisor'da tick ve API aynı süreçtedir. Tick ``decide_matrix``'i bir kez
koşar ve sonucunu buraya yayımlar; okuma yüzeyleri aynı snapshot için kararı
yeniden hesaplamaz, böylece ekran tick'in karar verdiği anı anlatır. Snapshot,
sembol seti ya da keşif bayrağı uymazsa (ayrı API süreci, test, bayat tick)
eski yol koşar: ``decide_matrix`` aynı girdilerle yeniden hesaplanır.

Salt okuma yüzeyi: karar yetkisi eklemez, RiskGate'i atlamaz, kararı değiştirmez.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TickMatrix:
    snapshot_id: str
    symbols: tuple[str, ...]
    paper_exploration: bool
    regime: Any
    risk: Any
    decisions: tuple[Any, ...]


_LOCK = threading.Lock()
_LATEST: TickMatrix | None = None
# Son kapı sonuçları: (snapshot_id, {(symbol, timeframe): FinalGate}).
_FINAL: tuple[str, dict[tuple[str, str], Any]] | None = None


def publish(
    snap: Any,
    symbols: list[str],
    *,
    paper_exploration: bool,
    regime: Any,
    risk: Any,
    decisions: list[Any],
) -> None:
    """Tick'in bu snapshot için verdiği kararı yayımla (yalnız tick çağırır)."""
    global _LATEST
    snapshot_id = str(getattr(snap, "snapshot_id", "") or "")
    if not snapshot_id:
        return
    with _LOCK:
        _LATEST = TickMatrix(
            snapshot_id=snapshot_id,
            symbols=tuple(symbols),
            paper_exploration=bool(paper_exploration),
            regime=regime,
            risk=risk,
            decisions=tuple(decisions),
        )


def latest() -> TickMatrix | None:
    return _LATEST


def publish_final(snap: Any, results: dict[tuple[str, str], Any]) -> None:
    """Tick'in bu snapshot için son kapı sonuçlarını yayımla (yalnız tick çağırır)."""
    global _FINAL
    snapshot_id = str(getattr(snap, "snapshot_id", "") or "")
    if not snapshot_id:
        return
    with _LOCK:
        _FINAL = (snapshot_id, dict(results))


def final_for(snap: Any) -> dict[tuple[str, str], Any] | None:
    """Aynı snapshot için tick'in son kapı sonuçları; yoksa None."""
    item = _FINAL
    snapshot_id = str(getattr(snap, "snapshot_id", "") or "")
    if item is None or not snapshot_id or item[0] != snapshot_id:
        return None
    return item[1]


def reset() -> None:
    """Testler arası sızıntıyı önlemek için (conftest)."""
    global _LATEST, _FINAL
    with _LOCK:
        _LATEST = None
        _FINAL = None


def decide_matrix_for(
    symbols: list[str],
    snap: Any,
    risk_in: Any,
    *,
    open_positions: list | None = None,
    paper_exploration: bool = False,
) -> tuple[Any, Any, list[Any]]:
    """Tick aynı snapshot için karar verdiyse onu döner; yoksa yeniden hesaplar."""
    art = _LATEST
    snapshot_id = str(getattr(snap, "snapshot_id", "") or "")
    if (
        art is not None
        and snapshot_id
        and art.snapshot_id == snapshot_id
        and art.symbols == tuple(symbols)
        and art.paper_exploration == bool(paper_exploration)
    ):
        return art.regime, art.risk, list(art.decisions)
    from packages.decision.engine import decide_matrix

    return decide_matrix(
        symbols,
        snap,
        risk_in,
        open_positions=open_positions,
        paper_exploration=paper_exploration,
    )


__all__ = ["TickMatrix", "decide_matrix_for", "final_for", "latest", "publish", "publish_final", "reset"]
