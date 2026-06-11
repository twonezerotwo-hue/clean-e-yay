"""Olay takvimi sağlayıcısı — mock-first."""
from __future__ import annotations

import hashlib
from datetime import timedelta

from packages.data.types import Catalyst, utcnow

_MOCK_EVENTS: list[tuple[str, str, int]] = [
    # (title, importance, hours_from_now)
    ("US CPI (YoY)", "high", 4),
    ("FOMC Minutes", "high", 26),
    ("ECB Press Conference", "medium", 51),
    ("US Initial Jobless Claims", "low", 8),
    ("China Industrial Production", "medium", 34),
    ("OPEC+ Monthly Report", "medium", 14),
]


def list_catalysts(limit: int = 10) -> list[Catalyst]:
    now = utcnow()
    out: list[Catalyst] = []
    for i, (title, imp, h) in enumerate(_MOCK_EVENTS[:limit]):
        cid = hashlib.sha1(f"{title}|{i}".encode()).hexdigest()[:10]
        out.append(
            Catalyst(
                id=cid,
                ts=now + timedelta(hours=h),
                title=title,
                importance=imp,  # type: ignore[arg-type]
            )
        )
    return out
