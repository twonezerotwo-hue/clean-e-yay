"""Supervisor entry point — uvicorn API + tick + learning, tek loop.

    python -m apps.supervisor

Ortam değişkenleri:
    API_HOST              (default 0.0.0.0)
    API_PORT              (default 9000)
    LEARNING_INTERVAL_SEC (default 300)
    RUN_WORKERS           (default true) — false ise sadece API

Mimari not: arka plan döngülerinin sahibi BURASIDIR, apps/api değil. Bu
sayede apps/api ince HTTP katmanı olarak kalır (architecture guard geçer),
ama kullanıcı hâlâ tek komutla 7/24 agent + API alır.

Tek çalışma şekli (owner kararı, 2026-10-02): lokal keeper da AWS de bu
süreci çalıştırır. tick_worker.run_once adı async olsa da içi senkron
(build_snapshot ~20 sn); event loop'ta koşarsa API her tick'te donar. Bu
yüzden tick ve learning ayrı thread'de koşar, loop yalnız HTTP'ye kalır.
Tick ayrıca tick_worker'ın tekil-süreç kilidini alır: başka bir tick süreci
canlıysa ikinci bir defter yazarı başlatılmaz.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

_log = logging.getLogger("apps.supervisor")


def _env_truthy(name: str, default: str = "true") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


async def _learning_loop(stop: asyncio.Event, interval: int) -> None:
    """learning_worker.run_once'ı periyodik döngüye sar (one-shot → daemon)."""
    from apps.learning_worker.main import run_once as learning_run_once

    _log.info("learning loop started, interval=%ds", interval)
    while not stop.is_set():
        try:
            await asyncio.to_thread(learning_run_once)
        except Exception:
            _log.exception("learning run_once failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
    _log.info("learning loop stopped")


def _run_tick_once_blocking() -> None:
    """tick_worker.run_once'ı bu thread'in kendi event loop'unda koş."""
    from apps.tick_worker import main as tick

    asyncio.run(tick.run_once())


def _rest_seconds(interval: float, elapsed: float, min_rest: float) -> float:
    """Tick sonrası bekleme: döngü hedefine kalan süre, ama en az `min_rest`."""
    return max(min_rest, interval - elapsed)


async def _tick_loop(stop: asyncio.Event, interval: int, min_rest: float = 10.0) -> None:
    """Tick döngüsü — iş thread'de, bekleme loop'ta (API hiç bloke olmaz).

    `interval` DÖNGÜ aralığıdır: iş süresi beklemeye EKLENMEZ (hedef = cycle
    başı + interval). Aksi halde ~34 sn iş + 30 sn bekleme ≈ 65 sn'de bir taze
    karar olurdu. Ama tick aralıktan uzun sürerse tick'ler beklemesiz arka arkaya
    koşup iş parçacığını (ve aynı süreçteki API/öğrenmeyi) boğmasın diye her
    tick'ten sonra en az `min_rest` saniye dinlenilir (owner kararı 2026-10-06:
    en az 10 sn → ~34 sn tick ile kararlar ~44 sn'de bir).
    """
    from apps.tick_worker import main as tick

    _log.info("tick loop started, interval=%ds min_rest=%.0fs", interval, min_rest)
    locked = False
    try:
        while not stop.is_set():
            cycle_start = time.monotonic()
            if not locked:
                try:
                    tick._acquire_single_instance()
                    locked = True
                except RuntimeError as exc:
                    # Başka tick yazarı canlı (ör. eski ayrı süreç). Çift yazar
                    # defteri ayrıştırır; o ölene kadar tick atlanır, API sürer.
                    _log.error("tick atlandı — %s", exc)
            if locked:
                try:
                    await asyncio.to_thread(_run_tick_once_blocking)
                except Exception:
                    _log.exception("tick run_once failed")
            # Döngü aralığı: iş süresini beklemeden düşerek hedefe hizala; ama en az
            # min_rest dinlen (uzun tick'ler arka arkaya koşmasın).
            remaining = _rest_seconds(interval, time.monotonic() - cycle_start, min_rest)
            try:
                await asyncio.wait_for(stop.wait(), timeout=remaining)
            except TimeoutError:
                pass
    finally:
        if locked:
            tick._release_single_instance()
    _log.info("tick loop stopped")


async def _serve() -> None:
    import uvicorn

    from apps.api.main import app

    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("API_PORT", "9000"))

    config = uvicorn.Config(app, host=host, port=port, log_level="info", lifespan="on")
    server = uvicorn.Server(config)

    stop = asyncio.Event()
    tasks: list[asyncio.Task] = []

    if _env_truthy("RUN_WORKERS", "true"):
        from apps.tick_worker.main import INTERVAL as tick_interval

        interval = int(os.environ.get("LEARNING_INTERVAL_SEC", "300"))
        tasks = [
            asyncio.create_task(_tick_loop(stop, tick_interval), name="tick_worker"),
            asyncio.create_task(_learning_loop(stop, interval), name="learning_loop"),
        ]
        _log.info("agent ON — tick + learning workers running alongside API")
    else:
        _log.info("agent OFF (RUN_WORKERS=false) — API only")

    try:
        # uvicorn.Server.serve() SIGINT/SIGTERM'i kendi yakalar; çıkışta
        # worker'ları durdururuz.
        await server.serve()
    finally:
        # Normal çıkışta döngüler stop'u görür ve thread'deki tick bitirilir.
        # SIGTERM/SIGINT'te uvicorn sinyali serve() sonrası yeniden yükseltir;
        # süreç burada beklemeden biter (eski davranış). Tick kilidi bayat kalır,
        # sonraki açılış ölü pid'i görüp devralır.
        stop.set()
        for t in tasks:
            try:
                await asyncio.wait_for(t, timeout=60.0)
            except (asyncio.CancelledError, TimeoutError, Exception):
                pass


def main() -> None:
    from packages.ops.logsetup import configure_logging

    configure_logging()  # UTF-8 akışlar + standart şema (Türkçe log bozulmasın)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
