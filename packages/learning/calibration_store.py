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


def _load_raw() -> dict:
    """Store dosyasının ham içeriği (kilitsiz iç yardımcı; çağıran kilitler)."""
    path = _store_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _params_from(data: dict) -> CalibrationParams:
    try:
        return CalibrationParams(
            a=float(data.get("a", 1.0)),
            b=float(data.get("b", 0.0)),
            samples=int(data.get("samples", 0)),
            fitted_at=data.get("fitted_at"),
            status=data.get("status", "identity"),
        )
    except (TypeError, ValueError):
        return CalibrationParams()


def load() -> CalibrationParams:
    with _LOCK:
        data = _load_raw()
    if not data:
        return CalibrationParams()
    return _params_from(data)


def load_per_timeframe() -> dict[str, CalibrationParams]:
    """F4-1 — TF başına Platt parametreleri (yoksa boş dict; legacy dosya uyumlu)."""
    with _LOCK:
        data = _load_raw()
    per = data.get("per_timeframe")
    if not isinstance(per, dict):
        return {}
    return {
        str(tf): _params_from(p) for tf, p in per.items() if isinstance(p, dict)
    }


def load_tf(timeframe: str) -> CalibrationParams | None:
    """F4-1 — tek TF'in fit'i; hiç fit edilmemişse None (uydurma parametre yok)."""
    return load_per_timeframe().get(timeframe)


def save(
    params: CalibrationParams,
    per_timeframe: dict[str, CalibrationParams] | None = None,
) -> CalibrationParams:
    """Global parametreleri (ve verildiyse TF fit'lerini) atomik-yakın yaz.

    `per_timeframe=None` → dosyadaki mevcut TF fit'leri KORUNUR (global-only
    çağrılar TF verisini silmesin)."""
    path = _store_path()
    with _LOCK:
        payload = dict(asdict(params))
        if per_timeframe is None:
            existing = _load_raw().get("per_timeframe")
            if isinstance(existing, dict):
                payload["per_timeframe"] = existing
        else:
            payload["per_timeframe"] = {
                tf: asdict(p) for tf, p in per_timeframe.items()
            }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
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


def tf_platt_enabled() -> bool:
    """F4-1 — `calibration.tf_platt` owner-flag'i (default KAPALI = global fit).

    Aktivasyon ayrı tarihli owner kararı: /learning/calibration'daki
    `per_timeframe` örnek sayıları + fit ayrışması izlenip açılır."""
    try:
        return bool(load_thresholds().get("calibration", {}).get("tf_platt", False))
    except (OSError, KeyError, ValueError, TypeError):
        return False


def predict_calibrated_tf(raw_p: float, timeframe: str) -> tuple[float, str]:
    """F4-1 — TF-duyarlı kalibrasyon. Flag KAPALIYKEN global `predict_calibrated`
    birebir (bayt-aynı). AÇIKKEN: o TF'in fit'i varsa uygulanır (kaynak
    "fitted_tf"); TF fit'i yoksa/yetersizse global fit'e düşer (dürüst fallback,
    sahte TF parametresi uydurulmaz). RiskGate'i bypass etmez."""
    if not tf_platt_enabled():
        return predict_calibrated(raw_p)
    tf_params = load_tf(timeframe)
    if tf_params is None or tf_params.status != "fitted":
        return predict_calibrated(raw_p)
    raw = min(max(raw_p, 0.0), 1.0)
    val = apply_platt(raw, tf_params.a, tf_params.b)
    if math.isnan(val) or math.isinf(val):
        return round(raw, 4), "insufficient"
    return round(min(max(val, 0.0), 1.0), 4), "fitted_tf"


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
    # F4-1: TF-fit ("fitted_tf") de aynı şişme guardrail'ine tabi — TF katmanı
    # guardrail'i bypass edemez.
    if source not in ("fitted", "fitted_tf"):
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
        return capped, f"{source}_capped"
    return fitted_p, source
