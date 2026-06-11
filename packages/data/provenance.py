"""Veri kaynak/güvenilirlik damgası (mode block).

Tüm karar API'leri bu helper'ı kullanır:
- LIVE             → tüm price quote'ları verified+OK, DQS OK, mock yok.
- MOCK MODE        → PRICE_USE_MOCK=true (runtime explicit) → kırmızı banner.
- SIMULATION       → test fixture (TEST_USE_MOCK) veya verified=false price var.
- INSUFFICIENT_DATA→ DQS BLOCKED/DEGRADED, live providers veri getiremiyor.

Frontend `mode.live_data` false ise verdict'leri "SIMULATION ONLY" etiketler.
"""
from __future__ import annotations

from packages.data.ingestion.pipeline import MarketSnapshot
from packages.data.providers import price as price_provider


def _resolve_label(snap: MarketSnapshot, mock_warning: bool, test_mock: bool) -> tuple[str, str]:
    if mock_warning:
        return (
            "MOCK_MODE",
            "PRICE_USE_MOCK=true — mock veriyle çalışıyor; karar live değildir.",
        )
    if snap.quality.status == "BLOCKED":
        return (
            "INSUFFICIENT_DATA",
            "DQS BLOCKED — gerçek veri yetersiz, yeni karar üretilmiyor.",
        )
    if test_mock:
        return (
            "SIMULATION",
            "Test/dev fixture aktif (TEST_USE_MOCK); karar live değildir.",
        )
    if any(not p.verified or p.price is None for p in snap.prices):
        if snap.quality.status == "DEGRADED":
            return (
                "SIMULATION",
                "Bazı kaynaklar veri sağlayamıyor (DQS DEGRADED); karar live sayılmaz.",
            )
        return (
            "SIMULATION",
            "Doğrulanmamış kaynak var; karar live sayılmaz.",
        )
    if snap.quality.status == "DEGRADED":
        return (
            "SIMULATION",
            "DQS DEGRADED — ham veri tam doğrulanamıyor; karar live sayılmaz.",
        )
    return ("LIVE", "Gerçek veri, tüm kaynaklar doğrulanmış.")


def data_provenance(snap: MarketSnapshot) -> dict:
    mock_mode = price_provider.is_mock_mode()
    mock_warning = price_provider.is_runtime_mock_explicit()
    test_mock = price_provider.is_test_mock_allowed()
    label, advisory = _resolve_label(snap, mock_warning, test_mock)
    live_data = label == "LIVE"
    return {
        "live_data": live_data,
        "mock_mode": mock_mode,
        "mock_warning": mock_warning,
        "test_mock": test_mock,
        "dqs_status": snap.quality.status,
        "label": label,
        "advisory": advisory,
    }


def decision_disclaimer(snap: MarketSnapshot) -> str | None:
    """Karar/verdict satırının önüne basılacak uyarı; None → uyarı yok."""
    p = data_provenance(snap)
    if p["live_data"]:
        return None
    return f"[{p['label']}] {p['advisory']}"
