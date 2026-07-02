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

F3-3 (2026-07-02) — flag `MISTAKE_MEMORY_V2` (env, default KAPALI = bayt-aynı):
denetim bulgusu 1.4/4.4 — exact-match + 200'lük volatile pencere yüzünden hafıza
fiilen ölüydü (fingerprint kardinalitesi yüksek, aynı 8-parçalı imza 3 kez
neredeyse hiç birikmiyor). AÇIKKEN üç düzeltme:
1. Kaynak: recent_trades yerine outcomes_from_state (decision_log kalıcı kaynağı
   dahil — trainer'la aynı desen).
2. Hiyerarşik fallback: exact imza yetersizse önce L1 (symbol|tf|rejim|yön),
   sonra L2 (symbol|yön) kovasına bakılır (`~L1|`/`~L2|` sentetik kayıtları —
   gerçek fingerprint'le çakışamaz).
3. Wilson güven sınırı: AVOID ancak üst sınır < eşik (gerçekten kötü olduğundan
   eminsek), BOOST ancak alt sınır > eşik. 1W/2L gibi az-veri imzalar artık
   AVOID yerine WARNING alır (aceleci blok yok). Streak kuralı aynen kalır.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Literal

from packages.learning import fingerprint as fp_mod
from packages.learning import outcomes as outcomes_mod
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


_V2_OFF = {"0", "false", "no", "off", ""}


def _v2_enabled() -> bool:
    return os.environ.get("MISTAKE_MEMORY_V2", "0").strip().lower() not in _V2_OFF


def _pnl(t) -> float:
    """Trade (`pnl_usd`) ve CanonicalOutcome (`pnl`) için ortak PnL erişimi."""
    v = getattr(t, "pnl_usd", None)
    return float(v if v is not None else getattr(t, "pnl", 0.0))


def wilson_bounds(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Win-rate için %95 Wilson güven aralığı (alt, üst). n=0 → (0, 1)."""
    if n <= 0:
        return 0.0, 1.0
    phat = wins / n
    denom = 1.0 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    margin = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def _l1_key(fingerprint: str | None) -> str | None:
    """L1 kovası: symbol|timeframe|rejim|yön (skor/confluence/modül düşer)."""
    p = fp_mod.parse(fingerprint)
    if not p["symbol"] or not p["direction"]:
        return None
    return "|".join(["~L1", p["symbol"], p["timeframe"] or "-",
                     p["regime"] or "-", p["direction"]])


def _l2_key(fingerprint: str | None) -> str | None:
    """L2 kovası: symbol|yön (en kaba anlamlı seviye)."""
    p = fp_mod.parse(fingerprint)
    if not p["symbol"] or not p["direction"]:
        return None
    return "|".join(["~L2", p["symbol"], p["direction"]])


def _aggregate_by(trades, key_fn) -> list[Mistake]:
    by_key: dict[str, list] = {}
    for t in trades:
        if not getattr(t, "data_verified", False):
            continue
        if not t.fingerprint:
            continue
        key = key_fn(t.fingerprint)
        if not key:
            continue
        by_key.setdefault(key, []).append(t)
    out: list[Mistake] = []
    for key, items in by_key.items():
        items_sorted = sorted(items, key=lambda x: x.closed_at or "")
        wins = sum(1 for t in items_sorted if _pnl(t) > 0)
        # F1-2 — başabaş (pnl==0, örn. time-stop BE çıkışı) kayıp DEĞİLDİR:
        # eskiden loss sayılıp win_rate'i suni düşürüyor, AVOID'u yanlış
        # tetikleyebiliyordu. losses yalnız pnl<0; win_rate paydası kararlı
        # trade'ler (wins+losses). Streak de yalnız gerçek kayıpları sayar —
        # BE araya girerse seriyi keser (kayıp serisi değildir).
        losses = sum(1 for t in items_sorted if _pnl(t) < 0)
        decided = wins + losses
        streak = 0
        for t in reversed(items_sorted):
            if _pnl(t) < 0:
                streak += 1
            else:
                break
        out.append(
            Mistake(
                fingerprint=key,
                trades=len(items_sorted),
                wins=wins,
                losses=losses,
                win_rate=round(wins / decided, 3) if decided else 0.0,
                total_pnl=round(sum(_pnl(t) for t in items_sorted), 2),
                last_seen_at=items_sorted[-1].closed_at if items_sorted else None,
                streak_losses=streak,
            )
        )
    return out


def _aggregate(trades) -> list[Mistake]:
    return _aggregate_by(trades, lambda f: f)


def summary() -> list[Mistake]:
    s = paper_state.load()
    if not _v2_enabled():
        return _aggregate(s.recent_trades)
    # F3-3 — kalıcı kaynak (decision_log + recent_trades) + hiyerarşik kovalar.
    records = outcomes_mod.outcomes_from_state(s)
    out = _aggregate(records)
    out.extend(_aggregate_by(records, _l1_key))
    out.extend(_aggregate_by(records, _l2_key))
    return out


def _verdict_for(rec: Mistake | None, fp: str, *, use_wilson: bool = False) -> MistakeVerdict:
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
    # F3-3 — Wilson modu: AVOID/BOOST nokta tahminiyle değil güven sınırıyla.
    # AVOID ancak ÜST sınır eşiğin altındaysa (gerçekten kötü olduğundan
    # eminiz); BOOST ancak ALT sınır eşiğin üstündeyse. Az veri → karar yok.
    lo, hi = wilson_bounds(rec.wins, decided) if use_wilson else (rec.win_rate, rec.win_rate)
    if hi < AVOID_WIN_RATE:
        return MistakeVerdict(
            action="AVOID",
            reason=(
                f"düşük win_rate {rec.win_rate} (wilson üst {hi:.2f})"
                if use_wilson else f"düşük win_rate {rec.win_rate}"
            ),
            size_factor=SIZE_FACTOR_AVOID,
            evidence=[
                f"trades={rec.trades}",
                f"total_pnl={rec.total_pnl}",
            ],
            fingerprint=fp,
            record=rec,
        )
    if lo > BOOST_WIN_RATE:
        return MistakeVerdict(
            action="BOOST",
            reason=(
                f"yüksek win_rate {rec.win_rate} (wilson alt {lo:.2f})"
                if use_wilson else f"yüksek win_rate {rec.win_rate}"
            ),
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
    if not _v2_enabled():
        return _verdict_for(rec, fingerprint)
    # F3-3 — hiyerarşik fallback: exact imza yetersizse L1 → L2 kovası.
    level = "exact"
    decided = (rec.wins + rec.losses) if rec else 0
    if decided < MIN_TRADES:
        for lvl, key_fn in (("L1", _l1_key), ("L2", _l2_key)):
            key = key_fn(fingerprint)
            cand = next((m for m in mems if m.fingerprint == key), None) if key else None
            if cand is not None and (cand.wins + cand.losses) >= MIN_TRADES:
                rec, level = cand, lvl
                break
    verdict = _verdict_for(rec, fingerprint, use_wilson=True)
    if level != "exact":
        verdict.reason = f"[{level}] {verdict.reason}"
        verdict.evidence.append(f"fallback_level={level}")
        verdict.evidence.append(f"bucket={rec.fingerprint}")
    return verdict


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
