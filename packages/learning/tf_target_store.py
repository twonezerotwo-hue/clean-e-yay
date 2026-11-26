"""TF-target override store — file-backed, owner onaylı.

Trainer ürettiği `TfTargetProposal`'ı bu modül kalıcılaştırır: her öneri PENDING olur,
yalnız owner `approve_pending()` ile uygular. (26 Kasım 2026'ya dek ±%15 bant içi
öneriler TF_TARGET_EDGE_GATE açıkken kendiliğinden uygulanıyordu; yerelde 7 kez oldu.
Owner kararıyla kalktı; her ortam bugünkü override'ında dondu.)

`compute_tf_targets` config'i okurken bu store'u override olarak uygular:
    final = clamp_guardrails(base_config[tf] → store[tf])
Store boşsa davranış = saf config (bozulmama garantisi).

PAPER_SAFE: store sadece SL/TP geometri parametrelerini etkiler; size/blok
kararına dokunmaz. Mutlak sınır clamp her zaman zorlanır — kötü öneri bile
güvenlik bandının dışına çıkamaz.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Literal

from packages.data.registry.loader import REPO_ROOT
from packages.ops.store import write_text_atomic

# Mutlak guardrail bantları (öğrenme hiç bunların dışına çıkamaz). Bu sınırlar
# `compute_tf_targets`'ın config defaults'unun da uzaktan üstü — onaylanan kötü bir
# öneri bile bu güvenlik bandının dışına çıkamaz.
GUARDRAIL: dict[str, tuple[float, float]] = {
    "sl_atr_mult":  (0.5, 3.0),
    "rr":           (1.5, 5.0),   # 15m için trade_economics.min_rr (1.5) zemin
    "sl_pct_floor": (0.002, 0.030),
    "sl_pct_cap":   (0.010, 0.150),
    # CP4 slice 3 — trailing mesafesi çarpanı (tier.trail_distance × trail_mult).
    # 1.0 = nötr (bayt-aynı). EXIT_EARLY bulgusunda trainer ↑ önerir (trail gevşer,
    # kâr daha çok koşar). Mutlak band: yarısı–iki katı arası, gürültüye karşı.
    "trail_mult":   (0.5, 2.0),
}

ProposalStatus = Literal["PENDING", "APPROVED", "REJECTED", "SUPERSEDED"]

_LOCK = threading.Lock()


def _store_path() -> Path:
    p = Path(os.environ.get("TF_TARGET_STORE_PATH", "data/runtime/tf_targets.json"))
    return p if p.is_absolute() else REPO_ROOT / p


def _empty() -> dict:
    return {"current": {}, "history": []}


def load() -> dict:
    """Store dosyası → {current: {tf: {sl_atr_mult, rr, ...}}, history: [...]}.

    Bozuk dosya → boş (crash yok). `current` boşsa override yok → saf config.
    """
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
        write_text_atomic(path, json.dumps(data, indent=2))


def active_overrides() -> dict[str, dict[str, float]]:
    """`compute_tf_targets`'ın okuyacağı aktif override'lar (sadece APPLIED/AUTO).

    `current` bloğu doğrudan döndürülür — sadece içeride APPLIED bayrağı olan
    TF'ler tutulur (PENDING önerileri etkin değildir).
    """
    return dict(load().get("current") or {})


def _clamp_guardrails(params: dict[str, float]) -> tuple[dict[str, float], list[str]]:
    """Guardrail bantlarına kıstır; clamp notları döndür."""
    notes: list[str] = []
    out: dict[str, float] = {}
    for key, value in params.items():
        lo, hi = GUARDRAIL.get(key, (None, None))
        if lo is None:
            out[key] = float(value)
            continue
        v = float(value)
        clamped = max(lo, min(hi, v))
        out[key] = clamped
        if clamped != v:
            notes.append(f"{key}={v} → clamped to [{lo},{hi}]={clamped}")
    return out, notes


def submit_proposal(proposal: dict) -> dict:
    """Trainer'dan gelen öneriyi PENDING olarak kaydet (guardrail'e kıstırılmış).

    `proposal` formatı: {"generated_at", "audit_note", "per_timeframe": {tf: {...}},
    "dataset_size", ...}. Dönüş: aynı öneri + her TF için "decision" ("pending").
    Canlı değer (current) değişmez; owner `approve_pending()` ile uygular."""
    data = load()
    decisions: dict[str, str] = {}
    pending_changes: dict[str, dict[str, float]] = {}
    for tf, new_params in (proposal.get("per_timeframe") or {}).items():
        clamped, clamp_notes = _clamp_guardrails(new_params)
        pending_changes[tf] = clamped
        decisions[tf] = "pending" + (f" ({'; '.join(clamp_notes)})" if clamp_notes else "")
    record = dict(proposal, status="PENDING", decisions=decisions, pending_changes=pending_changes)
    history = list(data.get("history") or [])
    cur_pending = data.get("pending")
    if cur_pending:
        history = [dict(cur_pending, status="SUPERSEDED"), *history][:50]
    _save({
        "current": dict(data.get("current") or {}),
        "pending": record if pending_changes else None,
        "history": [record, *history][:50],
    })
    return record


def get_pending() -> dict | None:
    return load().get("pending")


def approve_pending(approved_by: str = "owner") -> dict | None:
    """Bekleyen PENDING değişiklikleri current'a uygula."""
    data = load()
    pending = data.get("pending")
    if not pending:
        return None
    current = dict(data.get("current") or {})
    for tf, params in (pending.get("pending_changes") or {}).items():
        clamped, _ = _clamp_guardrails(params)
        current[tf] = clamped
    approved = dict(pending, status="APPROVED", approved_by=approved_by)
    history = [approved, *list(data.get("history") or [])][:50]
    _save({"current": current, "pending": None, "history": history})
    return approved


def reject_pending(reason: str = "owner_reject") -> dict | None:
    data = load()
    pending = data.get("pending")
    if not pending:
        return None
    rejected = dict(pending, status="REJECTED", reject_reason=reason)
    history = [rejected, *list(data.get("history") or [])][:50]
    _save({"current": data.get("current") or {}, "pending": None, "history": history})
    return rejected


def history(limit: int = 10) -> list[dict]:
    """Öneri/onay geçmişi (en yeni önce)."""
    return list(load().get("history") or [])[:limit]


def reset() -> None:
    """Tüm override'ları sil (saf config'e dönüş)."""
    _save(_empty())


__all__ = [
    "GUARDRAIL",
    "active_overrides",
    "approve_pending",
    "get_pending",
    "history",
    "load",
    "reject_pending",
    "reset",
    "submit_proposal",
]
