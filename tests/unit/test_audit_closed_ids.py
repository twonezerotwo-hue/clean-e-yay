"""Öğrenme kanıtı: denetim günlüğündeki tüm kapanışlar (eski kayıtlar position_id ile)."""
from __future__ import annotations

import json

from packages.paper import audit


def _write(path, events):
    path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")


def test_closed_ids_scan_whole_log_and_rotated_archive(tmp_path, monkeypatch):
    log = tmp_path / "paper_audit.jsonl"
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(log))
    _write(tmp_path / "paper_audit.jsonl.1", [{"action": "CLOSED", "position_id": "old1"}])
    events = [{"action": "CLOSED", "position_id": "p1"},                 # eski kayıt: trade_id yok
              {"action": "KILL_SWITCH_EXIT", "position_id": "p2", "trade_id": "t2"},
              {"action": "OPENED", "position_id": "p3"}]
    events += [{"action": "OPEN_BLOCKED", "symbol": "BTCUSD"}] * 500  # son 200 pencerenin dışı
    _write(log, events)
    assert audit.closed_trade_ids() == {"old1", "p1", "t2"}
    with log.open("a", encoding="utf-8") as fh:                          # önbellek dosyayla tazelenir
        fh.write(json.dumps({"action": "TIME_STOP_EXPIRED", "trade_id": "t9"}) + "\n")
    assert "t9" in audit.closed_trade_ids()
