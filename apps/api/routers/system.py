"""GET /api/v1/system/health — O1 7/24 worker reliability özeti.

api/worker/provider/dqs/snapshot/halt durumu + owner warning'leri. Network-free
(snapshot store + heartbeat + halt + paper audit'ten okur; live provider çağırmaz).
PAPER_SAFE / NO_EXECUTION: yalnızca raporlar — trade açmaz, RiskGate bypass etmez.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.ops.system_health import build_system_health

router = APIRouter(tags=["system"])


@router.get("/system/health")
def get_system_health() -> dict:
    return build_system_health()
