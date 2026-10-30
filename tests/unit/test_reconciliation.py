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
