"""Platt scaling + reliability binning — heuristik confidence kalibrasyonu."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class CalibrationBin:
    bin_lo: float
    bin_hi: float
    predicted: float
    observed: float
    count: int


def reliability_bins(
    samples: list[tuple[float, bool]],
    n_bins: int = 5,
) -> list[CalibrationBin]:
    """Her binin tahmin ortalaması vs. gözlenen kazanma oranı."""
    if not samples:
        return []
    edges = [i / n_bins for i in range(n_bins + 1)]
    bins: list[CalibrationBin] = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        # Bugfix 2026-07-02: son kovanın "p == hi dahil" istisnası alt sınırı
        # unutuyordu (p <= hi TÜM örnekleri eşliyordu) — son kova veri setinin
        # tamamını çifte sayıyordu (0.8-1.0 kovasında 130/130 görünmesinin sebebi).
        in_bin = [
            (p, w)
            for p, w in samples
            if p >= lo and (p < hi or (i == n_bins - 1 and p <= hi))
        ]
        if not in_bin:
            bins.append(CalibrationBin(bin_lo=lo, bin_hi=hi, predicted=0.0, observed=0.0, count=0))
            continue
        pred = sum(p for p, _ in in_bin) / len(in_bin)
        obs = sum(1 for _, w in in_bin if w) / len(in_bin)
        bins.append(
            CalibrationBin(
                bin_lo=round(lo, 3),
                bin_hi=round(hi, 3),
                predicted=round(pred, 3),
                observed=round(obs, 3),
                count=len(in_bin),
            )
        )
    return bins


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def fit_platt(samples: list[tuple[float, bool]], lr: float = 0.05, steps: int = 200) -> tuple[float, float]:
    """Platt scaling — tek değişkenli lojistik regresyon (a, b).
    Çok az veri için bile stabil; başlangıç (a=1, b=0).
    """
    a, b = 1.0, 0.0
    if not samples:
        return a, b
    for _ in range(steps):
        ga = 0.0
        gb = 0.0
        for p, w in samples:
            x = _logit(p)
            z = a * x + b
            sig = 1.0 / (1.0 + math.exp(-z))
            err = sig - (1.0 if w else 0.0)
            ga += err * x
            gb += err
        a -= lr * ga / len(samples)
        b -= lr * gb / len(samples)
    return a, b


def apply_platt(p: float, a: float, b: float) -> float:
    z = a * _logit(p) + b
    return 1.0 / (1.0 + math.exp(-z))
