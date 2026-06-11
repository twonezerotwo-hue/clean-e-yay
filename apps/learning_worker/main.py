"""Learning worker — kalibrasyon + walk-forward + ağırlık eğitimi.

Saatlik veya günlük tetikli (cron / scheduler). API'den bağımsızdır.
v2.4'te implement edilecek.
"""
from __future__ import annotations

import logging

log = logging.getLogger("learning_worker")


def run_once() -> None:
    log.info("learning_worker skeleton — v2.4'te implement edilecek")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_once()
