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
from packages.data.ingestion.pipeline import DEFAULT_SYMBOLS, get_cached_snapshot
from packages.decision.engine import decide_matrix
from packages.paper import state as paper_state
from packages.paper.lifecycle import flatten_all, open_position
from packages.paper.lifecycle import tick as price_tick
from packages.risk import halt as halt_store
from packages.risk.engine import RiskInput

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
        DEFAULT_SYMBOLS[:4], snap, risk_in, open_positions=ps.open_positions
    )
    open_keys = {(p.symbol, p.timeframe) for p in ps.open_positions}
    for d in decisions:
        if d.action in {"blocked", "hold"} or (d.symbol, d.timeframe) in open_keys:
            continue
        price = prices.get(d.symbol)
        if price is None or price <= 0:
            continue
        side = "long" if d.action == "open_long" else "short"
        pos = open_position(
            ps,
            symbol=d.symbol,
            side=side,
            entry_price=price,
            size_multiplier=d.size_multiplier,
            fingerprint=d.fingerprint,
            data_verified=verified_flags.get(d.symbol, False),
            predicted_confidence=d.confidence,
            raw_confidence=d.raw_confidence,
            confidence_source=d.confidence_source,
            timeframe=d.timeframe,
        )
        log.info(
            "open: %s %s %s @ %.4f size=%.0f valid_until=%s",
            pos.symbol, pos.timeframe, pos.side, pos.entry_price, pos.size_usd,
            pos.valid_until,
        )

    paper_state.save(ps)


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
