"""GET /api/v1/system/health — O1 7/24 worker reliability özeti.

api/worker/provider/dqs/snapshot/halt durumu + owner warning'leri. Network-free
(snapshot store + heartbeat + halt + paper audit'ten okur; live provider çağırmaz).
PAPER_SAFE / NO_EXECUTION: yalnızca raporlar — trade açmaz, RiskGate bypass etmez.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.ops import compliance, metrics, registry
from packages.ops.system_health import build_system_health

router = APIRouter(tags=["system"])


@router.get("/system/health")
def get_system_health() -> dict:
    return build_system_health()


@router.get("/system/metrics")
def get_system_metrics() -> dict:
    """Tick aşama süreleri (son 60 tur: son, p50, p95, en yüksek) — salt okuma."""
    return metrics.tick_metrics()


@router.get("/system/registry")
def get_system_registry() -> dict:
    """Model, sinyal ve ajan sürümleri (salt okuma)."""
    return registry.snapshot()


@router.get("/system/compliance")
def get_system_compliance(limit: int = compliance.DEFAULT_LIMIT) -> dict:
    """Denetim ve uyum kaydı: son komutlar + hash zinciri doğrulaması (salt okuma)."""
    return compliance.report(limit)
