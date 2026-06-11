"""G6 — Calibration trainer.

Politika:
- Yalnızca `data_verified=True` ve `predicted_confidence is not None`
  trade'ler örneklere alınır (DATA_POLICY).
- En az `MIN_SAMPLES` örnek olmadan fit yapılmaz; insufficient durumunda
  identity (a=1, b=0) saklanır.
- Owner approval gerekmez; calibration parametreleri audit'lenir (status
  + samples + fitted_at + reliability bins).
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from packages.learning import calibration_store
from packages.learning.calibration import fit_platt, reliability_bins
from packages.paper import state as paper_state


def _samples_from_state() -> list[tuple[float, bool]]:
    s = paper_state.load()
    out: list[tuple[float, bool]] = []
    for t in s.recent_trades:
        if not getattr(t, "data_verified", False):
            continue
        p = getattr(t, "predicted_confidence", None)
        if p is None:
            continue
        out.append((float(p), bool(t.pnl_usd > 0)))
    return out


def train() -> dict:
    """Calibration parametrelerini öğren, store'a yaz, özet döndür."""
    samples = _samples_from_state()
    n = len(samples)
    if n < calibration_store.MIN_SAMPLES:
        params = calibration_store.CalibrationParams(
            a=1.0,
            b=0.0,
            samples=n,
            fitted_at=datetime.now(UTC).isoformat(),
            status="insufficient",
        )
        calibration_store.save(params)
        return {
            "status": "INSUFFICIENT",
            "samples": n,
            "min_required": calibration_store.MIN_SAMPLES,
            "params": asdict(params),
            "bins": [],
        }

    a, b = fit_platt(samples)
    params = calibration_store.CalibrationParams(
        a=round(float(a), 6),
        b=round(float(b), 6),
        samples=n,
        fitted_at=datetime.now(UTC).isoformat(),
        status="fitted",
    )
    calibration_store.save(params)
    bins = [asdict(x) for x in reliability_bins(samples, n_bins=5)]
    return {
        "status": "FITTED",
        "samples": n,
        "params": asdict(params),
        "bins": bins,
    }
