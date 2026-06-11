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
    REPO_ROOT,
    weights_manifest_path,
)

ProposalStatus = Literal["PENDING", "APPROVED", "REJECTED"]

_LOCK = threading.Lock()


def _store_path() -> Path:
    p = Path(os.environ.get("REBALANCE_STORE_PATH", "data/runtime/rebalance.json"))
    return p if p.is_absolute() else REPO_ROOT / p


def _weights_output_dir() -> Path:
    """Yeni weights yaml dosyalarının yazıldığı dizin. Test override için
    `WEIGHTS_OUTPUT_DIR` env değişkeni kullanılır; default config/."""
    p = os.environ.get("WEIGHTS_OUTPUT_DIR")
    if p:
        path = Path(p)
        return path if path.is_absolute() else REPO_ROOT / path
    return CONFIG_DIR


def _resolve(p: Path) -> Path:
    return p if p.is_absolute() else REPO_ROOT / p


def _empty() -> dict:
    return {"current": None, "history": []}


def load() -> dict:
    path = _store_path()
    with _LOCK:
        if not path.exists():
            return _empty()
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _empty()


def _save(data: dict) -> None:
    path = _store_path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_pending() -> dict | None:
    cur = load().get("current")
    if cur and cur.get("status") == "PENDING":
        return cur
    return None


def set_pending(proposal: dict) -> dict:
    """Yeni proposal yaz; eski PENDING varsa history'e taşı (SUPERSEDED)."""
    data = load()
    cur = data.get("current")
    if cur and cur.get("status") == "PENDING":
        cur = dict(cur, status="REJECTED", reject_reason="superseded")
        data["history"] = [cur, *data.get("history", [])][:50]
    proposal = dict(proposal, status="PENDING")
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


def approve_current(approved_by: str = "owner") -> dict | None:
    """Approve: yeni weights yaml + manifest yaz; trainer'ın önerdiği weights
    dosyaya gider, consensus bu manifest üzerinden okur."""
    pending = get_pending()
    if pending is None:
        return None
    new_yaml_payload = pending["proposed_yaml"]
    new_version = pending["to_version"]
    yaml_filename = f"weights_v{new_version}.yaml"
    yaml_path = _weights_output_dir() / yaml_filename
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(
        yaml.safe_dump(new_yaml_payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    try:
        yaml_path_str = str(yaml_path.relative_to(REPO_ROOT))
    except ValueError:
        yaml_path_str = str(yaml_path)
    manifest = weights_manifest_path()
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "version": new_version,
                "yaml_path": yaml_path_str,
                "approved_by": approved_by,
                "approved_at": pending.get("generated_at"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return _archive(
        "APPROVED",
        approved_by=approved_by,
        active_yaml=yaml_path_str,
    )


def history(limit: int = 20) -> list[dict]:
    return load().get("history", [])[:limit]
