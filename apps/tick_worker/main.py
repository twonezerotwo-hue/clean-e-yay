"""Tick worker — 30sn döngü.

Çalıştırma:
    python -m apps.tick_worker.main
veya:
    python apps/tick_worker/main.py

API ile aynı state.json dosyasını paylaşır; HTTP'ye ihtiyacı yok.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal

# httpx üzerinden API'yi çağırmak yerine paketleri doğrudan çağırıyoruz —
# böylece worker API'ye bağımlı değil.
from packages.data import snapshot_store
from packages.data.ingestion.pipeline import DEFAULT_SYMBOLS, get_cached_snapshot
from packages.data.provenance import data_provenance
from packages.decision.engine import decide_matrix, matrix_view
from packages.paper import state as paper_state
from packages.paper.lifecycle import attempt_open, flatten_all
from packages.paper.lifecycle import tick as price_tick
from packages.risk import halt as halt_store
from packages.risk.engine import RiskInput

MATRIX_SYMBOLS = DEFAULT_SYMBOLS[:4]


def _snapshot_record(snap, view: dict, risk, ps) -> dict:
    """R1 — disk snapshot store payload'u (gerçek state; sahte backtest yok)."""
    return {
        "schema_version": snapshot_store.SCHEMA_VERSION,
        "snapshot_id": snap.snapshot_id,
        "generated_at": snap.generated_at.isoformat(),
        "mode": data_provenance(snap),
        "dqs": {"score": snap.quality.score, "status": snap.quality.status},
        "provider_status": snap.provider_status or {},
        "data_snapshot": {
            "prices": [
                {
                    "symbol": q.symbol,
                    "price": q.price,
                    "verified": q.verified,
                    "status": getattr(q, "status", None),
                }
                for q in snap.prices
            ],
            "warnings": list(snap.warnings)[:8],
        },
        "decision_matrix": view,
        "risk_state": {
            "action": risk.action,
            "reason": risk.reason,
            "evidence": list(risk.evidence),
        },
        "paper_state_summary": {
            "equity_usd": round(ps.equity_usd, 2),
            "peak_equity_usd": round(ps.peak_equity_usd, 2),
            "daily_pnl_usd": round(ps.daily_pnl_usd, 2),
            "realized_pnl_usd": round(ps.realized_pnl_usd, 2),
            "open_position_count": len(ps.open_positions),
            "open_positions": [
                {
                    "symbol": p.symbol,
                    "side": p.side,
                    "timeframe": getattr(p, "timeframe", "1d"),
                    "size_usd": round(p.size_usd, 2),
                }
                for p in ps.open_positions
            ],
        },
    }

log = logging.getLogger("tick_worker")

INTERVAL = int(os.environ.get("TICK_INTERVAL_SEC", "30"))
_STOP = asyncio.Event()


def _install_signals() -> None:
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _STOP.set)
        except NotImplementedError:
            pass


async def run_once() -> None:
    snap = get_cached_snapshot()
    ps = paper_state.load()
    prices = {q.symbol: q.price for q in snap.prices if q.price is not None}
    verified_flags = {q.symbol: q.verified for q in snap.prices}
    closed = price_tick(ps, prices)
    for cls in closed:
        log.info("close: %s %s pnl=%.2f reason=%s", cls.symbol, cls.side, cls.pnl_usd, cls.close_reason)

    risk_in = RiskInput(
        dqs_score=snap.quality.score,
        equity_usd=ps.equity_usd,
        peak_equity_usd=ps.peak_equity_usd,
        daily_pnl_usd=ps.daily_pnl_usd,
        open_position_count=len(ps.open_positions),
    )

    # G5 — halt durumunu oku/persist et; KILL_SWITCH halt → flatten,
    # yeni trade açma (risk engine halt'i KILL_SWITCH/RISK_REDUCE'a çevirir).
    halts = halt_store.sync(risk_in)
    if any(h.level == "KILL_SWITCH" for h in halts):
        for cls in flatten_all(ps, prices):
            log.info(
                "halt flatten: %s %s pnl=%.2f reason=%s",
                cls.symbol, cls.side, cls.pnl_usd, cls.close_reason,
            )
        risk_in = RiskInput(
            dqs_score=snap.quality.score,
            equity_usd=ps.equity_usd,
            peak_equity_usd=ps.peak_equity_usd,
            daily_pnl_usd=ps.daily_pnl_usd,
            open_position_count=len(ps.open_positions),
        )
    if halts:
        log.warning("active halts: %s", [h.type for h in halts])

    # T2 — (symbol, timeframe) karar uzayı; fingerprint TF segmenti taşır,
    # 1w decide_matrix içinde paper_execution=false ile hold'a düşer.
    _regime, _risk, decisions = decide_matrix(
        MATRIX_SYMBOLS, snap, risk_in, open_positions=ps.open_positions
    )
    for d in decisions:
        if d.action in {"blocked", "hold"}:
            continue
        side = "long" if d.action == "open_long" else "short"
        # P1 — açılış tek yoldan (attempt_open): duplicate/scale-in politikası +
        # fiyat denetimi + audit ortak. (symbol, timeframe) duplicate bloklanır.
        pos, _decision = attempt_open(
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
            log.info(
                "open: %s %s %s @ %.4f size=%.0f valid_until=%s",
                pos.symbol, pos.timeframe, pos.side, pos.entry_price, pos.size_usd,
                pos.valid_until,
            )

    paper_state.save(ps)

    # R1 — kararı disk snapshot store'a kaydet (replay temeli). Store yazımı
    # ASLA tick'i patlatmaz; başarısızsa loglanır ve döngü devam eder.
    try:
        view = matrix_view(_regime, _risk, decisions, snap, MATRIX_SYMBOLS)
        view["mode"] = data_provenance(snap)
        sid = snapshot_store.record(_snapshot_record(snap, view, _risk, ps))
        if sid:
            log.info("snapshot stored: %s (count=%d)", sid, snapshot_store.count())
    except Exception:
        log.exception("snapshot store record failed (tick devam ediyor)")


async def run() -> None:
    _install_signals()
    log.info("tick_worker started, interval=%ds", INTERVAL)
    while not _STOP.is_set():
        try:
            await run_once()
        except Exception as exc:
            log.exception("tick failed: %s", exc)
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=INTERVAL)
        except TimeoutError:
            pass
    log.info("tick_worker stopped")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run())
