"""B6 — tek atomik yazma yardımcısı (packages.ops.store)."""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

import pytest

from packages.ops import store

REPO = Path(__file__).resolve().parents[2]


def test_bytes_match_plain_write_text(tmp_path):
    text = json.dumps({"a": "ğüş", "b": [1, 2]}, ensure_ascii=False, indent=2) + "\n"
    ref = tmp_path / "ref.json"
    ref.write_text(text, encoding="utf-8")
    out = tmp_path / "sub" / "out.json"
    store.write_text_atomic(out, text)
    assert out.read_bytes() == ref.read_bytes()


def test_no_tmp_left_and_failure_keeps_target(tmp_path, monkeypatch):
    p = tmp_path / "x.json"
    store.write_json_atomic(p, {"v": 1})
    assert [f.name for f in tmp_path.iterdir()] == ["x.json"]

    def boom(src, dst):
        raise OSError("disk")

    monkeypatch.setattr(store.os, "replace", boom)
    monkeypatch.setattr(store, "_RETRY_BASE_SLEEP_S", 0.0)
    with pytest.raises(OSError):
        store.write_json_atomic(p, {"v": 2})
    assert json.loads(p.read_text()) == {"v": 1}
    assert [f.name for f in tmp_path.iterdir()] == ["x.json"]


def test_replace_retries_transient_lock(tmp_path, monkeypatch):
    real = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("locked")
        real(src, dst)

    monkeypatch.setattr(store.os, "replace", flaky)
    monkeypatch.setattr(store, "_RETRY_BASE_SLEEP_S", 0.0)
    store.write_text_atomic(tmp_path / "y.txt", "ok")
    assert (tmp_path / "y.txt").read_text() == "ok" and calls["n"] == 3


def test_concurrent_writers_never_tear(tmp_path):
    p = tmp_path / "z.json"
    errors = []

    def writer(k):
        try:
            for i in range(50):
                store.write_json_atomic(p, {"k": k, "i": i, "pad": "x" * 2000})
        except Exception as exc:  # pragma: no cover - hata testi düşürür
            errors.append(exc)

    ts = [threading.Thread(target=writer, args=(k,)) for k in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors
    assert json.loads(p.read_text())["pad"] == "x" * 2000
    assert [f.name for f in tmp_path.iterdir()] == ["z.json"]


def test_no_handrolled_tmp_replace_in_packages():
    """Ratchet: store'lar kendi tmp+replace kodunu yeniden yazmasın."""
    allowed = {"packages/ops/store.py"}
    pat = re.compile(r"\btmp\w*\.replace\(|os\.replace\(tmp")
    offenders = []
    for f in (REPO / "packages").rglob("*.py"):
        rel = f.relative_to(REPO).as_posix()
        if rel in allowed:
            continue
        if pat.search(f.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert offenders == [], f"write_text_atomic kullan: {offenders}"


def _old_tail(path, limit):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return lines[-max(1, limit):]


@pytest.mark.parametrize("ending", ["\n", "\r\n", ""])
@pytest.mark.parametrize("limit", [1, 3, 200, 5000])
def test_read_tail_lines_matches_full_read(tmp_path, ending, limit):
    rows = [json.dumps({"i": i, "t": "ğüş" * (i % 7)}, ensure_ascii=False) for i in range(1200)]
    p = tmp_path / "log.jsonl"
    p.write_bytes((ending.join(rows) + ending).encode("utf-8") if ending else "\n".join(rows).encode("utf-8"))
    got = store.read_tail_lines(p, limit, chunk=257)  # küçük blok: sınır durumları
    assert got == _old_tail(p, limit)


def test_read_jsonl_tail_skips_bad_and_missing(tmp_path):
    p = tmp_path / "x.jsonl"
    assert store.read_jsonl_tail(p, 10) == []
    p.write_text('{"a":1}\n\nbozuk\n[1,2]\n{"b":2}\n', encoding="utf-8")
    assert store.read_jsonl_tail(p, 10) == [{"a": 1}, {"b": 2}]
    assert store.read_jsonl_tail(p, 1) == [{"b": 2}]
