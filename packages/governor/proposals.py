"""Genel Öneri Defteri — her tipte owner-onaylı önerinin tek kaydı.

Desen `rebalance_store` / `mode/store` ile aynı: file-backed JSON, env path
override, thread-safe, atomik yazım (temp + replace), bozuk/eksik → boş default
(crash yok). `data/runtime/governor_proposals.json` içinde
`{"pending": [...], "history": [son 100]}` tutulur.

DEĞİŞMEZ GÜVENLİK SINIRI
------------------------
Bu defter bir DEFTERDİR, bir UYGULAYICI DEĞİLDİR. `approve()` yalnızca owner'ın
kararını kaydeder (status=APPROVED); canlı config'e (weights / thresholds /
risk_policy / agent_mode) HİÇBİR ŞEY YAZMAZ. Gerçek uygulama yalnızca mevcut
owner-gated yollardan yapılır:
  - WEIGHT_CHANGE   → packages/learning/rebalance_store.approve_current()
  - MODE_CHANGE     → packages/mode/store.save_overrides()
  - TF_TARGET_CHANGE→ packages/learning/tf_target_store.approve_pending()
Böylece RiskGate/weights değişiklikleri tek denetlenebilir kanaldan geçer ve bu
defter bir "arka kapı" hâline gelmez. THRESHOLD/RISK/DATA/STRATEGY önerileri için
henüz otomatik uygulama yolu yoktur — onlar yalnızca kayıt + owner kararı taşır.

PAPER_SAFE / NO_EXECUTION: paper state'e dokunmaz, trade açmaz/kapatmaz.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from packages.data.registry.loader import REPO_ROOT

ProposalStatus = Literal["PENDING", "APPROVED", "REJECTED"]

# Whitelist — bilinmeyen tip reddedilir (defter şeması korunur). Raporun §6
# proposal tipleriyle hizalı.
PROPOSAL_TYPES: tuple[str, ...] = (
    "WEIGHT_CHANGE",
    "MODE_CHANGE",
    "THRESHOLD_CHANGE",
    "RISK_POLICY_CHANGE",
    "DATA_PROVIDER_CHANGE",
    "TF_TARGET_CHANGE",
    "STRATEGY_ENABLE",
    "STRATEGY_DISABLE",
    "DASHBOARD_ALERT",
)

_HISTORY_CAP = 100
_LOCK = threading.Lock()


def _store_path() -> Path:
    p = Path(
        os.environ.get("GOVERNOR_PROPOSALS_PATH", "data/runtime/governor_proposals.json")
    )
    return p if p.is_absolute() else REPO_ROOT / p


def _empty() -> dict:
    return {"pending": [], "history": []}


def load() -> dict:
    """Tüm defter ({pending, history}). Bozuk/eksik → boş default."""
    path = _store_path()
    with _LOCK:
        if not path.exists():
            return _empty()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _empty()
    if not isinstance(data, dict):
        return _empty()
    data.setdefault("pending", [])
    data.setdefault("history", [])
    if not isinstance(data["pending"], list):
        data["pending"] = []
    if not isinstance(data["history"], list):
        data["history"] = []
    return data


def _save(data: dict) -> None:
    path = _store_path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(path)


def _safe_dict(value: Any) -> dict:
    """JSON-serileştirilebilir dict'e indir; değilse boş dict (uydurma yapmaz)."""
    if not isinstance(value, dict):
        return {}
    try:
        json.dumps(value)
        return dict(value)
    except (TypeError, ValueError):
        return {}


def sanitize(payload: dict) -> dict | None:
    """Gelen öneriyi güvenli kayda indir. Geçersiz tip → None (reddedilir).

    Yalnızca bilinen alanlar tutulur; evidence/requested_change JSON-safe dict'e
    indirgenir. id/created_at/status burada ATANMAZ (submit ekler)."""
    if not isinstance(payload, dict):
        return None
    ptype = payload.get("proposal_type")
    if ptype not in PROPOSAL_TYPES:
        return None
    title = str(payload.get("title") or "").strip()
    if not title:
        return None
    return {
        "proposal_type": ptype,
        "title": title[:200],
        "summary": str(payload.get("summary") or "").strip()[:1000],
        "evidence": _safe_dict(payload.get("evidence")),
        "requested_change": _safe_dict(payload.get("requested_change")),
        "rollback_plan": str(payload.get("rollback_plan") or "").strip()[:500],
        "source": str(payload.get("source") or "governor").strip()[:50],
        # Her kritik değişiklik owner onayı ister (varsayılan True). Yalnızca
        # DASHBOARD_ALERT açıkça False geçebilir (kanıt/uyarı, config değişmez).
        "requires_owner_approval": bool(payload.get("requires_owner_approval", True)),
    }


