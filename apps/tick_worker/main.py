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
from packages.decision.engine import decide_all
from packages.learning.fingerprint import make as make_fingerprint
from packages.paper import state as paper_state
from packages.paper.lifecycle import open_position
from packages.paper.lifecycle import tick as price_tick
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
    regime, _risk, decisions = decide_all(DEFAULT_SYMBOLS[:4], snap, risk_in)
    open_symbols = {p.symbol for p in ps.open_positions}
    for d in decisions:
        if d.action in {"blocked", "hold"} or d.symbol in open_symbols:
            continue
        price = prices.get(d.symbol)
        if price is None or price <= 0:
            continue
        fp = make_fingerprint(
            symbol=d.symbol,
            regime=regime.label,
            direction=d.consensus.direction,
            score=d.consensus.score,
            confluence=d.consensus.confluence_aligned,
            dominant_module=d.consensus.dominant_module,
        )
        side = "long" if d.action == "open_long" else "short"
        pos = open_position(
            ps,
            symbol=d.symbol,
            side=side,
            entry_price=price,
            size_multiplier=d.size_multiplier,
            fingerprint=fp,
            data_verified=verified_flags.get(d.symbol, False),
            predicted_confidence=d.confidence,
            raw_confidence=d.raw_confidence,
            confidence_source=d.confidence_source,
        )
        log.info("open: %s %s @ %.4f size=%.0f", pos.symbol, pos.side, pos.entry_price, pos.size_usd)

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
