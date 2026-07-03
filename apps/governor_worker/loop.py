"""Standalone governor loop daemon — runs governor_worker.run_once() forever.

    python -m apps.governor_worker.loop

learning_worker.loop ile aynı desen: lokal (üç-süreç) mimaride supervisor
çalışmadığı için governor'ın periyodik koşusunu bu bağımsız süreç sağlar.
AWS'te supervisor kendi governor döngüsünü zaten çalıştırır (RUN_GOVERNOR)
— orada bu script başlatılmaz.

Her koşu observe-only: görev üret + read-only koş (rapor). Trade/config'e
yazamaz (packages/governor/tasks.py yapısal invariant'ları).

Env:
    GOVERNOR_INTERVAL_SEC (default 900) — supervisor'daki default ile aynı
"""
from __future__ import annotations

import logging
import os
import signal
import time

from apps.governor_worker.main import run_once
from packages.data.registry.loader import REPO_ROOT

_log = logging.getLogger("apps.governor_worker.loop")
_STOP = False


def _handle_stop(signum: int, frame: object) -> None:
    global _STOP
    _STOP = True


def _acquire_singleton_lock():
    """Tek-örnek kilidi: keeper tick'i ile manuel start-dashboard çağrısı
    yarışırsa iki loop doğabiliyor (check-then-start TOCTOU). İkinci kopya
    burada sessizce çıkar. Kilit süreç ölünce OS tarafından bırakılır —
    stale-lock problemi yok. Kilit alınamazsa None döner."""
    import msvcrt

    lock_path = REPO_ROOT / "data" / "runtime" / "governor_loop.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a")  # ömrü süreç ömrü kadar — kapatılmaz
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return handle
    except OSError:
        handle.close()
        return None


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    lock = _acquire_singleton_lock()
    if lock is None:
        _log.info("governor loop zaten çalışıyor — bu kopya çıkıyor")
        return
    interval = int(os.environ.get("GOVERNOR_INTERVAL_SEC", "900"))
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)
    _log.info("governor loop started, interval=%ds", interval)
    while not _STOP:
        try:
            run_once()
        except Exception:
            _log.exception("governor run_once failed")
        for _ in range(interval):
            if _STOP:
                break
            time.sleep(1)
    _log.info("governor loop stopped")


if __name__ == "__main__":
    main()
