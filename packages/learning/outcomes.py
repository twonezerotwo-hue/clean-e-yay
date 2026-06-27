"""L1 — canonical paper-trade outcome record + timeframe-aware aggregation.

Kapalı paper trade'lerden tek **canonical outcome record** türetir. Yeni veri
kaynağı YOK — yalnızca mevcut `Trade` + fingerprint'ten türetir. Legacy kayıtlar
eksik alanlarla gelir → güvenli default (crash yok). Tüm outcome'lar `paper_only`.

PAPER_SAFE / NO_EXECUTION: yalnızca okuma + türetme; emir/karar üretmez.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from packages.learning import decision_log
from packages.learning import fingerprint as fp
from packages.paper import state as paper_state
from packages.paper.state import Trade


@dataclass
class CanonicalOutcome:
    trade_id: str
    symbol: str
    timeframe: str
    opened_at: str | None
    closed_at: str | None
    duration_seconds: float | None
    direction: str
    open_price: float | None
    close_price: float | None
    pnl: float
    pnl_pct: float | None
    open_reason: str | None
    close_reason: str | None
    fingerprint: str | None
    regime: str
    dominant_module: str
    candidate_action: str | None
    final_action: str | None
    blocked_by: list[str] = field(default_factory=list)
    gates_applied: list[str] = field(default_factory=list)
    snapshot_id: str | None = None
    decision_id: str | None = None
    data_verified: bool = False
    source_quality: str = "unknown"
    paper_only: bool = True


def _duration_seconds(opened_at: str | None, closed_at: str | None) -> float | None:
    if not opened_at or not closed_at:
        return None
    try:
        delta = datetime.fromisoformat(closed_at) - datetime.fromisoformat(opened_at)
        return round(delta.total_seconds(), 1)
    except (ValueError, TypeError):
        return None


def _pnl_pct(entry: float | None, exit_: float | None, side: str) -> float | None:
    try:
        if not entry or exit_ is None:
            return None
        raw = (exit_ - entry) / entry * 100.0
        return round(raw if side == "long" else -raw, 4)
    except (TypeError, ZeroDivisionError):
        return None


def _final_action(side: str) -> str | None:
    if side == "long":
        return "open_long"
    if side == "short":
        return "open_short"
    return None


def build_outcome(t: Trade) -> CanonicalOutcome:
    """Tek Trade → CanonicalOutcome (legacy default'larla; asla patlamaz)."""
    parsed = fp.parse(getattr(t, "fingerprint", None))
    side = getattr(t, "side", None) or "?"
    timeframe = getattr(t, "timeframe", None) or parsed["timeframe"] or "1d"
    verified = bool(getattr(t, "data_verified", False))
    final = _final_action(side)
    entry = getattr(t, "entry_price", None)
    exit_ = getattr(t, "exit_price", None)
    return CanonicalOutcome(
        trade_id=str(getattr(t, "id", "") or ""),
        symbol=str(getattr(t, "symbol", "") or ""),
        timeframe=timeframe,
        opened_at=getattr(t, "opened_at", None),
        closed_at=getattr(t, "closed_at", None),
        duration_seconds=_duration_seconds(
            getattr(t, "opened_at", None), getattr(t, "closed_at", None)
        ),
        direction=side,
        open_price=entry,
        close_price=exit_,
        pnl=float(getattr(t, "pnl_usd", 0.0) or 0.0),
        pnl_pct=_pnl_pct(entry, exit_, side),
        open_reason=getattr(t, "open_reason", None),
        close_reason=getattr(t, "close_reason", None),
        fingerprint=getattr(t, "fingerprint", None),
        regime=parsed["regime"] or "UNKNOWN",
        dominant_module=parsed["dominant_module"] or "unknown",
        # P1 Trade candidate/final/gate attribution taşımıyor → açılmış trade
        # için final == candidate (open_*), bloklanmamış (blocked_by boş).
        candidate_action=final,
        final_action=final,
        blocked_by=[],
        gates_applied=[],
        snapshot_id=getattr(t, "snapshot_id", None),
        decision_id=None,
        data_verified=verified,
        source_quality="verified" if verified else "unverified",
        paper_only=True,
    )


def build_outcome_from_log_entry(entry: dict) -> CanonicalOutcome:
    """Tek decision_log kaydı → CanonicalOutcome (build_outcome'un dict ikizi).

    decision_log.jsonl, paper_state.recent_trades'in kalıcı (append-only) eşidir
    — recent_trades sadece son 200'lük bir penceredir ve state dosyası bozulup
    sıfırlanırsa (bkz. paper_state.corrupt-*.json yedekleri) bu pencere kaybolur.
    decision_log hiçbir zaman sıfırlanmaz, bu yüzden öğrenme verisinin asıl
    kaynağı budur; recent_trades sadece yazma hatası durumunda yedektir.
    """
    opening = entry.get("opening_signal") or {}
    exit_ = entry.get("exit") or {}
    outcome = entry.get("outcome") or {}
    fingerprint = opening.get("fingerprint")
    parsed = fp.parse(fingerprint)
    side = entry.get("side") or "?"
    timeframe = entry.get("timeframe") or parsed["timeframe"] or "1d"
    verified = bool(opening.get("data_verified", False))
    final = _final_action(side)
    entry_price = outcome.get("entry_price")
    exit_price = outcome.get("exit_price")
    return CanonicalOutcome(
        trade_id=str(entry.get("trade_id") or ""),
        symbol=str(entry.get("symbol") or ""),
        timeframe=timeframe,
        opened_at=entry.get("opened_at"),
        closed_at=entry.get("closed_at"),
        duration_seconds=_duration_seconds(entry.get("opened_at"), entry.get("closed_at")),
        direction=side,
        open_price=entry_price,
        close_price=exit_price,
        pnl=float(outcome.get("pnl_usd") or 0.0),
        pnl_pct=_pnl_pct(entry_price, exit_price, side),
        open_reason=opening.get("reason"),
        close_reason=exit_.get("reason"),
        fingerprint=fingerprint,
        regime=parsed["regime"] or "UNKNOWN",
        dominant_module=parsed["dominant_module"] or "unknown",
        candidate_action=final,
        final_action=final,
        blocked_by=[],
        gates_applied=[],
        snapshot_id=opening.get("snapshot_id"),
        decision_id=None,
        data_verified=verified,
        source_quality="verified" if verified else "unverified",
        paper_only=True,
    )


def outcomes_from_state(
    state: paper_state.PaperState | None = None,
) -> list[CanonicalOutcome]:
    """recent_trades (volatile pencere) + decision_log (kalıcı kayıt) birleşimi.

    recent_trades öncelikli kaynaktır (mevcut davranış birebir korunur — id
    çakışsa bile hepsi sayılır). decision_log her kapanışta recent_trades ile
    birlikte yazılır (bkz. packages/paper/lifecycle.py); recent_trades'te
    OLMAYAN trade_id'leri (örn. paper_state.json bozulup sıfırlandıysa, bkz.
    paper_state.corrupt-*.json yedekleri) decision_log'dan kurtarıp ekliyoruz —
    veri kaybı yok.
    """
    s = state if state is not None else paper_state.load()
    primary = [build_outcome(t) for t in s.recent_trades]
    known_ids = {o.trade_id for o in primary if o.trade_id}
    recovered: list[CanonicalOutcome] = []
    for raw in decision_log.read_recent(limit=decision_log.DEFAULT_MAX_READ):
        try:
            o = build_outcome_from_log_entry(raw)
        except Exception:  # bozuk/eksik kayıt → atla, worker patlamasın
            continue
        if o.trade_id and o.trade_id not in known_ids:
            known_ids.add(o.trade_id)
            recovered.append(o)
    return primary + recovered


def outcome_to_dict(o: CanonicalOutcome) -> dict:
    return asdict(o)


# --------------------------------------------------------------------------
# Timeframe-aware aggregation — 15m outcome'u 1d bucket'ını ETKİLEMEZ.
# --------------------------------------------------------------------------

def _empty_bucket() -> dict:
    return {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "total_pnl": 0.0,
        "avg_pnl": 0.0,
        "verified": 0,
    }


def bucketize(outcomes: list[CanonicalOutcome], key) -> dict[str, dict]:
    """`key(outcome) -> str` ile grupla; bucket başına istatistik üret."""
    acc: dict[str, dict] = {}
    for o in outcomes:
        k = key(o)
        b = acc.setdefault(str(k if k is not None else "unknown"), _empty_bucket())
        b["trades"] += 1
        if o.pnl > 0:
            b["wins"] += 1
        else:
            b["losses"] += 1
        b["total_pnl"] = round(b["total_pnl"] + o.pnl, 2)
        if o.data_verified:
            b["verified"] += 1
    for b in acc.values():
        n = b["trades"]
        b["win_rate"] = round(b["wins"] / n, 3) if n else 0.0
        b["avg_pnl"] = round(b["total_pnl"] / n, 2) if n else 0.0
    return acc


def breakdowns(outcomes: list[CanonicalOutcome]) -> dict[str, dict]:
    return {
        "by_timeframe": bucketize(outcomes, lambda o: o.timeframe),
        "by_symbol": bucketize(outcomes, lambda o: o.symbol),
        "by_regime": bucketize(outcomes, lambda o: o.regime),
        "by_dominant_module": bucketize(outcomes, lambda o: o.dominant_module),
        "by_close_reason": bucketize(outcomes, lambda o: o.close_reason or "unknown"),
    }


def distribution(outcomes: list[CanonicalOutcome], key) -> dict[str, int]:
    """Sadece sayım (trainer evidence'ı için kompakt dağılım)."""
    out: dict[str, int] = {}
    for o in outcomes:
        k = str(key(o) if key(o) is not None else "unknown")
        out[k] = out.get(k, 0) + 1
    return out
