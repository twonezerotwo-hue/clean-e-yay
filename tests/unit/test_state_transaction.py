"""T3 — defter transaction'ı (dış denetim P0-1: lost update).

Kapsam:
- transaction() commit'i kalıcıdır ve revision'ı +1 artırır (legacy dosya 0'dan);
- istisna → abort: değişiklik YAZILMAZ, revision değişmez;
- kilitsiz yazar araya girerse (bug simülasyonu) STATE_CONFLICT audit'i düşer;
- iki AYRI SÜREÇ eşzamanlı artırım yapar → hiçbir artırım kaybolmaz (asıl P0).
"""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def st(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    from packages.paper import state as ps
    importlib.reload(ps)
    return ps


def test_commit_persists_and_bumps_revision(st) -> None:
    with st.transaction("test") as ps:
        ps.equity_usd += 100.0
    after = st.load()
    assert after.revision == 1
    base = after.equity_usd
    with st.transaction("test") as ps:
        ps.equity_usd += 50.0
    after2 = st.load()
    assert after2.revision == 2
    assert after2.equity_usd == base + 50.0


def test_abort_on_exception_discards_changes(st) -> None:
    with st.transaction("seed") as ps:
        pass  # revision=1 ile dosya otursun
    before = st.load()
    with pytest.raises(RuntimeError):
        with st.transaction("boom") as ps:
            ps.equity_usd += 999.0
            raise RuntimeError("patla")
    after = st.load()
    assert after.equity_usd == before.equity_usd
    assert after.revision == before.revision


def test_unguarded_writer_triggers_state_conflict_audit(st, tmp_path) -> None:
    with st.transaction("seed"):
        pass
    txn = st.begin("test-conflict")
    try:
        # Kilitsiz yazar simülasyonu: dosyayı doğrudan farklı revision'la ez
        # (flock tavsiye kilididir — doğrudan yazımı engellemez; mesele onu
        # commit anında YAKALAMAK).
        raw = json.loads(st.STATE_PATH.read_text(encoding="utf-8"))
        raw["revision"] = 99
        st.STATE_PATH.write_text(json.dumps(raw), encoding="utf-8")
        txn.state.equity_usd += 1.0
        txn.commit()
    finally:
        txn.abort()
    audit_lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in audit_lines]
    assert any(e.get("action") == "STATE_CONFLICT" for e in events), events
    # Son-yazan-kazanır ama artık görünür iz var; revision monoton devam eder.
    assert st.load().revision == 2


_WORKER_SNIPPET = """
import sys
from packages.paper import state as st
for _ in range(int(sys.argv[1])):
    with st.transaction("race") as ps:
        ps.equity_usd += 1.0
"""


def test_two_processes_no_lost_update(st, tmp_path) -> None:
    """Asıl P0 senaryosu: iki süreç aynı deftere eşzamanlı yazar; kilit sayesinde
    hiçbir artırım kaybolmaz (kilitsiz dünyada bu test olasılıksal olarak düşerdi)."""
    with st.transaction("seed") as ps:
        base = ps.equity_usd
    n = 15
    env = {
        "PAPER_STATE_PATH": str(tmp_path / "paper.json"),
        "PAPER_AUDIT_PATH": str(tmp_path / "audit.jsonl"),
        "PATH": "/usr/bin:/bin",
    }
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _WORKER_SNIPPET, str(n)],
            cwd=str(REPO), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    for p in procs:
        _, err = p.communicate(timeout=120)
        assert p.returncode == 0, err.decode(errors="replace")
    after = st.load()
    assert after.equity_usd == base + 2 * n  # kayıp artırım YOK
    assert after.revision == 1 + 2 * n
