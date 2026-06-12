"""GET /api/v1/replay/status, GET /api/v1/replay/{snapshot_id}

Replay temeli — DÜRÜST iskelet. Deterministik replay / backtest motoru
**REZERVE**; bu sürümde AKTİF DEĞİL. Sahte replay veya uydurma backtest
üretilmez (PAPER_SAFE / NO_EXECUTION).

Bu endpoint yalnızca:
- En son okunabilir snapshot kimliğini dürüstçe raporlar.
- Replay durumunu `reserved_not_active` olarak açıkça bildirir.
- Belirli bir snapshot_id istenirse, en son snapshot ile eşleşip
  eşleşmediğini söyler ama replay çalıştırmaz.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.data.ingestion.pipeline import get_cached_snapshot

router = APIRouter(tags=["replay"])

# Replay motoru henüz yok; durum dürüstçe rezerve olarak raporlanır.
REPLAY_STATUS = "reserved_not_active"
_REASON = (
    "Deterministik replay / backtest motoru rezerve — bu sürümde aktif değil. "
    "Sahte replay üretilmez (PAPER_SAFE / NO_EXECUTION)."
)


@router.get("/replay/status")
def get_replay_status() -> dict:
    """Replay altyapı durumu + en son okunabilir snapshot (read-only)."""
    snap = get_cached_snapshot()
    return {
        "status": REPLAY_STATUS,
        "available": False,
        "latest_snapshot_id": snap.snapshot_id,
        "generated_at": snap.generated_at.isoformat(),
        "reason": _REASON,
    }


@router.get("/replay/{snapshot_id}")
def get_replay(snapshot_id: str) -> dict:
    """Belirli snapshot için replay isteği — dürüstçe rezerve döner (çalıştırmaz)."""
    snap = get_cached_snapshot()
    return {
        "snapshot_id": snapshot_id,
        "status": REPLAY_STATUS,
        "available": False,
        "matches_latest": snapshot_id == snap.snapshot_id,
        "latest_snapshot_id": snap.snapshot_id,
        "reason": _REASON,
    }
