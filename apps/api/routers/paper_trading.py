"""GET /api/v1/paper-trading/state, POST /api/v1/paper-trading/tick"""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter

from packages.data.ingestion.pipeline import DEFAULT_SYMBOLS, get_cached_snapshot
from packages.decision.engine import decide_matrix
from packages.paper import audit as paper_audit
from packages.paper import state as paper_state
from packages.paper.lifecycle import (
    attempt_open,
    flatten_all,
    max_drawdown_pct,
)
from packages.paper.lifecycle import (
    tick as price_tick,
)
from packages.risk import halt as halt_store
from packages.risk.engine import RiskInput

router = APIRouter(tags=["paper-trading"])


def _time_stop_status(p: paper_state.Position, now: datetime) -> tuple[str, int | None]:
    """UX1 — time-stop durumu backend'de; negatif geri sayım ÜRETİLMEZ.

    NONE → time-stop yok; ACTIVE → kalan saniye (>0); EXPIRED → süre geçti,
    kalan 0 (exit pending — fiyatla TIME_STOP_EXIT'te kapanır).
    """
    vu = getattr(p, "valid_until", None)
    if not vu:
        return "NONE", None
    try:
        deadline = datetime.fromisoformat(vu)
    except (ValueError, TypeError):
        return "NONE", None
    remaining = (deadline - now).total_seconds()
    if remaining <= 0:
        return "EXPIRED", 0
    return "ACTIVE", int(remaining)


def _duplicate_warning(ps: paper_state.PaperState) -> list[dict]:
    """P1 — savunmacı duplicate tespiti: aynı (symbol, timeframe) için birden
    fazla açık pozisyon (politika gereği normalde boş). Görünür uyarı için."""
    seen: dict[tuple[str, str], int] = {}
    for p in ps.open_positions:
        seen[(p.symbol, p.timeframe)] = seen.get((p.symbol, p.timeframe), 0) + 1
    return [
        {"symbol": sym, "timeframe": tf, "open_count": n}
        for (sym, tf), n in sorted(seen.items())
        if n > 1
    ]


def _serialize_state(ps: paper_state.PaperState) -> dict:
    now = datetime.now(UTC)
    open_pos = []
    unreal_total = 0.0
    for p in ps.open_positions:
        d = asdict(p)
        d["unrealized_pnl_usd"] = round(p.unrealized_pnl_usd, 2)
        ts_status, ts_remaining = _time_stop_status(p, now)
        d["time_stop_status"] = ts_status
        d["time_stop_seconds_remaining"] = ts_remaining
        unreal_total += d["unrealized_pnl_usd"]
        open_pos.append(d)
    # P1 — yeni girişler kapalı mı: aktif halt (KILL_SWITCH/RISK_REDUCE) varsa
    # yeni pozisyon açılmaz (read-only; risk hesaplamaz, persist halt'i okur).
    new_entries_disabled = bool(halt_store.active_halts())
    return {
        "equity_usd": round(ps.equity_usd, 2),
        "realized_pnl_usd": round(ps.realized_pnl_usd, 2),
        "unrealized_pnl_usd": round(unreal_total, 2),
        "max_drawdown_pct": max_drawdown_pct(ps),
        "sharpe_30d": 0.0,
        "open_positions": open_pos,
        "recent_trades": [asdict(t) for t in ps.recent_trades[-25:]],
        # P1 — additive lifecycle/audit yüzeyi (frontend hesap yapmaz).
        "new_entries_disabled": new_entries_disabled,
        "duplicate_warning": _duplicate_warning(ps),
        "audit_summary": paper_audit.summary(),
        "recent_audit_events": paper_audit.read_recent(20),
    }


@router.get("/paper-trading/state")
def get_paper_state() -> dict:
    return _serialize_state(paper_state.load())


