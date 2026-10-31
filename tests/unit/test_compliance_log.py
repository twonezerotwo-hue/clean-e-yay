"""st_audit — yazma komutları hash zincirli denetim kaydına düşer; değişiklik görünür."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from apps.api.main import app
from packages.ops import compliance


def test_commands_are_chained_and_reads_are_not_logged(tmp_path, monkeypatch):
    log = tmp_path / "compliance.jsonl"
    monkeypatch.setenv("COMPLIANCE_LOG_PATH", str(log))
    monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
    client = TestClient(app)
    client.get("/api/v1/system/compliance")                       # okuma: kayıt yok
    client.post("/api/v1/notifications/ack-all")                   # komut değil: kayıt yok
    client.post("/api/v1/governor/proposals/nope/reject")          # komut (bulunamasa da)
    client.post("/api/v1/risk/halts/reset?scope=all")
    rep = client.get("/api/v1/system/compliance").json()
    assert rep["total"] == 2 and rep["chain_ok"] is True
    newest = rep["entries"][0]
    assert newest["path"] == "/api/v1/risk/halts/reset" and newest["query"] == "scope=all"
    assert newest["actor"] == "local" and newest["prev"] == rep["entries"][1]["hash"]


def test_denied_attempt_is_logged_and_tampering_is_detected(tmp_path, monkeypatch):
    log = tmp_path / "compliance.jsonl"
    monkeypatch.setenv("COMPLIANCE_LOG_PATH", str(log))
    monkeypatch.setenv("API_AUTH_TOKEN", "t0ken")
    client = TestClient(app)
    assert client.post("/api/v1/risk/halts/reset").status_code == 401
    client.post("/api/v1/risk/halts/reset", headers={"Authorization": "Bearer t0ken"})
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["outcome"] == "denied" and rows[0]["actor"] == "anonymous"
    assert rows[1]["actor"] == "owner"
    assert compliance.verify()["chain_ok"] is True
    rows[0]["path"] = "/api/v1/something/else"                       # sonradan değiştirme
    log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    assert compliance.verify() == {"chain_ok": False, "broken_at": 0}


def test_automatic_promotions_join_the_same_chain(tmp_path, monkeypatch):
    monkeypatch.setenv("COMPLIANCE_LOG_PATH", str(tmp_path / "compliance.jsonl"))
    from packages.learning import weight_autoapply_store as was

    monkeypatch.setattr(was, "_save", lambda _d: None)
    monkeypatch.setattr(was, "load", lambda: {"active": None, "history": []})
    was.record_apply(applied_version="1.0.1", prev_version="1.0.0", prev_manifest=None,
                     baseline_expectancy=0.1, baseline_n=30, regime=None, deltas={})
    rep = compliance.report()
    assert rep["chain_ok"] and rep["entries"][0]["action"] == "WEIGHTS_AUTO_APPLIED"
    assert rep["entries"][0]["actor"] == "auto" and rep["entries"][0]["detail"]["version"] == "1.0.1"
