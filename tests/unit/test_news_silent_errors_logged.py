"""N5 (grup 5): haber hattında yutulan hata artık bir log satırı bırakır; sonuç değişmez."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from types import SimpleNamespace

from packages.data.providers.news import first_seen


def test_first_seen_write_failure_is_logged_not_raised(tmp_path, monkeypatch, caplog):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("NEWS_FIRST_SEEN_PATH", str(blocker / "ledger.jsonl"))  # üst "klasör" bir dosya
    monkeypatch.setattr(first_seen, "_KNOWN", None, raising=False)
    head = SimpleNamespace(id="h1", ts=datetime(2026, 11, 25, tzinfo=UTC), source="Reuters", title="Fed holds rates", url=None, region=None)
    with caplog.at_level(logging.WARNING, logger=first_seen.__name__):
        assert first_seen.record("reuters", [head], group="market", now=datetime(2026, 11, 25, tzinfo=UTC)) == 0
    assert any("first_seen: ledger write failed" in r.getMessage() for r in caplog.records)
