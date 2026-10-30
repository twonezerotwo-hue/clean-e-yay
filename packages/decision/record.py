"""Kalıcı karar kaydı (hedef mimari 4. aşama, st_record).

Her tick'in kararı ve son kapı rotası günlük, yalnız-ekleme dosyalara yazılır:
``data/runtime/decision_record/YYYY-MM-DD.jsonl``. Snapshot deposu birkaç saat
sonra budanır ve açılmayan adayların son kapı sonucu hiçbir yerde kalmıyordu.

Boyut küçük tutulur: her turda yalnız önceki tura göre DEĞİŞEN hücreler yazılır
("delta"); saatte bir ve süreç başlangıcında tüm hücreler yazılır ("checkpoint").
Her checkpoint ve sürüm değişikliği sürüm bilgisini (kod commit'i, eşik ve ağırlık
dosyası özeti, karar bayrakları) taşır. Karar mantığına dokunmaz; yazılamazsa
tick sürer (çağıran yakalar).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_CHECKPOINT_EVERY = timedelta(hours=1)
# Karar yolunu değiştirebilen bayraklar; değerleri kayıtta sürüm bilgisidir.
_DECISION_FLAGS = (
    "E_YAY_CANONICAL_RUNTIME", "EYAY_MACRO_MATRIX_ENABLED", "EYAY_HOLIDAY_TABLE_ENABLED",
    "LEARNING_ADVISOR_APPLY", "TF_SCORING_V2_SHADOW", "LEARNING_AUDIT_LEDGER_ONLY",
)
_LOCK = threading.Lock()
_STATE: dict[str, Any] = {"cells": {}, "checkpoint_at": None, "versions": None, "pruned_day": None}


def _dir() -> Path:
    return Path(os.environ.get("DECISION_RECORD_DIR", "data/runtime/decision_record"))


def _retention_days() -> int:
    try:
        return max(1, int(os.environ.get("DECISION_RECORD_RETENTION_DAYS", "30")))
    except ValueError:
        return 30


def _digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except OSError:
        return None


def _git_commit() -> str | None:
    head = _REPO / ".git" / "HEAD"
    try:
        ref = head.read_text(encoding="utf-8").strip()
        if not ref.startswith("ref: "):
            return ref[:12]
        name = ref[5:]
        ref_file = _REPO / ".git" / name
        if ref_file.exists():
            return ref_file.read_text(encoding="utf-8").strip()[:12]
        for line in (_REPO / ".git" / "packed-refs").read_text(encoding="utf-8").splitlines():
            if line.endswith(" " + name):
                return line.split(" ", 1)[0][:12]
    except OSError:
        return None
    return None


def versions() -> dict[str, Any]:
    weights = Path(os.environ.get("WEIGHTS_MANIFEST_PATH") or "data/runtime/weights_active.json")
    return {
        "commit": _git_commit(),
        "thresholds": _digest(_REPO / "config" / "thresholds_v1.0.yaml"),
        "weights": _digest(weights),
        "flags": {name: os.environ.get(name) for name in _DECISION_FLAGS if os.environ.get(name) is not None},
    }


def _cell(decision: Any, gate: Any) -> dict[str, Any]:
    consensus = getattr(decision, "consensus", None)
    ev = getattr(decision, "expected_value", None)
    return {
        "symbol": decision.symbol,
        "timeframe": decision.timeframe,
        "action": decision.action,
        "candidate": getattr(decision, "candidate_action", None),
        "direction": getattr(consensus, "direction", None),
        "score": getattr(decision, "consensus_score", None),
        "confidence": round(float(getattr(decision, "confidence", 0.0) or 0.0), 3),
        "ev": round(float(ev), 3) if ev is not None else None,
        "blocked_by": list(getattr(decision, "blocked_by", None) or ()),
        "route": getattr(gate, "route", None),
        "gate_blocker": getattr(gate, "blocker", None),
        "size_multiplier": round(float(getattr(gate, "size_multiplier", 0.0) or 0.0), 3) if gate is not None else None,
        "decision_id": getattr(decision, "decision_id", None),
    }


def _key(cell: dict[str, Any]) -> tuple:
    # Skorun küçük oynaması satır üretmez; karar, rota ya da engel değişince yazılır.
    return (cell["action"], cell["candidate"], cell["direction"], tuple(cell["blocked_by"]),
            cell["route"], cell["gate_blocker"])


def _prune(folder: Path, today: datetime) -> None:
    cutoff = (today - timedelta(days=_retention_days())).date().isoformat()
    for path in folder.glob("????-??-??.jsonl"):
        if path.stem < cutoff:
            path.unlink(missing_ok=True)


def append(snap: Any, decisions: list[Any], final_results: dict[tuple[str, str], Any], *,
           now: datetime | None = None, risk_action: str | None = None) -> dict[str, Any]:
    """Bu turun kararlarını kayda ekler; ne yazıldığını döner."""
    now = now or datetime.now(UTC)
    cells = [_cell(d, final_results.get((d.symbol, d.timeframe))) for d in decisions]
    with _LOCK:
        current_versions = versions()
        checkpoint = (_STATE["checkpoint_at"] is None or now - _STATE["checkpoint_at"] >= _CHECKPOINT_EVERY
                      or current_versions != _STATE["versions"])
        previous = _STATE["cells"]
        changed = cells if checkpoint else [c for c in cells if previous.get((c["symbol"], c["timeframe"])) != _key(c)]
        _STATE["cells"] = {(c["symbol"], c["timeframe"]): _key(c) for c in cells}
        if not changed:
            return {"kind": "none", "cells": 0}
        row: dict[str, Any] = {
            "ts": now.isoformat(),
            "kind": "checkpoint" if checkpoint else "delta",
            "snapshot_id": getattr(snap, "snapshot_id", None),
            "risk_action": risk_action,
            "dqs": getattr(getattr(snap, "quality", None), "status", None),
            "cells": changed,
        }
        if checkpoint:
            row["versions"] = current_versions
            _STATE["checkpoint_at"] = now
            _STATE["versions"] = current_versions
        folder = _dir()
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / f"{now.date().isoformat()}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        day = now.date().isoformat()
        if _STATE["pruned_day"] != day:
            _prune(folder, now)
            _STATE["pruned_day"] = day
    return {"kind": row["kind"], "cells": len(changed)}


def load_day(day: str) -> list[dict[str, Any]]:
    """Bir günün kayıtları (eskiden yeniye); bozuk satır atlanır."""
    path = _dir() / f"{day}.jsonl"
    out: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        return []
    return out


def reset() -> None:
    with _LOCK:
        _STATE.update({"cells": {}, "checkpoint_at": None, "versions": None, "pruned_day": None})