def _dedup_key(p: dict) -> tuple:
    return (
        p.get("proposal_type"),
        json.dumps(p.get("requested_change") or {}, sort_keys=True),
    )


def submit(payload: dict) -> dict | None:
    """Yeni öneri kaydet (status=PENDING). Geçersiz → None.

    Aynı (tip, requested_change) ile PENDING bir öneri zaten varsa yenisini
    EKLEMEZ; var olanı döner (gürültü/çift kayıt önlenir)."""
    clean = sanitize(payload)
    if clean is None:
        return None
    data = load()
    key = _dedup_key(clean)
    for existing in data["pending"]:
        if _dedup_key(existing) == key:
            return existing
    proposal = {
        "proposal_id": uuid.uuid4().hex[:12],
        "status": "PENDING",
        "created_at": datetime.now(UTC).isoformat(),
        **clean,
    }
    data["pending"].append(proposal)
    _save(data)
    return proposal


def list_pending() -> list[dict]:
    return list(load().get("pending", []))


def get(proposal_id: str) -> dict | None:
    data = load()
    for p in data["pending"]:
        if p.get("proposal_id") == proposal_id:
            return p
    for p in data["history"]:
        if p.get("proposal_id") == proposal_id:
            return p
    return None


def _decide(proposal_id: str, status: ProposalStatus, **extra) -> dict | None:
    """PENDING öneriyi karara bağla (history'e taşı). Bulunamazsa None.

    NOT: canlı config'e DOKUNMAZ — yalnızca defter kaydını günceller (bkz. modül
    docstring'i). Uygulama owner-gated yolların sorumluluğundadır."""
    data = load()
    idx = next(
        (i for i, p in enumerate(data["pending"]) if p.get("proposal_id") == proposal_id),
        None,
    )
    if idx is None:
        return None
    p = dict(data["pending"].pop(idx))
    p.update(status=status, decided_at=datetime.now(UTC).isoformat(), **extra)
    data["history"] = [p, *data["history"]][:_HISTORY_CAP]
    _save(data)
    return p


def approve(proposal_id: str, approved_by: str = "owner") -> dict | None:
    """Owner kararını kaydet (APPROVED). Canlı config DEĞİŞMEZ — uygulama mevcut
    owner-gated yoldan yapılır (modül docstring'i)."""
    return _decide(proposal_id, "APPROVED", approved_by=approved_by)


def reject(proposal_id: str, reason: str = "owner_reject") -> dict | None:
    return _decide(proposal_id, "REJECTED", reject_reason=reason)


def clear() -> None:
    """Defteri sıfırla (test/owner reset için)."""
    path = _store_path()
    with _LOCK:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def summary_viewmodel(limit: int = 20) -> dict:
    """Dashboard için read-only özet: bekleyen + son geçmiş + sayaçlar."""
    data = load()
    pending = data.get("pending", [])
    history = data.get("history", [])
    by_type: dict[str, int] = {}
    for p in pending:
        t = p.get("proposal_type", "UNKNOWN")
        by_type[t] = by_type.get(t, 0) + 1
    return {
        "proposal_types": list(PROPOSAL_TYPES),
        "pending": list(pending),
        "pending_count": len(pending),
        "pending_by_type": by_type,
        "history": history[:limit],
        "note": (
            "Öneri defteri yalnızca kayıt tutar; onay canlı config'i otomatik "
            "değiştirmez (owner-gated uygulama ayrıdır)."
        ),
    }


__all__ = [
    "PROPOSAL_TYPES",
    "approve",
    "clear",
    "get",
    "list_pending",
    "load",
    "reject",
    "sanitize",
    "submit",
    "summary_viewmodel",
]
