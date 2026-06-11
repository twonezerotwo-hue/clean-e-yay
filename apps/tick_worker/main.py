"""Tick worker — paper trading 30sn döngüsü.

Ayrı process olarak çalışır. API ile aynı state dosyalarını paylaşır
ama HTTP'ye bağımlı değildir. v2.3'te implement edilecek.
"""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("tick_worker")


async def run() -> None:
    log.info("tick_worker skeleton — v2.3'te implement edilecek")
    while True:
        await asyncio.sleep(30)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
