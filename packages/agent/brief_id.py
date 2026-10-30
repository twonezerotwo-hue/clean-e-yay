"""Canonical identity for the read-only executive brief.

The visual brief, notification text and voice reader must describe the same
snapshot.  The id is therefore derived from immutable state identifiers rather
than the render time; polling the cockpit does not manufacture a new brief.
"""
from __future__ import annotations

import hashlib


def build_brief_id(snapshot_id: str | None, paper_state_revision: int | str | None) -> str:
    raw = f"{snapshot_id or 'snapshot-missing'}|{paper_state_revision if paper_state_revision is not None else 'state-missing'}"
    return "brief_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


__all__ = ["build_brief_id"]