@router.post("/paper-trading/tick")
def post_paper_tick() -> dict:
    ps = paper_state.load()
    snap = get_cached_snapshot()
    # None fiyatlar lifecycle'a aktarılmaz; mock fiyat dağıtılmaz.
    prices = {q.symbol: q.price for q in snap.prices if q.price is not None}
    verified_flags = {q.symbol: q.verified for q in snap.prices}

    # Önce mevcut pozisyonları fiyatla güncelle (SL/TP)
    closed = price_tick(ps, prices)

    risk_in = RiskInput(
        dqs_score=snap.quality.score,
        equity_usd=ps.equity_usd,
        peak_equity_usd=ps.peak_equity_usd,
        daily_pnl_usd=ps.daily_pnl_usd,
        open_position_count=len(ps.open_positions),
    )

    # G5 — breach varsa halt'i persist et; KILL_SWITCH seviyesinde halt
    # aktifse mevcut pozisyonları düzleştir (KILL_SWITCH_EXIT). Sadece risk
    # azaltıcı; yeni açılışlar zaten risk engine'deki halt ile bloklanır.
    actions: list[dict] = []
    halts = halt_store.sync(risk_in)
    if any(h.level == "KILL_SWITCH" for h in halts):
        for cls in flatten_all(ps, prices):
            closed.append(cls)
        risk_in = RiskInput(
            dqs_score=snap.quality.score,
            equity_usd=ps.equity_usd,
            peak_equity_usd=ps.peak_equity_usd,
            daily_pnl_usd=ps.daily_pnl_usd,
            open_position_count=len(ps.open_positions),
        )

    # T2 — (symbol, timeframe) karar uzayı. 1w decide_matrix içinde zaten
    # paper_execution=false ile hold'a düşer; fingerprint TF segmenti taşır.
    _regime, _risk, decisions = decide_matrix(
        DEFAULT_SYMBOLS[:4], snap, risk_in, open_positions=ps.open_positions
    )

    for cls in closed:
        actions.append(
            {
                "symbol": cls.symbol,
                "action": "close",
                "reason": cls.close_reason,
                "timeframe": cls.timeframe,
            }
        )

    for d in decisions:
        entry = {"symbol": d.symbol, "timeframe": d.timeframe}
        if d.action == "blocked":
            actions.append({**entry, "action": "blocked", "reason": d.reason})
            continue
        if d.action == "hold":
            actions.append({**entry, "action": "hold", "reason": d.reason})
            continue
        # P1 — açılış tek yoldan (attempt_open): duplicate/scale-in politikası +
        # fiyat denetimi + audit burada. Yanıt etiketleri korunur.
        side = "long" if d.action == "open_long" else "short"
        pos, decision = attempt_open(
            ps,
            symbol=d.symbol,
            side=side,
            entry_price=prices.get(d.symbol),
            size_multiplier=d.size_multiplier,
            timeframe=d.timeframe,
            open_reason=d.reason,
            snapshot_id=snap.snapshot_id,
            fingerprint=d.fingerprint,
            data_verified=verified_flags.get(d.symbol, False),
            predicted_confidence=d.confidence,
            raw_confidence=d.raw_confidence,
            confidence_source=d.confidence_source,
        )
        if pos is not None:
            actions.append({**entry, "action": "open", "reason": d.reason})
        elif decision["reason"] == "no_price":
            actions.append({**entry, "action": "blocked", "reason": "fiyat yok"})
        elif decision.get("duplicate"):
            actions.append({**entry, "action": "hold", "reason": "zaten açık (aynı TF)"})
        else:
            actions.append({**entry, "action": "blocked", "reason": decision["reason"]})

    paper_state.save(ps)

    return {
        "tick_at": datetime.now(UTC).isoformat(),
        "signals_processed": len(decisions),
        "actions": actions,
    }


# Test/dev: pozisyonları sıfırla
@router.post("/paper-trading/reset")
def reset() -> dict:
    ps = paper_state._initial_state()
    # SL/TP olmadan sadece son trade ve pozisyonları temizle, equity sıfırlama:
    # gerçek "reset" davranışı için _initial_state yeterli
    paper_state.save(ps)
    paper_audit.record("STATE_REPAIRED", reason="manual_reset")
    return _serialize_state(ps)
