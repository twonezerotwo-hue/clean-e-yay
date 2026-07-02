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


def _samples_from_state() -> list[tuple[str, float, bool]]:
    """Canonical outcome'lardan (recent_trades + decision_log birleşimi) fit
    örnekleri: (timeframe, raw_confidence, win). Volatile recent_trades
    penceresi yerine kalıcı kaydı kullanır — paper_state bozulması/200-pencere
    taşması veri kaybına yol açmaz.

    x = raw_confidence (kalibrasyon ÖNCESİ) — predict_calibrated'ın karar
    anında aldığı girdiyle aynı dağılım. predicted_confidence fit'e GİRMEZ.
    F4-1: timeframe per-TF fit için taşınır; global fit tüm örnekleri kullanır."""
    out: list[tuple[str, float, bool]] = []
    for o in outcomes_mod.outcomes_from_state():
        if not o.data_verified or o.raw_confidence is None:
            continue
        out.append((str(o.timeframe or "1d"), float(o.raw_confidence), bool(o.pnl > 0)))
    return out


def _fit_per_timeframe(
    samples: list[tuple[str, float, bool]], fitted_at: str
) -> dict[str, calibration_store.CalibrationParams]:
    """F4-1 — TF başına Platt fit'i. TF'in örneği MIN_SAMPLES altındaysa
    "insufficient" (identity parametreli) kaydedilir — örnek sayısı owner'ın
    aktivasyon kanıtıdır, sahte fit üretilmez."""
    by_tf: dict[str, list[tuple[float, bool]]] = {}
    for tf, x, y in samples:
        by_tf.setdefault(tf, []).append((x, y))
    per: dict[str, calibration_store.CalibrationParams] = {}
    for tf, tf_samples in sorted(by_tf.items()):
        n = len(tf_samples)
        if n < calibration_store.MIN_SAMPLES:
            per[tf] = calibration_store.CalibrationParams(
                a=1.0, b=0.0, samples=n, fitted_at=fitted_at, status="insufficient"
            )
            continue
        a, b = fit_platt(tf_samples)
        per[tf] = calibration_store.CalibrationParams(
            a=round(float(a), 6),
            b=round(float(b), 6),
            samples=n,
            fitted_at=fitted_at,
            status="fitted",
        )
    return per


def train() -> dict:
    """Calibration parametrelerini öğren (global + F4-1 per-TF), store'a yaz,
    özet döndür. Global fit davranışı birebir eskisi; per-TF fit'ler additive
    yazılır ve yalnız `calibration.tf_platt` flag'i açıkken karar zincirine girer."""
    tf_samples = _samples_from_state()
    samples = [(x, y) for _, x, y in tf_samples]
    n = len(samples)
    fitted_at = datetime.now(UTC).isoformat()
    per_tf = _fit_per_timeframe(tf_samples, fitted_at)
    per_tf_summary = {tf: asdict(p) for tf, p in per_tf.items()}
    tf_fitted = sorted(tf for tf, p in per_tf.items() if p.status == "fitted")
    if n < calibration_store.MIN_SAMPLES:
        params = calibration_store.CalibrationParams(
            a=1.0,
            b=0.0,
            samples=n,
            fitted_at=fitted_at,
            status="insufficient",
        )
        calibration_store.save(params, per_timeframe=per_tf)
        return {
            "status": "INSUFFICIENT",
            "samples": n,
            "min_required": calibration_store.MIN_SAMPLES,
            "params": asdict(params),
            "bins": [],
            "per_timeframe": per_tf_summary,
            "tf_fitted": tf_fitted,
        }

    a, b = fit_platt(samples)
    params = calibration_store.CalibrationParams(
        a=round(float(a), 6),
        b=round(float(b), 6),
        samples=n,
        fitted_at=fitted_at,
        status="fitted",
    )
    calibration_store.save(params, per_timeframe=per_tf)
    bins = [asdict(x) for x in reliability_bins(samples, n_bins=5)]
    return {
        "status": "FITTED",
        "samples": n,
        "params": asdict(params),
        "bins": bins,
        "per_timeframe": per_tf_summary,
        "tf_fitted": tf_fitted,
    }
