"""Rebalance proposal storage — file-backed, JSON.

Politika:
- Owner approval olmadan active weights değişmez.
- Proposal `data/runtime/rebalance.json` içinde tutulur:
  `current` (PENDING/APPROVED/REJECTED) + `history` (en son 50).
- Approve aksiyonu yeni weights yaml yazar ve manifest'i (`weights_active.json`)
  güncelleyerek consensus'a aktarır.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Literal

import yaml

from packages.data.registry.loader import (
    CONFIG_DIR,
    GIT_WEIGHTS_MANIFEST,
    REPO_ROOT,
    WEIGHTS_RUNTIME_DIR,
    weights_manifest_path,
)
from packages.ops.store import write_text_atomic

ProposalStatus = Literal["PENDING", "APPROVED", "REJECTED"]

_LOCK = threading.Lock()
_MIN_EFFECTIVE_DELTA = 0.0001

def _store_path() -> Path:
    p = Path(os.environ.get("REBALANCE_STORE_PATH", "data/runtime/rebalance.json"))
    return p if p.is_absolute() else REPO_ROOT / p


def _weights_output_dir() -> Path:
    """Yeni weights yaml dosyalarının yazıldığı dizin. Test override için
    `WEIGHTS_OUTPUT_DIR` env değişkeni kullanılır; default data/runtime/weights/
    (F5-4 — makine üretimi config/'i kirletmesin, gitignore'lu kalsın). Eski
    config/ altındaki dosyalar loader'ın çift-yol fallback'iyle okunmaya devam
    eder."""
    p = os.environ.get("WEIGHTS_OUTPUT_DIR")
    if p:
        path = Path(p)
        return path if path.is_absolute() else REPO_ROOT / path
    # K5 — git manifest kullanılıyorsa onaylanan yaml da git'e (config/) yazılır;
    # owner onayı lokalde yapılır, config/ değişikliği PR ile AWS'e gider.
    if not os.environ.get("WEIGHTS_MANIFEST_PATH") and GIT_WEIGHTS_MANIFEST.exists():
        return CONFIG_DIR
    return WEIGHTS_RUNTIME_DIR


def _resolve(p: Path) -> Path:
    return p if p.is_absolute() else REPO_ROOT / p


def _empty() -> dict:
    return {"current": None, "history": []}


def has_effective_delta(proposal: dict | None) -> bool:
    if not isinstance(proposal, dict):
        return False
    deltas = proposal.get("deltas")
    if not isinstance(deltas, list):
        return False
    for d in deltas:
        if (
            isinstance(d, dict)
            and abs(float(d.get("delta") or 0.0)) >= _MIN_EFFECTIVE_DELTA
        ):
            return True
    return False


def _proposal_signature(proposal: dict) -> tuple:
    deltas = proposal.get("deltas") if isinstance(proposal.get("deltas"), list) else []
    compact_deltas = tuple(
        sorted(
            (
                str(d.get("module")),
                round(float(d.get("old") or 0.0), 6),
                round(float(d.get("new") or 0.0), 6),
                round(float(d.get("delta") or 0.0), 6),
            )
            for d in deltas
            if isinstance(d, dict)
        )
    )
    return (
        str(proposal.get("from_version") or ""),
        str(proposal.get("to_version") or ""),
        str(proposal.get("regime") or ""),
        compact_deltas,
    )


def load() -> dict:
    path = _store_path()
    with _LOCK:
        if not path.exists():
            return _empty()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _empty()
    # Bozuk/şekilsiz içerik (örn. dosya bir liste) → boş şema; `.get` patlamasın.
    if not isinstance(data, dict):
        return _empty()
    data.setdefault("current", None)
    if not isinstance(data.get("history"), list):
        data["history"] = []
    return data


def _save(data: dict) -> None:
    path = _store_path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomik yazım: tmp'e yaz + replace — yarım/bozuk JSON bırakmaz.
        write_text_atomic(path, json.dumps(data, indent=2))


def get_pending() -> dict | None:
    cur = load().get("current")
    if cur and cur.get("status") == "PENDING" and has_effective_delta(cur):
        return cur
    return None


def set_pending(proposal: dict) -> dict:
    """Yeni proposal yaz; eski PENDING varsa history'e taşı (SUPERSEDED)."""
    proposal = dict(proposal, status="PENDING")
    if not has_effective_delta(proposal):
        return dict(proposal, status="NO_CHANGE")
    data = load()
    cur = data.get("current")
    if (
        cur
        and cur.get("status") == "PENDING"
        and _proposal_signature(cur) == _proposal_signature(proposal)
    ):
        return cur
    if cur and cur.get("status") == "PENDING":
        cur = dict(cur, status="REJECTED", reject_reason="superseded")
        data["history"] = [cur, *data.get("history", [])][:50]
    data["current"] = proposal
    _save(data)
    return proposal


def _archive(status: ProposalStatus, **extra) -> dict | None:
    data = load()
    cur = data.get("current")
    if not cur or cur.get("status") != "PENDING":
        return None
    cur = dict(cur, status=status, **extra)
    data["current"] = cur
    data["history"] = [cur, *data.get("history", [])][:50]
    _save(data)
    return cur


def reject_current(reason: str = "owner_reject") -> dict | None:
    return _archive("REJECTED", reject_reason=reason)


def _read_manifest() -> dict | None:
    """Mevcut active weights manifest'i (yoksa None → baseline v1.0.0)."""
    m = weights_manifest_path()
    if not m.exists():
        return None
    try:
        data = json.loads(m.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _apply_payload(
    proposed_yaml: dict, to_version: str, approved_by: str, approved_at: str | None
) -> str:
    """Yeni weights yaml + manifest yaz; consensus bu manifest üzerinden okur.

    Owner onayının (approve_current) uygulama yolu. Yazılan yaml'ın repo-göreli
    yolunu döner."""
    yaml_filename = f"weights_v{to_version}.yaml"
    yaml_path = _weights_output_dir() / yaml_filename
    write_text_atomic(yaml_path, yaml.safe_dump(proposed_yaml, sort_keys=False, allow_unicode=True))
    try:
        yaml_path_str = str(yaml_path.relative_to(REPO_ROOT))
    except ValueError:
        yaml_path_str = str(yaml_path)
    manifest = weights_manifest_path()
    write_text_atomic(manifest, json.dumps(
        {
            "version": to_version,
            "yaml_path": yaml_path_str,
            "approved_by": approved_by,
            "approved_at": approved_at,
        },
        indent=2,
    ))
    return yaml_path_str


def approve_current(approved_by: str = "owner") -> dict | None:
    """Approve: yeni weights yaml + manifest yaz; trainer'ın önerdiği weights
    dosyaya gider, consensus bu manifest üzerinden okur."""
    pending = get_pending()
    if pending is None:
        return None
    yaml_path_str = _apply_payload(
        pending["proposed_yaml"], pending["to_version"], approved_by, pending.get("generated_at")
    )
    return _archive(
        "APPROVED",
        approved_by=approved_by,
        active_yaml=yaml_path_str,
    )


def history(limit: int = 20) -> list[dict]:
    return load().get("history", [])[:limit]
