"""G2 — Auto-weight trainer.

Politika:
- DATA_POLICY: sadece `data_verified=True` trade'ler dataset'e alınır.
  MOCK / DATA_UNAVAILABLE / verified=False kayıtları öğrenmeye girmez.
- Trainer öneri üretir — `RebalanceProposal`. Owner approval olmadan canlı
  ağırlık değişmez (rebalance_store.approve_current).

Algoritma:
1. `data_verified=True` kapalı trade'leri yükle.
2. Fingerprint string'inden `dominant_module` parçasını parse et.
3. Modül başına: count, wins, win_rate, avg_pnl, total_pnl.
4. Performans skoru: `win_rate * 100 + clamp(avg_pnl / equity_unit, -10, +10)`.
5. Mevcut weights'ten delta hesapla. Constraint'lere göre clip et
   (max_delta_per_module, max_total_drift, min_module_floor).
6. Versiyonu bump et (1.0 → 1.1 → 1.2 ...).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Literal

from packages.data.registry.loader import (
    active_weights_version,
    load_active_weights,
    load_thresholds,
)
from packages.paper import state as paper_state

MIN_TRADES_PER_MODULE = 3
MIN_TOTAL_TRADES = 10

NotEnoughDataReason = Literal[
    "no_verified_trades",
    "below_min_total",
    "no_module_meets_min",
]


@dataclass
class ModulePerf:
    module: str
    trades: int
    wins: int
    win_rate: float
    avg_pnl: float
    total_pnl: float
    score: float


@dataclass
class WeightDelta:
    module: str
    old: float
    new: float
    delta: float


@dataclass
class RebalanceProposal:
    from_version: str
    to_version: str
    generated_at: str
    regime: str
    deltas: list[WeightDelta]
    proposed_yaml: dict
    evidence: list[ModulePerf]
    audit_note: str
    dataset_size: int
    rejected_records: int = 0
    status: str = "PENDING"
    notes: list[str] = field(default_factory=list)


def _parse_dominant_module(fingerprint: str | None) -> str | None:
    if not fingerprint:
        return None
    parts = fingerprint.split("|")
    if len(parts) < 6:
        return None
    return parts[5] or None


def _bump_version(version: str) -> str:
    try:
        major, minor, *_rest = version.split(".")
        return f"{major}.{int(minor) + 1}.0"
    except (ValueError, IndexError):
        return "1.1.0"


def _module_score(win_rate: float, avg_pnl: float) -> float:
    pnl_unit = 1000.0
    pnl_term = max(-10.0, min(10.0, avg_pnl / pnl_unit))
    return round(win_rate * 100.0 + pnl_term, 3)


def _aggregate(trades) -> tuple[list[ModulePerf], int]:
    by_module: dict[str, list] = {}
    rejected = 0
    for t in trades:
        if not getattr(t, "data_verified", False):
            rejected += 1
            continue
        mod = _parse_dominant_module(t.fingerprint)
        if not mod:
            rejected += 1
            continue
        by_module.setdefault(mod, []).append(t)

    perfs: list[ModulePerf] = []
    for mod, items in by_module.items():
        n = len(items)
        if n < MIN_TRADES_PER_MODULE:
            continue
        wins = sum(1 for t in items if t.pnl_usd > 0)
        total_pnl = sum(t.pnl_usd for t in items)
        win_rate = wins / n
        avg_pnl = total_pnl / n
        perfs.append(
            ModulePerf(
                module=mod,
                trades=n,
                wins=wins,
                win_rate=round(win_rate, 3),
                avg_pnl=round(avg_pnl, 2),
                total_pnl=round(total_pnl, 2),
                score=_module_score(win_rate, avg_pnl),
            )
        )
    perfs.sort(key=lambda p: -p.score)
    return perfs, rejected


def _propose_for_regime(
    perfs: list[ModulePerf],
    regime: str,
    base_weights: dict,
    constraints: dict,
) -> tuple[dict, list[WeightDelta]]:
    """Bir rejim için yeni ağırlık önerisi.

    Yüksek skorlu modül +delta, düşük skorlu -delta alır. Constraint'lere
    göre clip + min floor + total drift kontrol edilir; sonunda normalize.
    """
    max_delta = float(constraints.get("max_delta_per_module", 0.03))
    max_total_drift = float(constraints.get("max_total_drift", 0.10))
    floor = float(constraints.get("min_module_floor", 0.02))

    if not perfs:
        return dict(base_weights), []

    avg_score = sum(p.score for p in perfs) / len(perfs)
    raw_delta: dict[str, float] = {}
    for p in perfs:
        diff = (p.score - avg_score) / 100.0
        d = max(-max_delta, min(max_delta, round(diff * max_delta, 4)))
        raw_delta[p.module] = d

    # Total drift sınırı:
    total_abs = sum(abs(d) for d in raw_delta.values())
    if total_abs > max_total_drift and total_abs > 0:
        scale = max_total_drift / total_abs
        raw_delta = {k: round(v * scale, 4) for k, v in raw_delta.items()}

    new_weights = dict(base_weights)
    for mod, d in raw_delta.items():
        if mod in new_weights:
            new_weights[mod] = max(floor, round(new_weights[mod] + d, 4))

    # Tüm modülleri toplam 1.0'a normalize et.
    total = sum(new_weights.values()) or 1.0
    new_weights = {k: round(v / total, 4) for k, v in new_weights.items()}

    deltas = [
        WeightDelta(
            module=mod,
            old=round(base_weights[mod], 4),
            new=new_weights[mod],
            delta=round(new_weights[mod] - base_weights[mod], 4),
        )
        for mod in base_weights
    ]
    return new_weights, deltas


def train(regime: str = "NEUTRAL") -> RebalanceProposal | dict:
    """Trainer ana giriş. Yeterli veri yoksa açıklayıcı dict döner."""
    s = paper_state.load()
    trades = list(s.recent_trades)

    perfs, rejected = _aggregate(trades)
    eligible = sum(1 for t in trades if getattr(t, "data_verified", False))
    total = len(trades)

    if eligible == 0:
        return {
            "status": "INSUFFICIENT",
            "reason": "no_verified_trades",
            "dataset_size": 0,
            "rejected_records": total,
        }
    if eligible < MIN_TOTAL_TRADES:
        return {
            "status": "INSUFFICIENT",
            "reason": "below_min_total",
            "dataset_size": eligible,
            "rejected_records": rejected,
            "min_required": MIN_TOTAL_TRADES,
        }
    if not perfs:
        return {
            "status": "INSUFFICIENT",
            "reason": "no_module_meets_min",
            "dataset_size": eligible,
            "rejected_records": rejected,
            "min_per_module": MIN_TRADES_PER_MODULE,
        }

    weights_cfg = load_active_weights()
    constraints = weights_cfg.get("constraints", {})
    base = dict(weights_cfg["regimes"].get(regime, weights_cfg["regimes"]["NEUTRAL"]))
    new_w, deltas = _propose_for_regime(perfs, regime, base, constraints)

    from_version = active_weights_version()
    to_version = _bump_version(from_version)

    new_regimes = dict(weights_cfg["regimes"])
    new_regimes[regime] = new_w
    proposed_yaml = {
        "version": to_version,
        "created_at": datetime.now(UTC).date().isoformat(),
        "description": (
            f"Auto-weight trainer proposal from {from_version} "
            f"(regime={regime}, dataset={eligible})."
        ),
        "regimes": new_regimes,
        "constraints": dict(constraints),
        "audit": {
            "based_on_trades": eligible,
            "rejected_records": rejected,
            "module_performance": [asdict(p) for p in perfs],
        },
    }

    thresholds = load_thresholds().get("learning", {})
    notes = [
        f"min_trades_per_module={MIN_TRADES_PER_MODULE}",
        f"thresholds.learning={thresholds}",
    ]

    return RebalanceProposal(
        from_version=from_version,
        to_version=to_version,
        generated_at=datetime.now(UTC).isoformat(),
        regime=regime,
        deltas=deltas,
        proposed_yaml=proposed_yaml,
        evidence=perfs,
        audit_note=(
            f"{eligible} verified trade üzerinden öğrenildi. "
            f"{rejected} verified=false/missing-fingerprint kayıt atlandı."
        ),
        dataset_size=eligible,
        rejected_records=rejected,
        notes=notes,
    )


def proposal_to_dict(p: RebalanceProposal) -> dict:
    return {
        "status": p.status,
        "from_version": p.from_version,
        "to_version": p.to_version,
        "generated_at": p.generated_at,
        "regime": p.regime,
        "deltas": [asdict(d) for d in p.deltas],
        "evidence": [asdict(e) for e in p.evidence],
        "proposed_yaml": p.proposed_yaml,
        "audit_note": p.audit_note,
        "dataset_size": p.dataset_size,
        "rejected_records": p.rejected_records,
        "notes": list(p.notes),
    }
