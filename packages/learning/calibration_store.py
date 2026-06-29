"""Calibration parametreleri (Platt a, b) için file-backed store.

Politika:
- Fit edilmiş parametre yoksa identity (a=1, b=0) → confidence değişmez.
- `predict_calibrated()` her zaman güvenli değer döner; karar engine'i
  bunu sadece bilgi/sizing için kullanır, RiskGate'i bypass etmez.
"""
from __future__ import annotations

import json
import math
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from packages.data.registry.loader import REPO_ROOT, load_thresholds
from packages.learning.calibration import apply_platt

MIN_SAMPLES = 10
_LOCK = threading.Lock()


def _store_path() -> Path:
    p = Path(os.environ.get("CALIBRATION_STORE_PATH", "data/runtime/platt.json"))
    return p if p.is_absolute() else REPO_ROOT / p


@dataclass
class CalibrationParams:
    a: float = 1.0
    b: float = 0.0
    samples: int = 0
    fitted_at: str | None = None
    status: str = "identity"  # identity | fitted | insufficient


def load() -> CalibrationParams:
    path = _store_path()
    with _LOCK:
        if not path.exists():
            return CalibrationParams()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return CalibrationParams(
                a=float(data.get("a", 1.0)),
                b=float(data.get("b", 0.0)),
                samples=int(data.get("samples", 0)),
                fitted_at=data.get("fitted_at"),
                status=data.get("status", "identity"),
            )
        except (OSError, json.JSONDecodeError, ValueError):
            return CalibrationParams()


def save(params: CalibrationParams) -> CalibrationParams:
    path = _store_path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(params), indent=2), encoding="utf-8")
    return params


def raw_confidence_from_score(score: float) -> float:
    """Consensus score (0-100) → ham confidence (0-1).

    Skor 50'den uzaklaştıkça artan |score-50|/50 yaklaşımı. 0.99 ile cap.
    """
    return min(0.99, max(0.0, abs(score - 50.0) / 50.0))


def predict_calibrated(
    raw_p: float,
    params: CalibrationParams | None = None,
) -> tuple[float, str]:
    """Ham olasılığı kalibre edilmiş olasılığa çevirir.

    Yetersiz örnek varsa identity dönüyoruz; karar engine bunu görür ve
    `confidence_source` damgasını TradeDecision'a koyar.
    """
    params = params or load()
    raw = min(max(raw_p, 0.0), 1.0)
    if params.status != "fitted":
        return round(raw, 4), params.status
    val = apply_platt(raw, params.a, params.b)
    if math.isnan(val) or math.isinf(val):
        return round(raw, 4), "insufficient"
    return round(min(max(val, 0.0), 1.0), 4), "fitted"


def _guardrail_cfg() -> dict:
    try:
        return load_thresholds().get("calibration_guardrail", {}) or {}
    except (OSError, KeyError, ValueError, TypeError):
        return {}


def inflation_delta(raw_p: float, fitted_p: float) -> float:
    """Kalibrasyonun ham olasılığı ne kadar şişirdiği (negatifse: kıstı)."""
    return round(float(fitted_p) - float(raw_p), 4)


def apply_inflation_guardrail(raw_p: float, fitted_p: float, source: str) -> tuple[float, str]:
    """Kalibrasyonun ZAYIF ham sinyali aşırı şişirmesini sınırlar.

    OWNER-FLAG, varsayılan KAPALI. `calibration_guardrail.enabled=false` iken
    PASSTHROUGH — mevcut karar/sizing davranışı birebir korunur (bozulma yok).
    Açıkken: `fitted - raw > max_inflation_delta` ise fitted = raw + max_delta'ya
    kıstırılır ve kaynak "fitted_capped" olarak damgalanır (ledger'da görünür).
    Yalnızca KISITLAR — fitted'i asla artırmaz, RiskGate/DQS'i bypass etmez.
    """
    if source != "fitted":
        return fitted_p, source
    cfg = _guardrail_cfg()
    if not cfg.get("enabled", False):
        return fitted_p, source
    try:
        max_delta = float(cfg.get("max_inflation_delta", 0.25))
    except (TypeError, ValueError):
        max_delta = 0.25
    if max_delta < 0:
        return fitted_p, source
    if float(fitted_p) - float(raw_p) > max_delta:
        capped = round(min(1.0, max(0.0, float(raw_p) + max_delta)), 4)
        return capped, "fitted_capped"
    return fitted_p, source
