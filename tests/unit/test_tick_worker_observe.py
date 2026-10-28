"""T1 — worker gözlem yüzeyi (eski API tick motorundan taşınan blok).

Kapsam:
- ticket deposu round-trip (save_last/load_last; dosya yok/bozuksa boş döner);
- run_once sonrası: tickets deposu built_at damgalı, state recheck damgalı,
  heartbeat FAILED değil (run_once istisnayı yutar — sessiz çökme yakalanır);
- GET /paper-trading/tickets worker'ın yazdığı depodan okur (API'de motor yok).
"""
from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("TICKETS_PATH", str(tmp_path / "tickets.json"))
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "halts.json"))
    from packages.paper import state as ps
    importlib.reload(ps)
    return ps


def test_ticket_store_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TICKETS_PATH", str(tmp_path / "tickets.json"))
    from packages.paper import ticket

    assert ticket.load_last() == {"built_at": None, "tickets": []}
    ticket.save_last([{"id": "t-1", "status": "active"}])
    data = ticket.load_last()
    assert data["tickets"] == [{"id": "t-1", "status": "active"}]
    assert data["built_at"] is not None


def test_ticket_store_corrupt_file_returns_empty(tmp_path, monkeypatch) -> None:
    p = tmp_path / "tickets.json"
    monkeypatch.setenv("TICKETS_PATH", str(p))
    p.write_text("{bozuk json", encoding="utf-8")
    from packages.paper import ticket

    assert ticket.load_last() == {"built_at": None, "tickets": []}


def test_run_once_writes_observe_surfaces(env) -> None:
    from apps.tick_worker import main as tick_worker
    from packages.ops import heartbeat
    from packages.paper import ticket

    asyncio.run(tick_worker.run_once())
    hb = heartbeat.load("tick_worker")
    assert hb is not None and hb["status"] != "FAILED"
    # Gözlem yüzeyi: ticket deposu yazıldı (liste boş olabilir — mock koşula bağlı)
    data = ticket.load_last()
    assert data["built_at"] is not None
    assert isinstance(data["tickets"], list)
    # Recheck damgası state'e işlendi (worker pass'inin yan ürünü)
    assert env.load().last_recheck_at is not None


def test_get_tickets_reads_worker_store(env) -> None:
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from packages.paper import ticket

    ticket.save_last([
        {"id": "tk-1", "status": "active"},
        {"id": "tk-2", "status": "insufficient_rr"},
    ])
    client = TestClient(app)
    r = client.get("/api/v1/paper-trading/tickets")
    assert r.status_code == 200
    body = r.json()
    assert [t["id"] for t in body["tickets"]] == ["tk-1"]  # filtreli: yalnız active
    assert body["total"] == 1
    assert body["last_built_at"] is not None


def test_ticket_notifications_share_news_confluence_gate(monkeypatch) -> None:
    """A signal without final news+technical confluence is not announced."""
    from packages.paper import ticket

    decision = SimpleNamespace(
        action="open_short",
        symbol="XAGUSD",
        timeframe="15m",
        risk=SimpleNamespace(action="ALLOW_NORMAL"),
    )
    snapshot = SimpleNamespace(
        prices=[SimpleNamespace(symbol="XAGUSD", price=53.2, verified=True)]
    )
    state = SimpleNamespace(news_prepared_setups=[])
    monkeypatch.setattr(ticket, "is_execution_ready", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(ticket.news_setup, "require_confluence_for_auto_open", lambda: True)
    monkeypatch.setattr(ticket.news_setup, "match_confluence", lambda *_args, **_kwargs: None)
    assert ticket.build_tickets_from_decisions([decision], snapshot, state) == []

    monkeypatch.setattr(ticket.news_setup, "match_confluence", lambda *_args, **_kwargs: {"setup_id": "s1"})
    monkeypatch.setattr(ticket, "build_ticket", lambda *_args, **_kwargs: SimpleNamespace(status="active"))
    assert len(ticket.build_tickets_from_decisions([decision], snapshot, state)) == 1
