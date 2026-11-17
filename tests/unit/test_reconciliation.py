from packages.paper.reconciliation import reconcile


def test_reconcile_keeps_ticket_and_position_identity_together():
    result = reconcile(
        tickets={"tickets": [{
            "id": "t1", "status": "active", "position_id": "p1",
            "signal_id": "s1", "decision_id": "d1", "news_evidence_id": "e1",
        }]},
        positions=[{
            "id": "p1", "signal_id": "s1", "decision_id": "d1", "news_evidence_id": "e1",
        }],
        notifications=[{"id": "n1", "type": "ticket_created", "ticket_id": "t1"}],
    )
    assert result["status"] == "PASS"
    assert result["score"] == 100.0


def test_reconcile_reports_signal_without_position_instead_of_inventing_one():
    result = reconcile(
        tickets={"tickets": [{"id": "t1", "status": "active", "position_id": "missing"}]},
        positions=[],
        notifications=[],
    )
    assert result["status"] == "FAIL"
    assert result["mismatches"][0]["type"] == "ticket_position_missing"


def test_reconcile_marks_legacy_attribution_incomplete_not_wrong():
    result = reconcile(
        tickets={"tickets": [{"id": "t1", "status": "active", "position_id": "p1", "decision_id": "d1"}]},
        positions=[{"id": "p1", "decision_id": None}],
        notifications=[],
    )
    assert result["status"] == "WARN"
    assert result["incomplete"][0]["type"] == "position_missing_decision_id"


# ---------- 17 Kasım: kartı düşmüş açık pozisyon karar kaydıyla doğrulanır ----------

_OPEN = {"id": "p1", "signal_id": "s1", "decision_id": "dec_abc", "opened_at": "2026-11-16T18:47:20+00:00"}


def test_open_position_without_ticket_is_linked_when_decision_is_recorded():
    # Önceden: pozisyon açılıp kart listeden düşünce "open_position_without_ticket" FAIL.
    assert reconcile(tickets={"tickets": []}, positions=[_OPEN], notifications=[])["status"] == "FAIL"
    result = reconcile(tickets={"tickets": []}, positions=[_OPEN], notifications=[],
                       decision_lookup=lambda did, at: did == "dec_abc")
    assert result["status"] == "PASS"
    assert result["recorded_positions"] == 1 and result["mismatches"] == []


def test_open_position_whose_decision_is_not_recorded_fails():
    result = reconcile(tickets={"tickets": []}, positions=[_OPEN], notifications=[],
                       decision_lookup=lambda did, at: False)
    assert result["status"] == "FAIL"
    assert result["mismatches"] == [{"position_id": "p1", "decision_id": "dec_abc",
                                     "type": "position_decision_not_recorded"}]


def test_unverifiable_decision_is_a_warning_not_a_failure():
    result = reconcile(tickets={"tickets": []}, positions=[_OPEN], notifications=[],
                       decision_lookup=lambda did, at: None)
    assert result["status"] == "WARN"
    assert result["incomplete"][0]["type"] == "decision_record_unavailable"


def test_decision_recorded_reads_the_opening_day_and_its_neighbours(tmp_path, monkeypatch):
    from packages.paper import reconciliation

    monkeypatch.setenv("DECISION_RECORD_DIR", str(tmp_path))
    monkeypatch.setattr(reconciliation, "_RECORDED", set())
    assert reconciliation.decision_recorded("dec_abc", _OPEN["opened_at"]) is None      # kayıt yok
    (tmp_path / "2026-11-16.jsonl").write_text('{"cells": [{"decision_id": "dec_other"}]}\n', encoding="utf-8")
    assert reconciliation.decision_recorded("dec_abc", _OPEN["opened_at"]) is False     # gün var, karar yok
    (tmp_path / "2026-11-15.jsonl").write_text('{"cells": [{"decision_id": "dec_abc"}]}\n', encoding="utf-8")
    assert reconciliation.decision_recorded("dec_abc", _OPEN["opened_at"]) is True      # önceki gün dosyası
    assert reconciliation.decision_recorded("dec_abc", "bozuk") is True                 # bulunan önbellekte
    assert reconciliation.decision_recorded("dec_x", "bozuk") is None
