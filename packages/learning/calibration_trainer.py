"""G6 — Calibration trainer.

Politika:
- Yalnızca `data_verified=True` ve `raw_confidence is not None` trade'ler
  örneklere alınır (DATA_POLICY). Fit girdisi HAM güvendir: predict_calibrated
  karar anında ham güvene uygulanır, dolayısıyla fit de aynı dağılımdan
  öğrenmeli. (Eskiden `predicted_confidence` — yani önceki fit'in ÇIKTISI —
  kullanılıyordu; model kendi çıktısıyla eğitilip her re-fit'te girdi dağılımı
  kayıyordu. raw_confidence taşımayan legacy kayıtlar fit'e girmez — dürüst
  daralma, uydurma fallback yok.)
- En az `MIN_SAMPLES` örnek olmadan fit yapılmaz; insufficient durumunda
  identity (a=1, b=0) saklanır.
- Owner approval gerekmez; calibration parametreleri audit'lenir (status
  + samples + fitted_at + reliability bins).
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from packages.learning import calibration_store
from packages.learning import outcomes as outcomes_mod
from packages.learning.calibration import fit_platt, reliability_bins


def _samples_from_state() -> list[tuple[float, bool]]:
    """Canonical outcome'lardan (recent_trades + decision_log birleşimi) fit
    örnekleri. Volatile recent_trades penceresi yerine kalıcı kaydı kullanır —
    paper_state bozulması/200-pencere taşması veri kaybına yol açmaz.

    x = raw_confidence (kalibrasyon ÖNCESİ) — predict_calibrated'ın karar
    anında aldığı girdiyle aynı dağılım. predicted_confidence fit'e GİRMEZ."""
    out: list[tuple[float, bool]] = []
    for o in outcomes_mod.outcomes_from_state():
        if not o.data_verified or o.raw_confidence is None:
            continue
        out.append((float(o.raw_confidence), bool(o.pnl > 0)))
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
