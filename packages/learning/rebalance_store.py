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
from packages.learning import weight_autoapply_store

ProposalStatus = Literal["PENDING", "APPROVED", "REJECTED"]

_LOCK = threading.Lock()
_MIN_EFFECTIVE_DELTA = 0.0001

# G3 — otonom (worker) yolunda dar-bant otomatik uygulama. API propose/approve
# endpoint'leri ETKİLENMEZ (owner-kapısı orada aynen durur). Ana anahtar default
# AÇIK; `REBALANCE_AUTO_APPLY=0` ile kapatılır (kapalıyken davranış set_pending'e
# düşer — bugünkü saf owner akışı). Bant: bir modülün ağırlığı tek seferde en fazla
# ±REBALANCE_AUTO_APPLY_BAND (default 0.05) oynayabilir; bir delta bile bant dışı →
# PENDING (owner). Bkz. [[weight_autoapply_store]] + [[weight_rollback]].
_AUTO_APPLY_BAND_DEFAULT = 0.05
_AUTO_APPLY_OFF = {"0", "false", "no", "off", ""}


def _auto_apply_enabled() -> bool:
    return os.environ.get("REBALANCE_AUTO_APPLY", "1").strip().lower() not in _AUTO_APPLY_OFF


def _max_abs_delta() -> float:
    try:
        return float(os.environ.get("REBALANCE_AUTO_APPLY_BAND", _AUTO_APPLY_BAND_DEFAULT))
    except (TypeError, ValueError):
        return _AUTO_APPLY_BAND_DEFAULT


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

    approve_current (owner) ve maybe_auto_apply (otonom) ORTAK uygulama yolu —
    tek kaynak. Yazılan yaml'ın repo-göreli yolunu döner."""
    yaml_filename = f"weights_v{to_version}.yaml"
    yaml_path = _weights_output_dir() / yaml_filename
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(
        yaml.safe_dump(proposed_yaml, sort_keys=False, allow_unicode=True),
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
                "version": to_version,
                "yaml_path": yaml_path_str,
                "approved_by": approved_by,
                "approved_at": approved_at,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
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


def revert_to_manifest(prev_manifest: dict | None) -> None:
    """Rollback: manifest'i önceki haline döndür. `prev_manifest` None ise manifest
    silinir (active weights baseline v1.0.0'a düşer). Yalnız manifest pointer'ı
    değişir — yazılmış weights_vX.yaml dosyaları olduğu gibi kalır (zararsız)."""
    m = weights_manifest_path()
    m.parent.mkdir(parents=True, exist_ok=True)
    if prev_manifest is None:
        try:
            m.unlink(missing_ok=True)
        except OSError:
            pass
        return
    m.write_text(json.dumps(prev_manifest, indent=2), encoding="utf-8")


def _all_deltas_within_band(proposal: dict, band: float) -> bool:
    """Proposal'daki TÜM modül delta'ları |delta| ≤ band ise True (boş → False)."""
    deltas = proposal.get("deltas") if isinstance(proposal.get("deltas"), list) else []
    valid = [d for d in deltas if isinstance(d, dict)]
    if not valid:
        return False
    return all(abs(float(d.get("delta") or 0.0)) <= band for d in valid)


def maybe_auto_apply(
    proposal: dict, *, baseline_expectancy: float, baseline_n: int
) -> dict:
    """G3 — otonom yol: proposal dar bantta ve auto-apply açıksa OTOMATİK uygula;
    aksi halde PENDING (owner). Dönen dict bir `decision` taşır:

      auto_applied | pending_out_of_band | pending_monitoring | pending_disabled |
      no_change

    Aynı anda yalnız tek izlenen değişiklik: aktif bir auto-apply izleniyorsa
    (henüz CONFIRMED/ROLLED_BACK değil) yeni proposal PENDING'e yönlendirilir."""
    proposal = dict(proposal, status="PENDING")
    if not has_effective_delta(proposal):
        return dict(proposal, status="NO_CHANGE", decision="no_change")
    if not _auto_apply_enabled():
        set_pending(proposal)
        return dict(proposal, decision="pending_disabled")
    if weight_autoapply_store.get_active() is not None:
        set_pending(proposal)
        return dict(proposal, decision="pending_monitoring")
    if not _all_deltas_within_band(proposal, _max_abs_delta()):
        set_pending(proposal)
        return dict(proposal, decision="pending_out_of_band")

    # --- dar bant + açık + izleme yok → otomatik uygula ---
    prev_manifest = _read_manifest()
    prev_version = str((prev_manifest or {}).get("version", "1.0.0"))
    yaml_path_str = _apply_payload(
        proposal["proposed_yaml"], proposal["to_version"], "auto", proposal.get("generated_at")
    )
    weight_autoapply_store.record_apply(
        applied_version=str(proposal["to_version"]),
        prev_version=prev_version,
        prev_manifest=prev_manifest,
        baseline_expectancy=baseline_expectancy,
        baseline_n=baseline_n,
        regime=proposal.get("regime"),
        deltas=proposal.get("deltas"),
    )
    applied = dict(
        proposal, status="AUTO_APPLIED", approved_by="auto", active_yaml=yaml_path_str
    )
    data = load()
    data["current"] = applied
    data["history"] = [applied, *data.get("history", [])][:50]
    _save(data)
    return dict(applied, decision="auto_applied")


def history(limit: int = 20) -> list[dict]:
    return load().get("history", [])[:limit]
