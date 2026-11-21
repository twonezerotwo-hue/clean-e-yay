"""Eşik önericisi: allowlist eşiklerini backtest'le dener, en iyi adayı ÖNERİ olarak
kaydeder. Canlı eşiği DEĞİŞTİRMEZ.

21 Kasım 2026 owner kararı: otomatik eşik uygulaması (eski `THRESHOLD_AUTOTUNE`,
dosya tabanlı runtime override + outcome-rollback) kaldırıldı. 10–17 Kasım arasında
canlı eşikleri onaysız 5 kez değiştirmişti (bias_cuts.bull 60→66, tp_rr_ratio
2,0→2,2); dayanağı 4 sembol × 1d küçük bir backtest farkıydı, rollback ölçümü de
bozuktu. Karar/eşik değişikliği ölçüm + plasebo + owner onayı ister: canlı eşik
yalnız owner'ın config dosyasından (thresholds_v1.0.yaml) gelir.

Akış (train, off-tick, günde en çok bir kez):
  1. Her tunable eşik için mevcut değerin ±NUDGE_STEP adayını üret (guardrail clamp'li).
  2. `threshold_ab.sweep` ile MEVCUT backtest motorunda dener (config-injection seam).
  3. En iyi aday baseline'ı MIN_IMPROVEMENT'tan fazla geçiyorsa VE `edge_report.
     safe_to_autotune` STABLE ise → geçmişe PROPOSED olarak yazılır (owner inceler).

PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import REPO_ROOT, load_thresholds
from packages.learning import edge_report, threshold_ab
from packages.ops.store import write_text_atomic

NUDGE_STEP = 0.10           # ±%10 aday
MIN_IMPROVEMENT = 0.0005    # avg_return_pct bu kadar iyileşmeli (gürültü değil)
PROPOSE_INTERVAL_HOURS = 24.0

# Backtest-doğrulama: global eşikler tek sembolde değil, işlem evreni SEPETİNDE
# doğrulanır (CP4-fix #5) — trade-ağırlıklı ortalama. tp_rr_ratio gibi geometri de
# sepet üstünde daha sağlam.
VALIDATION_SYMBOLS = ["BTCUSD", "ETHUSD", "XAUUSD", "XAGUSD"]
VALIDATION_TF = "1d"


@dataclass(frozen=True)
class ThresholdParam:
    path: str
    lo: float
    hi: float


# Allowlist — run_signal_backtest'in gerçekten ÖLÇTÜĞÜ skaler eşikler (sepet üstünde
# doğrulanır). tp_rr_ratio: tp_pct = sl_pct × tp_rr_ratio. CP4-fix #5: sinyal/rejim
# eşikleri eklendi — bunlar build_timeframe_result'ın bias/rejimini (giriş tetiği)
# doğrudan etkiler, sweep ile ölçülebilir:
#   * technical.bias_cuts.bull / .bear — TF'in BULLISH/BEARISH eşiği (giriş yönü)
#   * technical.adx_trend_min — TREND vs RANGE rejim ayrımı
# (consensus.* eşikleri run_signal_backtest'i ETKİLEMEZ — o karar-katmanı gate'i;
#  onun için tam decision-pipeline backtest'i gerekir, ayrı iş.)
TUNABLE: list[ThresholdParam] = [
    ThresholdParam("paper_trading.tp_rr_ratio", lo=1.5, hi=4.0),
    ThresholdParam("technical.bias_cuts.bull", lo=52.0, hi=70.0),
    ThresholdParam("technical.bias_cuts.bear", lo=30.0, hi=48.0),
    ThresholdParam("technical.adx_trend_min", lo=12.0, hi=30.0),
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
    write_text_atomic(path, json.dumps(data, indent=2, default=str))


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


def _hours_since(ts: str | None) -> float | None:
    try:
        dt = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (datetime.now(UTC) - dt).total_seconds() / 3600.0


def _retire_auto_apply(st: dict) -> dict:
    """Eski otomatik uygulamadan kalan izleme kaydını geçmişe kapatır (bir kez)."""
    active = st.get("active")
    if active:
        closed = {**active, "status": "REMOVED", "event": "AUTO_APPLY_REMOVED",
                  "resolved_at": datetime.now(UTC).isoformat()}
        st["history"] = [closed, *st.get("history", [])][:100]
        st["active"] = None
    return st


def train() -> dict:
    """Eşik öneri döngüsü (off-tick). Canlı eşiği değiştirmez; yalnız öneri yazar."""
    st = _load_state()
    if st.get("active"):
        _save_state(_retire_auto_apply(st))
    age = _hours_since(st.get("last_run_at"))
    if age is not None and age < PROPOSE_INTERVAL_HOURS:
        return {"status": "RECENT"}
    # Edge-gate: kanıt stabil değilse öneri de yok.
    if not edge_report.report().get("safe_to_autotune"):
        return {"status": "EDGE_UNSTABLE"}

    evaluated: list[dict] = []
    proposals: list[dict] = []
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
            p.path, cands, symbols=VALIDATION_SYMBOLS, timeframe=VALIDATION_TF
        )
        base_ret = (ab.get("baseline") or {}).get("avg_return_pct")
        rec = ab.get("recommendation")
        if (
            rec is not None
            and base_ret is not None
            and rec.get("avg_return_pct", -1e9) - base_ret >= MIN_IMPROVEMENT
        ):
            entry = {
                "path": p.path, "from": float(cur), "to": rec["value"],
                "backtest_gain": round(rec["avg_return_pct"] - base_ret, 6),
                "proposed_at": datetime.now(UTC).isoformat(),
                "status": "PROPOSED", "event": "PROPOSED",
            }
            proposals.append(entry)
            evaluated.append({**entry, "decision": "proposed"})
            continue
        evaluated.append({
            "path": p.path, "decision": "no_improvement",
            "baseline_avg_return": base_ret,
            "best": rec,
        })
    st = _load_state()
    st["last_run_at"] = datetime.now(UTC).isoformat()
    st["history"] = [*proposals, *st.get("history", [])][:100]
    _save_state(st)
    return {"status": "PROPOSED" if proposals else "NO_CHANGE", "evaluated": evaluated}


def status_viewmodel() -> dict:
    """Panel/endpoint için özet. Otomatik uygulama yok: `enabled` daima False,
    aktif override ve izlenen uygulama yok; geçmişte öneriler ve eski kayıtlar."""
    st = _load_state()
    return {
        "enabled": False,
        "safe_to_autotune": bool(edge_report.report().get("safe_to_autotune")),
        "tunable": [p.path for p in TUNABLE],
        "active_overrides": {},
        "monitor": None,
        "history": st.get("history", [])[:8],
    }


__all__ = ["TUNABLE", "status_viewmodel", "train"]
