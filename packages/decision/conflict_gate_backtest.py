"""Faz 9A — Conflict Gate retrospektif doğrulama (read-only rapor, karara bağlı DEĞİL).

Gerçekleşmiş paper trade'leri (`outcomes.py::CanonicalOutcome`, zaten var olan
kapanmış trade kayıtları) ile, aynı (snapshot_id, symbol) için zaten yazılmış
shadow gözlem kaydındaki (`data/runtime/shadow_decisions.jsonl::setup_conflict`)
Conflict Resolver verdict'ini eşleştirir.

Soru: "bu trade açıldığı anda Conflict Gate aktif olsaydı route'u ne olurdu,
ve o route'un gerçek win-rate'i neydi" — yani gate'in bloke/küçülttüğü
işlemlerin gerçekte kötü mü iyi mi çıktığını ölçer. Hiçbir karar zincirine
(decide_for_symbol/decide_matrix/agent_pipeline/conflict_gate.evaluate'in
CANLI çağrısı) bağlı DEĞİLDİR — yalnızca zaten var olan iki read-only veri
kaynağını (outcomes_from_state, shadow_decisions.jsonl) okur. Yeni veri
üretmez, hiçbir state'i mutate etmez.

PAPER_SAFE / NO_EXECUTION: salt okunur rapor.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from packages.decision import conflict_gate
from packages.learning.outcomes import CanonicalOutcome, outcomes_from_state
from packages.mode import profile_selector

DEFAULT_SHADOW_PATH = Path("data/runtime/shadow_decisions.jsonl")


def _load_setup_conflict_index(path: Path) -> dict[tuple[str, str], dict]:
    """(snapshot_id, symbol) -> setup_conflict dict. Bozuk/eksik satırlar atlanır."""
    index: dict[tuple[str, str], dict] = {}
    if not path.exists():
        return index
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            snap_id = rec.get("snapshot_id")
            if not snap_id:
                continue
            for row in rec.get("symbols") or []:
                sym = row.get("symbol")
                sc = row.get("setup_conflict")
                if sym and sc:
                    index[(snap_id, sym)] = sc
    return index


def _route_bucket(result: conflict_gate.GateResult) -> str:
    if result.route == "open" and result.effective_multiplier < 1.0:
        return "open_reduced"
    return result.route


def validation_report(
    *,
    outcomes: list[CanonicalOutcome] | None = None,
    shadow_path: Path | None = None,
    profile_modes: dict[str, str] | None = None,
) -> dict:
    """Her trade_profile için, gate (varsayımsal olarak hep aktif) route'unun
    gerçek win-rate/avg_pnl dağılımı. `_unmatched_no_shadow_data`: o trade'in
    açılış anında shadow gözlem kaydı yoktu (örn. Faz 6'dan önceki trade'ler).
    """
    rows = outcomes if outcomes is not None else outcomes_from_state()
    index = _load_setup_conflict_index(shadow_path or DEFAULT_SHADOW_PATH)
    base_modes = profile_modes or conflict_gate.load_config().profile_modes
    cfg = conflict_gate.ConflictGateConfig(enabled=True, profile_modes=dict(base_modes))

    buckets: dict[str, dict[str, list[CanonicalOutcome]]] = defaultdict(lambda: defaultdict(list))
    unmatched = 0

    for o in rows:
        sc = index.get((o.snapshot_id, o.symbol)) if o.snapshot_id else None
        if not sc:
            unmatched += 1
            continue
        setup_type = sc.get("setup_type") or "NO_TRADE"
        profile = profile_selector.select_profile(setup_type, o.timeframe)
        if profile is None:
            unmatched += 1
            continue
        result = conflict_gate.evaluate(
            trade_profile=profile,
            conflict_final_action=sc.get("conflict_final_action"),
            cfg=cfg,
        )
        buckets[profile][_route_bucket(result)].append(o)

    report: dict[str, dict] = {}
    for profile, by_route in buckets.items():
        report[profile] = {}
        for route, outs in by_route.items():
            n = len(outs)
            wins = sum(1 for x in outs if x.pnl > 0)
            report[profile][route] = {
                "n": n,
                "win_rate": round(wins / n, 3) if n else 0.0,
                "avg_pnl": round(sum(x.pnl for x in outs) / n, 2) if n else 0.0,
            }
    report["_unmatched_no_shadow_data"] = unmatched
    return report


__all__ = ["validation_report"]
