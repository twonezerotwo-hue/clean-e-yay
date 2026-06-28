"""Part 1 — Governor öneri defteri + read-only özet testleri.

Kapsam:
- sanitize: geçerli/geçersiz tip, boş title reddi, JSON-safe indirgeme.
- submit roundtrip + dedup (aynı tip+requested_change PENDING çiftlenmez).
- approve/reject: history'e taşır, bulunamazsa None, canlı config'e DOKUNMAZ.
- summary_viewmodel + report.build_report() yapısı (crash-safe, best-effort).
- endpoint GET/POST/approve/reject (in-process), 404/422 yolları.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def iso_store(tmp_path, monkeypatch):
    monkeypatch.setenv("GOVERNOR_PROPOSALS_PATH", str(tmp_path / "governor_proposals.json"))
    return tmp_path


def _valid(**over) -> dict:
    base = {
        "proposal_type": "THRESHOLD_CHANGE",
        "title": "Reversal trigger eşiğini gevşet",
        "summary": "15m reversal setup'larda trigger çok sıkı.",
        "evidence": {"sample_count": 84, "missed_win_rate": 0.34},
        "requested_change": {"trigger_threshold": 0.55},
        "rollback_plan": "eski eşiğe dön",
        "source": "governor",
    }
    base.update(over)
    return base


# ----------------- sanitize -----------------

def test_sanitize_rejects_unknown_type() -> None:
    from packages.governor import proposals
    assert proposals.sanitize({"proposal_type": "BOGUS", "title": "x"}) is None


def test_sanitize_rejects_empty_title() -> None:
    from packages.governor import proposals
    assert proposals.sanitize({"proposal_type": "MODE_CHANGE", "title": "  "}) is None


def test_sanitize_drops_non_json_safe_dicts() -> None:
    from packages.governor import proposals
    clean = proposals.sanitize(_valid(evidence={"x": object()}, requested_change="nope"))
    assert clean is not None
    assert clean["evidence"] == {}  # JSON-safe değildi → boş
    assert clean["requested_change"] == {}  # dict değildi → boş


# ----------------- submit / dedup -----------------

def test_submit_roundtrip(iso_store) -> None:
    from packages.governor import proposals
    p = proposals.submit(_valid())
    assert p is not None
    assert p["status"] == "PENDING"
    assert p["proposal_id"]
    assert proposals.list_pending()[0]["proposal_id"] == p["proposal_id"]


def test_submit_invalid_returns_none(iso_store) -> None:
    from packages.governor import proposals
    assert proposals.submit({"proposal_type": "NOPE", "title": "x"}) is None
    assert proposals.list_pending() == []


def test_submit_dedup_same_change(iso_store) -> None:
    from packages.governor import proposals
    a = proposals.submit(_valid())
    b = proposals.submit(_valid(title="farklı başlık ama aynı değişiklik"))
    assert a["proposal_id"] == b["proposal_id"]  # aynı requested_change → çiftlenmez
    assert len(proposals.list_pending()) == 1


# ----------------- approve / reject -----------------

def test_approve_moves_to_history(iso_store) -> None:
    from packages.governor import proposals
    p = proposals.submit(_valid())
    rec = proposals.approve(p["proposal_id"])
    assert rec is not None
    assert rec["status"] == "APPROVED"
    assert rec["approved_by"] == "owner"
    assert "decided_at" in rec
    assert proposals.list_pending() == []
    assert proposals.load()["history"][0]["proposal_id"] == p["proposal_id"]


def test_reject_records_reason(iso_store) -> None:
    from packages.governor import proposals
    p = proposals.submit(_valid())
    rec = proposals.reject(p["proposal_id"], reason="risk çok yüksek")
    assert rec["status"] == "REJECTED"
    assert rec["reject_reason"] == "risk çok yüksek"


def test_decide_unknown_id_returns_none(iso_store) -> None:
    from packages.governor import proposals
    assert proposals.approve("nope") is None
    assert proposals.reject("nope") is None


def test_approve_does_not_touch_weights(iso_store, tmp_path, monkeypatch) -> None:
    """DEĞİŞMEZ SINIR: governor approve canlı weights manifest'ini YAZMAZ."""
    from packages.governor import proposals
    from packages.learning import rebalance_store

    monkeypatch.setenv("REBALANCE_STORE_PATH", str(tmp_path / "rebalance.json"))
    p = proposals.submit(_valid(proposal_type="WEIGHT_CHANGE"))
    proposals.approve(p["proposal_id"])
    # Governor defteri WEIGHT_CHANGE onayladı ama rebalance store'a hiçbir şey
    # girmedi → weights uygulaması ayrı owner-gated yolun sorumluluğu.
    assert rebalance_store.get_pending() is None


# ----------------- corrupt-safe -----------------

def test_corrupt_store_returns_empty(iso_store) -> None:
    from packages.governor import proposals
    (iso_store / "governor_proposals.json").write_text("{bozuk", encoding="utf-8")
    assert proposals.load() == {"pending": [], "history": []}
    # Yine de yazılabilir olmalı (üstüne temiz yazar).
    assert proposals.submit(_valid()) is not None


# ----------------- report -----------------

def test_report_structure_and_crash_safe(iso_store) -> None:
    from packages.governor import report
    r = report.build_report()
    for key in (
        "generated_at",
        "learned",
        "found_missed_opportunities",
        "proposals",
        "other_pending_approvals",
        "data_trust",
    ):
        assert key in r
    assert r["paper_safe"] is True
    assert r["no_execution"] is True
    # Her bölüm "available" bayrağı taşır (best-effort sözleşmesi).
    assert "available" in r["proposals"]


# ----------------- endpoint -----------------

def test_endpoints_roundtrip(iso_store, monkeypatch) -> None:
    monkeypatch.setenv("TEST_USE_MOCK", "true")
    from fastapi.testclient import TestClient

    from apps.api.main import app
    c = TestClient(app)

    # boş defter
    g = c.get("/api/v1/governor/proposals")
    assert g.status_code == 200
    assert g.json()["pending_count"] == 0

    # geçersiz → 422
    bad = c.post("/api/v1/governor/proposals", json={"proposal_type": "NOPE", "title": "x"})
    assert bad.status_code == 422

    # geçerli submit
    sub = c.post("/api/v1/governor/proposals", json=_valid())
    assert sub.status_code == 200
    pid = sub.json()["proposal"]["proposal_id"]

    # report onu görür
    rep = c.get("/api/v1/governor/report")
    assert rep.status_code == 200
    assert rep.json()["proposals"]["data"]["pending_count"] == 1

    # approve
    ap = c.post(f"/api/v1/governor/proposals/{pid}/approve")
    assert ap.status_code == 200
    assert ap.json()["proposal"]["status"] == "APPROVED"

    # tekrar approve → 404 (artık pending değil)
    assert c.post(f"/api/v1/governor/proposals/{pid}/approve").status_code == 404
