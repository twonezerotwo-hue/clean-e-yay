"""Read-only reconciliation for the paper decision chain.

The worker is the only writer, but the UI consumes several persisted surfaces
(tickets, notifications and the paper ledger).  This module never repairs or
mutates those files; it reports whether the same signal still points to the
same decision and position.  Missing legacy attribution is reported as
``incomplete`` rather than fabricated.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def _rows(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        value = value.get("tickets") or value.get("notifications") or value.get("open_positions") or []
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _index(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, Mapping[str, Any]]:
    return {
        str(row.get(key)): row
        for row in rows
        if row.get(key) not in (None, "")
    }


def reconcile(
    *,
    tickets: Any = None,
    positions: Any = None,
    notifications: Any = None,
) -> dict[str, Any]:
    """Return deterministic identity-chain health for current paper state.

    Only active tickets and ``ticket_created`` notifications are checked.  A
    historical notification may legitimately refer to a closed position.
    """
    ticket_rows = [r for r in _rows(tickets) if str(r.get("status", "active")) == "active"]
    position_rows = _rows(positions)
    notif_rows = [r for r in _rows(notifications) if r.get("type") == "ticket_created"]
    by_position = _index(position_rows, "id")
    by_ticket = _index(ticket_rows, "id")

    mismatches: list[dict[str, Any]] = []
    incomplete: list[dict[str, Any]] = []
    for ticket in ticket_rows:
        tid = str(ticket.get("id"))
        pid = ticket.get("position_id")
        if not pid:
            mismatches.append({"type": "ticket_without_position", "ticket_id": tid})
            continue
        position = by_position.get(str(pid))
        if position is None:
            mismatches.append({"type": "ticket_position_missing", "ticket_id": tid, "position_id": pid})
            continue
        for field in ("signal_id", "decision_id", "news_evidence_id"):
            ticket_value = ticket.get(field)
            position_value = position.get(field)
            if ticket_value and position_value and str(ticket_value) != str(position_value):
                mismatches.append({
                    "type": f"{field}_mismatch",
                    "ticket_id": tid,
                    "position_id": pid,
                    "ticket": ticket_value,
                    "position": position_value,
                })
            elif ticket_value and not position_value:
                incomplete.append({"type": f"position_missing_{field}", "ticket_id": tid, "position_id": pid})

    historical_notifications = 0
    for notification in notif_rows:
        ticket_id = notification.get("ticket_id")
        if ticket_id and str(ticket_id) not in by_ticket:
            # A notification can outlive a ticket.  Keep it visible as an
            # informational count, never turn it into an active trade signal.
            historical_notifications += 1
        elif not ticket_id:
            incomplete.append({"type": "notification_without_ticket", "notification_id": notification.get("id")})

    active_position_ids = {
        str(row.get("position_id"))
        for row in ticket_rows
        if row.get("position_id") not in (None, "")
    }
    for row in position_rows:
        if not row.get("id") or str(row.get("id")) in active_position_ids:
            continue
        # Positions created before the canonical ticket lane have no identity
        # to reconcile.  Keep them visible as legacy/incomplete, but do not
        # label them as a live mismatch or block the system health endpoint.
        item = {
            "type": "open_position_without_ticket",
            "position_id": row.get("id"),
            "signal_id": row.get("signal_id"),
        }
        if any(row.get(key) for key in ("signal_id", "decision_id", "news_evidence_id")):
            mismatches.append(item)
        else:
            incomplete.append({**item, "type": "legacy_open_position"})

    total = len(ticket_rows) + len(position_rows)
    bad = len(mismatches)
    score = 100.0 if total == 0 else round(max(0.0, 100.0 - (bad / max(1, total)) * 100.0), 1)
    return {
        "status": "PASS" if not mismatches and not incomplete else ("WARN" if not mismatches else "FAIL"),
        "score": score,
        "active_tickets": len(ticket_rows),
        "open_positions": len(position_rows),
        "ticket_created_notifications": len(notif_rows),
        "historical_ticket_notifications": historical_notifications,
        "mismatches": mismatches,
        "incomplete": incomplete,
        "paper_safe": True,
        "no_execution": True,
    }


__all__ = ["reconcile"]
