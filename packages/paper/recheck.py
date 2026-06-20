"""Position re-check — açık paper pozisyonlarını mevcut karar matrisine göre
yeniden değerlendir (read-only öneri; otomatik kapatmaz).

Tick'in yan ürünü olarak çalışır: `decide_matrix` zaten her (symbol, timeframe)
için bir TradeDecision üretiyor; recheck her pozisyon için bu kararı bulup
"hâlâ geçerli mi?" sorusuna verdict döner.

Verdict skalası:
  OK              → fresh karar pozisyon yönüyle hizalı (open_long ↔ long, vb.)
  WATCH           → fresh karar hold (yön nötr; pozisyon zararsız taşınır)
  REDUCE          → fresh karar blocked (RiskGate sıkıştı; çıkış sonrası tekrar
                    açılamaz — boyutu düşürme önerisi)
  EXIT_RECOMMEND  → fresh karar TERS yön (long pozisyon ↔ open_short, vb.)

Bu modül karar VERMEZ; sadece sinyal verir. Çıkış yine `manual_close` veya
SL/TP üzerinden olur. PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from packages.decision.engine import TradeDecision
from packages.paper.state import Position

Verdict = str  # OK | WATCH | REDUCE | EXIT_RECOMMEND


@dataclass
class PositionRecheck:
    position_id: str
    symbol: str
    timeframe: str
    side: str                     # long | short
    verdict: Verdict
    reason: str
    fresh_action: str | None      # open_long | open_short | hold | blocked | None
    fresh_direction: str | None   # long | short | neutral | None
    fresh_confidence: float | None
    pnl_pct: float
    checked_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _decision_key(d: TradeDecision) -> tuple[str, str]:
    # TradeDecision'da timeframe ayrı alan değil; decide_matrix'te decision'ın
    # taşıdığı meta üzerinden buluruz. Fallback: fingerprint son segmenti.
    tf = getattr(d, "timeframe", None) or ""
    if not tf and d.fingerprint:
        # fingerprint format: "sym|tf|..."; defansif parse
        parts = d.fingerprint.split("|")
        if len(parts) >= 2:
            tf = parts[1]
    return (d.symbol, tf)


def _pnl_pct(pos: Position) -> float:
    if not pos.entry_price or pos.entry_price <= 0 or not pos.current_price:
        return 0.0
    raw = (pos.current_price - pos.entry_price) / pos.entry_price * 100.0
    return round(raw if pos.side == "long" else -raw, 2)


def _verdict_for(pos: Position, decision: TradeDecision | None) -> tuple[Verdict, str]:
    if decision is None:
        return "OK", "fresh_signal_missing"

    action = decision.action
    if action == "blocked":
        # RiskGate / KILL_SWITCH / korelasyon — yeni giriş kapanmış. Çıkış sonrası
        # tekrar girilemeyeceği için boyut azaltma önerisi.
        return "REDUCE", decision.reason or "risk_gate_blocked"

    if action == "hold":
        return "WATCH", decision.reason or "hold"

    desired_side = (
        "long" if action == "open_long"
        else "short" if action == "open_short"
        else None
    )
    if desired_side is None:
        return "OK", "no_actionable_signal"
    if desired_side != pos.side:
        return "EXIT_RECOMMEND", f"signal_flipped_to_{desired_side}"
    return "OK", "still_aligned"


def compute_rechecks(
    positions: list[Position],
    decisions: list[TradeDecision],
) -> list[PositionRecheck]:
    """Read-only: her açık pozisyon için fresh karara karşı recheck verdict üret.

    Eşleştirme: (symbol, timeframe). TradeDecision'da timeframe yoksa fingerprint
    parse'ı fallback olarak kullanılır. Eşleşme yoksa verdict OK / fresh_signal_missing.
    """
    by_key: dict[tuple[str, str], TradeDecision] = {}
    for d in decisions:
        by_key[_decision_key(d)] = d

    now = datetime.now(UTC).isoformat()
    out: list[PositionRecheck] = []
    for pos in positions:
        d = by_key.get((pos.symbol, pos.timeframe))
        verdict, reason = _verdict_for(pos, d)
        out.append(
            PositionRecheck(
                position_id=pos.id,
                symbol=pos.symbol,
                timeframe=pos.timeframe,
                side=pos.side,
                verdict=verdict,
                reason=reason,
                fresh_action=d.action if d else None,
                fresh_direction=(
                    d.consensus.direction if d and getattr(d, "consensus", None) else None
                ),
                fresh_confidence=round(d.confidence, 3) if d else None,
                pnl_pct=_pnl_pct(pos),
                checked_at=now,
            )
        )
    return out
