"""CP4 (final) — otonom eşik trainer: propose → backtest-doğrula → dar-bant oto-uygula
→ outcome-rollback. CP4'ün tüm parçalarını birleştirir.

Akış (train, off-tick, `THRESHOLD_AUTOTUNE` açıkken):
  1. Her tunable eşik için mevcut değerin ±NUDGE_STEP adayını üret (guardrail clamp'li).
  2. `threshold_ab.sweep` ile MEVCUT backtest motorunda dener (config-injection seam).
  3. En iyi aday baseline'ı MIN_IMPROVEMENT'tan fazla geçiyorsa VE `edge_report.
     safe_to_autotune` STABLE ise → `threshold_overrides` ile CANLIYA uygula.
  4. Uygulamayı izlemeye al (baseline expectancy); yeterli post-apply outcome sonra
     expectancy düşerse `threshold_overrides.revert` ile geri al (rollback net).

Güvenlik: allowlist (yalnız backtest-ÖLÇÜLEBİLİR eşikler; ilk sürüm
`paper_trading.tp_rr_ratio`), guardrail clamp, dar-bant nudge, edge-gate, outcome-
rollback, tek-değişiklik-tek-doğrulama. Flag OFF → hiçbir şey yapmaz (train DISABLED,
override okunmaz → bayt-aynı). weight_rollback expectancy pencereleri REUSE.

PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry import threshold_overrides
from packages.data.registry.loader import REPO_ROOT, load_thresholds
from packages.learning import edge_report, threshold_ab, weight_rollback

NUDGE_STEP = 0.10           # ±%10 aday
MIN_IMPROVEMENT = 0.0005    # avg_return_pct bu kadar iyileşmeli (gürültü değil)
_MIN_OUTCOMES_DEFAULT = 15
_MONITOR_MAX_AGE_HOURS = 336.0

# Backtest-doğrulama sembol/TF'i (harness; genişletmeye açık).
VALIDATION_SYMBOL = "BTCUSD"
VALIDATION_TF = "1d"


@dataclass(frozen=True)
class ThresholdParam:
    path: str
    lo: float
    hi: float


# Allowlist — YALNIZ run_signal_backtest'in gerçekten ölçtüğü skaler eşikler.
# tp_rr_ratio: _sl_tp_pct'te tp_pct = sl_pct × tp_rr_ratio (backtest bunu kullanır).
# (consensus/regime eşikleri run_signal_backtest'i etkilemediğinden ŞİMDİLİK dışarıda
#  — onlar için o eşikleri exercise eden bir backtest gerekir; sonraki iş.)
TUNABLE: list[ThresholdParam] = [
    ThresholdParam("paper_trading.tp_rr_ratio", lo=1.5, hi=4.0),
]


def _state_path() -> Path:
    p = Path(os.environ.get("THRESHOLD_AUTOAPPLY_PATH", "data/runtime/threshold_autoapply.json"))
    return p if p.is_absolute() else REPO_ROOT / p


def _load_state() -> dict:
    path = _state_path()
    if not path.exists():
        return {"active": None, "history": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"active": None, "history": []}
    data.setdefault("active", None)
    if not isinstance(data.get("history"), list):
        data["history"] = []
    return data


def _save_state(data: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _min_outcomes() -> int:
    try:
        return max(1, int(os.environ.get("THRESHOLD_ROLLBACK_MIN_OUTCOMES", _MIN_OUTCOMES_DEFAULT)))
    except (TypeError, ValueError):
        return _MIN_OUTCOMES_DEFAULT


def _current(path: str):
    node = load_thresholds()
    for k in path.split("."):
        if not isinstance(node, dict) or k not in node:
            return None
        node = node[k]
    return node


def _candidates(cur: float, p: ThresholdParam) -> list[float]:
    out = []
    for v in (cur * (1.0 - NUDGE_STEP), cur * (1.0 + NUDGE_STEP)):
        v = round(max(p.lo, min(p.hi, v)), 6)
        if v != cur and v not in out:
            out.append(v)
    return out


def train() -> dict:
    """Otonom eşik-ayar döngüsü (off-tick). Flag OFF → DISABLED (no-op, bayt-aynı)."""
    if not threshold_overrides.autotune_enabled():
        return {"status": "DISABLED"}
    # Tek-değişiklik-tek-doğrulama: aktif izleme varken yeni apply yok.
    if _load_state().get("active") is not None:
        return {"status": "MONITORING"}
    # Edge-gate: kanıt stabil değilse oto-uygulama YOK (kırmızı çizgi).
    if not edge_report.report().get("safe_to_autotune"):
        return {"status": "EDGE_UNSTABLE"}

    evaluated: list[dict] = []
    for p in TUNABLE:
        cur = _current(p.path)
        if not isinstance(cur, (int, float)):
            evaluated.append({"path": p.path, "decision": "skip_non_scalar"})
            continue
        cands = _candidates(float(cur), p)
        if not cands:
            evaluated.append({"path": p.path, "decision": "no_candidates"})
            continue
        ab = threshold_ab.sweep(
            p.path, cands, symbol=VALIDATION_SYMBOL, timeframe=VALIDATION_TF
        )
        base_ret = (ab.get("baseline") or {}).get("avg_return_pct")
        rec = ab.get("recommendation")
        if (
            rec is not None
            and base_ret is not None
            and rec.get("avg_return_pct", -1e9) - base_ret >= MIN_IMPROVEMENT
        ):
            # Uygula + izlemeye al (tek değişiklik → ilk uygun aday).
            base_n, base_exp = weight_rollback.pre_apply_expectancy()
            threshold_overrides.set_override(p.path, rec["value"], prev=float(cur))
            entry = {
                "path": p.path, "from": float(cur), "to": rec["value"],
                "backtest_gain": round(rec["avg_return_pct"] - base_ret, 6),
                "baseline_expectancy": round(base_exp, 4), "baseline_n": base_n,
                "applied_at": datetime.now(UTC).isoformat(), "status": "MONITORING",
            }
            st = _load_state()
            st["active"] = entry
            st["history"] = [{**entry, "event": "AUTO_APPLIED"}, *st.get("history", [])][:100]
            _save_state(st)
            evaluated.append({"path": p.path, "decision": "auto_applied", **entry})
            return {"status": "APPLIED", "evaluated": evaluated}
        evaluated.append({
            "path": p.path, "decision": "no_improvement",
            "baseline_avg_return": base_ret,
            "best": rec,
        })
    return {"status": "NO_CHANGE", "evaluated": evaluated}


def _resolve(active: dict, *, outcome: str, post_exp: float, post_n: int,
             reason: str | None = None) -> dict:
    resolved = {**active, "status": outcome, "post_expectancy": round(post_exp, 4),
                "post_n": post_n, "resolved_at": datetime.now(UTC).isoformat()}
    if reason:
        resolved["reason"] = reason
    st = _load_state()
    st["active"] = None
    st["history"] = [{**resolved, "event": outcome}, *st.get("history", [])][:100]
    _save_state(st)
    return resolved


def check_rollback() -> dict:
    """İzlenen eşik apply'ı değerlendir: no_active | monitoring | CONFIRMED |
    ROLLED_BACK. post < baseline → threshold_overrides.revert (geri al)."""
    active = _load_state().get("active")
    if not active:
        return {"status": "no_active"}
    need = _min_outcomes()
    applied_at = str(active.get("applied_at") or "")
    post_n, post_exp = weight_rollback.post_open_expectancy(applied_at)
    baseline = float(active.get("baseline_expectancy", 0.0))
    if post_n < need:
        dt = weight_rollback._parse_dt(applied_at)
        age_h = (datetime.now(UTC) - dt).total_seconds() / 3600.0 if dt else None
        if age_h is not None and age_h >= _MONITOR_MAX_AGE_HOURS:
            threshold_overrides.revert(active["path"])
            return _resolve(active, outcome="ROLLED_BACK", post_exp=post_exp,
                            post_n=post_n, reason="monitor_expired")
        return {"status": "monitoring", "post_n": post_n, "need": need}
    if post_exp < baseline:
        threshold_overrides.revert(active["path"])
        return _resolve(active, outcome="ROLLED_BACK", post_exp=post_exp, post_n=post_n)
    return _resolve(active, outcome="CONFIRMED", post_exp=post_exp, post_n=post_n)


def status_viewmodel() -> dict:
    """Panel/endpoint için özet."""
    st = _load_state()
    return {
        "enabled": threshold_overrides.autotune_enabled(),
        "safe_to_autotune": bool(edge_report.report().get("safe_to_autotune")),
        "tunable": [p.path for p in TUNABLE],
        "active_overrides": threshold_overrides.active(),
        "monitor": st.get("active"),
        "history": st.get("history", [])[:8],
    }


__all__ = ["TUNABLE", "check_rollback", "status_viewmodel", "train"]
