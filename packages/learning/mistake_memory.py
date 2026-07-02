"""G3 — Mistake Memory Gate.

Geçmişte aynı fingerprint'te tekrar eden kayıpları hatırla; aday TradeDecision'a
`AVOID / BOOST / WARNING / NEUTRAL` damgası üret.

Politika:
- RiskGate hard gate'leri (KILL_SWITCH/RISK_REDUCE/NO_POSITION_INCREASE) son
  söz sahibi; mistake memory onları **bypass etmez**, sadece consensus eşiği
  aşıldıktan sonra avoid/size_factor uygular.
- Yalnızca `data_verified=True` + fingerprint'i olan kapalı trade'ler dataset'e
  alınır (DATA_POLICY).
- `MIN_TRADES` altında her zaman NEUTRAL fallback (no_adjustment).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from packages.paper import state as paper_state

MIN_TRADES = 3
AVOID_WIN_RATE = 0.35
BOOST_WIN_RATE = 0.65
WARNING_WIN_RATE = 0.50
STREAK_AVOID = 3

SIZE_FACTOR_AVOID = 0.0      # AVOID → trade yok (hold)
SIZE_FACTOR_WARNING = 0.7
SIZE_FACTOR_NEUTRAL = 1.0
# No-AI-boost policy: learning may only REDUCE size. A strong fingerprint is still
# flagged BOOST (a positive signal for narrative/audit), but it is size-neutral —
# it never increases the deterministic base. (Was 1.2; clamped to 1.0.)
SIZE_FACTOR_BOOST = 1.0

MistakeAction = Literal["NEUTRAL", "AVOID", "BOOST", "WARNING"]


@dataclass
class Mistake:
    fingerprint: str
    trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    last_seen_at: str | None
    streak_losses: int


@dataclass
class MistakeVerdict:
    action: MistakeAction
    reason: str
    size_factor: float
    evidence: list[str] = field(default_factory=list)
    fingerprint: str | None = None
    record: Mistake | None = None


def _aggregate(trades) -> list[Mistake]:
    by_fp: dict[str, list] = {}
    for t in trades:
        if not getattr(t, "data_verified", False):
            continue
        if not t.fingerprint:
            continue
        by_fp.setdefault(t.fingerprint, []).append(t)
    out: list[Mistake] = []
    for fp, items in by_fp.items():
        items_sorted = sorted(items, key=lambda x: x.closed_at or "")
        wins = sum(1 for t in items_sorted if t.pnl_usd > 0)
        # F1-2 — başabaş (pnl==0, örn. time-stop BE çıkışı) kayıp DEĞİLDİR:
        # eskiden loss sayılıp win_rate'i suni düşürüyor, AVOID'u yanlış
        # tetikleyebiliyordu. losses yalnız pnl<0; win_rate paydası kararlı
        # trade'ler (wins+losses). Streak de yalnız gerçek kayıpları sayar —
        # BE araya girerse seriyi keser (kayıp serisi değildir).
        losses = sum(1 for t in items_sorted if t.pnl_usd < 0)
        decided = wins + losses
        streak = 0
        for t in reversed(items_sorted):
            if t.pnl_usd < 0:
                streak += 1
            else:
                break
        out.append(
            Mistake(
                fingerprint=fp,
                trades=len(items_sorted),
                wins=wins,
                losses=losses,
                win_rate=round(wins / decided, 3) if decided else 0.0,
                total_pnl=round(sum(t.pnl_usd for t in items_sorted), 2),
                last_seen_at=items_sorted[-1].closed_at if items_sorted else None,
                streak_losses=streak,
            )
        )
    return out


def summary() -> list[Mistake]:
    s = paper_state.load()
    return _aggregate(s.recent_trades)


def _verdict_for(rec: Mistake | None, fp: str) -> MistakeVerdict:
    # F1-2 — eşik KARARLI trade sayısına (wins+losses) bakar: 3 başabaş trade'lik
    # bir fingerprint win_rate=0 ile AVOID tetikleyemez (BE kayıp değildir).
    decided = (rec.wins + rec.losses) if rec else 0
    if rec is None or decided < MIN_TRADES:
        return MistakeVerdict(
            action="NEUTRAL",
            reason="yetersiz veri",
            size_factor=SIZE_FACTOR_NEUTRAL,
            evidence=[f"decided={decided} < {MIN_TRADES}"],
            fingerprint=fp,
            record=rec,
        )
    if rec.streak_losses >= STREAK_AVOID:
        return MistakeVerdict(
            action="AVOID",
            reason=f"art arda {rec.streak_losses} kayıp",
            size_factor=SIZE_FACTOR_AVOID,
            evidence=[
                f"win_rate={rec.win_rate}",
                f"streak_losses={rec.streak_losses}",
            ],
            fingerprint=fp,
            record=rec,
        )
    if rec.win_rate < AVOID_WIN_RATE:
        return MistakeVerdict(
            action="AVOID",
            reason=f"düşük win_rate {rec.win_rate}",
            size_factor=SIZE_FACTOR_AVOID,
            evidence=[
                f"trades={rec.trades}",
                f"total_pnl={rec.total_pnl}",
            ],
            fingerprint=fp,
            record=rec,
        )
    if rec.win_rate > BOOST_WIN_RATE:
        return MistakeVerdict(
            action="BOOST",
            reason=f"yüksek win_rate {rec.win_rate}",
            size_factor=SIZE_FACTOR_BOOST,
            evidence=[f"trades={rec.trades}", f"total_pnl={rec.total_pnl}"],
            fingerprint=fp,
            record=rec,
        )
    if rec.win_rate < WARNING_WIN_RATE:
        return MistakeVerdict(
            action="WARNING",
            reason=f"marjinal win_rate {rec.win_rate}",
            size_factor=SIZE_FACTOR_WARNING,
            evidence=[f"trades={rec.trades}"],
            fingerprint=fp,
            record=rec,
        )
    return MistakeVerdict(
        action="NEUTRAL",
        reason="kabul edilebilir win_rate",
        size_factor=SIZE_FACTOR_NEUTRAL,
        evidence=[f"trades={rec.trades}", f"win_rate={rec.win_rate}"],
        fingerprint=fp,
        record=rec,
    )


def evaluate(fingerprint: str, mems: list[Mistake] | None = None) -> MistakeVerdict:
    mems = mems if mems is not None else summary()
    rec = next((m for m in mems if m.fingerprint == fingerprint), None)
    return _verdict_for(rec, fingerprint)


def thresholds() -> dict:
    return {
        "min_trades": MIN_TRADES,
        "avoid_win_rate": AVOID_WIN_RATE,
        "boost_win_rate": BOOST_WIN_RATE,
        "warning_win_rate": WARNING_WIN_RATE,
        "streak_avoid": STREAK_AVOID,
        "size_factor_avoid": SIZE_FACTOR_AVOID,
        "size_factor_warning": SIZE_FACTOR_WARNING,
        "size_factor_neutral": SIZE_FACTOR_NEUTRAL,
        "size_factor_boost": SIZE_FACTOR_BOOST,
    }
