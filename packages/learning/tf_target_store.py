"""TF-target override store — file-backed, hibrit auto-apply gate.

Trainer ürettiği `TfTargetProposal`'ı bu modül kalıcılaştırır. Politika
`auto_weight_trainer` + `rebalance_store` desenine paralel ama **hibrit**:

- Yeni değer mevcut değerin ±AUTO_APPLY_BAND_PCT (%15) bandındaysa →
  status=AUTO_APPLIED, doğrudan store'a yazılır. Mutlak guardrail kıstırılır.
- Band dışındaysa → status=PENDING; owner `approve_current()` ile onaylar.

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

# Hibrit kapı — bu eşiğin altındaki nudge'lar otomatik uygulanır.
AUTO_APPLY_BAND_PCT = 0.15

# Mutlak guardrail bantları (öğrenme hiç bunların dışına çıkamaz). Bu sınırlar
# `compute_tf_targets`'ın config defaults'unun da uzaktan üstü — yani kötü bir
# proposal AUTO_APPLIED olsa bile bu clamp güvenlik bandı.
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

ProposalStatus = Literal["PENDING", "APPROVED", "REJECTED", "AUTO_APPLIED", "SUPERSEDED"]

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
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


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


def _within_auto_band(old: float, new: float, band: float = AUTO_APPLY_BAND_PCT) -> bool:
    """new değeri |Δ/old| ≤ band → otomatik uygulanabilir."""
    if old <= 0:
        return False  # mevcut yok → otomatik uygulama (ilk öneri owner onayına)
    return abs(new - old) / old <= band


def submit_proposal(
    proposal: dict,
    *,
    current_baseline: dict[str, dict[str, float]],
    auto_apply_allowed: bool = True,
) -> dict:
    """Trainer'dan gelen proposal'ı işle: TF başına AUTO_APPLY veya PENDING.

    `proposal` formatı:
        {
            "generated_at": iso,
            "audit_note": str,
            "per_timeframe": {"15m": {"sl_atr_mult": ..., "rr": ..., ...}, ...},
            "dataset_size": int,
            "evidence": [...],  # opsiyonel
        }

    `current_baseline`: o anki aktif değerler (config + mevcut store override).

    `auto_apply_allowed` (CP4 slice 2 — edge-gate): False ise band-içi nudge'lar bile
    AUTO_APPLIED edilmez, PENDING'e yönlendirilir (owner yine onaylayabilir). Worker
    bunu `edge_report.safe_to_autotune` + `TF_TARGET_EDGE_GATE` flag'inden hesaplar.
    Default True → eski davranış birebir (bayt-aynı; flag OFF iken gate yok).

    Dönüş: aynı proposal + her TF için "decision" ("auto_applied" | "pending" |
    "gated_pending") + `applied_changes` (auto uygulanan TF'lerin önceki→yeni değeri,
    rollback baseline'ı için).
    """
    data = load()
    current = dict(data.get("current") or {})
    decisions: dict[str, str] = {}
    pending_changes: dict[str, dict[str, float]] = {}
    applied_changes: dict[str, dict[str, float]] = {}  # rollback için prev snapshot

    for tf, new_params in (proposal.get("per_timeframe") or {}).items():
        baseline = current_baseline.get(tf) or {}
        # Tüm parametreler band içinde mi?
        all_within = True
        for key, new_val in new_params.items():
            old_val = float(baseline.get(key, 0.0) or 0.0)
            if not _within_auto_band(old_val, float(new_val)):
                all_within = False
                break

        clamped, clamp_notes = _clamp_guardrails(new_params)
        if all_within and auto_apply_allowed:
            applied_changes[tf] = dict(current.get(tf) or baseline)  # önceki değer
            current[tf] = clamped
            decisions[tf] = "auto_applied"
            if clamp_notes:
                decisions[tf] += f" ({'; '.join(clamp_notes)})"
        else:
            pending_changes[tf] = clamped
            decisions[tf] = "gated_pending" if (all_within and not auto_apply_allowed) else "pending"
            if clamp_notes:
                decisions[tf] += f" ({'; '.join(clamp_notes)})"

    record = dict(proposal, status="MIXED", decisions=decisions,
                  pending_changes=pending_changes, applied_changes=applied_changes)
    # Önceki PENDING varsa SUPERSEDED olarak history'e taşı.
    history = list(data.get("history") or [])
    cur_pending = data.get("pending")
    if cur_pending:
        history = [dict(cur_pending, status="SUPERSEDED"), *history][:50]
    data = {
        "current": current,
        "pending": record if pending_changes else None,
        "history": [record, *history][:50],
    }
    _save(data)
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


def revert_overrides(prev: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """CP4 slice 2 rollback — auto-apply edilmiş TF override'larını önceki değerine
    döndür. `prev` = {tf: {param: eski_değer}} (submit_proposal'ın `applied_changes`'i).
    Boş prev dict olan TF → override'ı tamamen kaldır (config default'a düş).
    Sadece manifest-pointer değil, gerçek değer geri yazılır. Dönüş = yeni current."""
    data = load()
    current = dict(data.get("current") or {})
    for tf, params in (prev or {}).items():
        if params:
            current[tf] = dict(params)
        else:
            current.pop(tf, None)
    _save({"current": current, "pending": data.get("pending"),
           "history": list(data.get("history") or [])})
    return current


def reset() -> None:
    """Tüm override'ları sil (saf config'e dönüş)."""
    _save(_empty())


__all__ = [
    "AUTO_APPLY_BAND_PCT",
    "GUARDRAIL",
    "active_overrides",
    "approve_pending",
    "get_pending",
    "load",
    "reject_pending",
    "reset",
    "revert_overrides",
    "submit_proposal",
]
