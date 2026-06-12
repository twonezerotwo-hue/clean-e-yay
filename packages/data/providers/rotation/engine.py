"""Sermaye rotasyonu motoru — eski Codex CapitalRotationProvider portu.

Clean OHLCV cache'inin 1d barları üstünde çalışır (pure Python, ek bağımlılık
yok). Hesaplar:
  1. Varlık başına 30g momentum
  2. Çapraz oran trendleri (GLD/TLT, BTC/GLD, TLT/SPY, HYG/LQD, BTC/DXY, GLD/DXY)
  3. Varlık sınıfı para-akış skorları (legacy _FLOW_SIGNALS katsayıları)
  4. Risk-on/risk-off eğiliminden 0-100 rotasyon skoru

Korelasyon analizi G4'te (packages/risk/correlation.py) zaten var — burada
tekrarlanmaz. Veri yetersizse sonuç UNAVAILABLE; mock skor üretilmez.
PAPER_SAFE / NO_EXECUTION — yalnızca gözlem.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Rotasyon anahtarı → Clean OHLCV sembolü
ROTATION_SYMBOLS: dict[str, str] = {
    "BTC": "BTCUSD",
    "GLD": "XAUUSD",
    "XAG": "XAGUSD",
    "TLT": "TLT",
    "SPY": "SP500",   # Clean OHLCV registry'sinde S&P 500 = "SP500" (^GSPC)
    "HYG": "HYG",
    "LQD": "LQD",
    "DXY": "DXY",
    "OIL": "BRENT",
}

# Her varlık sınıfının ana göstergesi (momentum referansı)
_CLASS_MAIN_ASSET: dict[str, str] = {
    "ALTIN": "GLD",
    "GÜMÜŞ": "XAG",
    "TAHVİL": "TLT",
    "BTC": "BTC",
    "HİSSE": "SPY",
    "DOLAR_GÜCÜ": "DXY",
    "PETROL": "OIL",
}

# Sınıf başına katkı sinyalleri: (sinyal, katsayı) — legacy parity.
# Pozitif katsayı → sinyal güçlenince o sınıfa para giriyor demek.
_FLOW_SIGNALS: dict[str, list[tuple[str, float]]] = {
    "ALTIN": [("GLD", 1.5), ("GLD/TLT", 1.0), ("GLD/DXY", 1.0), ("BTC/GLD", -0.5)],
    "GÜMÜŞ": [("XAG", 1.5), ("GLD/TLT", 0.5), ("GLD/DXY", 0.5)],
    "TAHVİL": [("TLT", 1.5), ("TLT/SPY", 1.0), ("GLD/TLT", -0.5)],
    "BTC": [("BTC", 1.5), ("BTC/GLD", 0.8), ("BTC/DXY", 1.0)],
    "HİSSE": [("SPY", 1.5), ("HYG/LQD", 0.5), ("TLT/SPY", -0.8)],
    "DOLAR_GÜCÜ": [("DXY", 1.5), ("BTC/DXY", -0.5), ("GLD/DXY", -0.5)],
    "PETROL": [("OIL", 2.0)],
}

_RATIO_DEFS: list[dict[str, str]] = [
    {
        "pair": "GLD/TLT", "num": "GLD", "den": "TLT",
        "up": "Altın tahvile baskın — enflasyon/güvensizlik baskısı",
        "down": "Tahvil altına baskın — deflasyon/güvenli liman talebi",
        "flat": "Altın–tahvil dengeli",
    },
    {
        "pair": "BTC/GLD", "num": "BTC", "den": "GLD",
        "up": "Kripto altına baskın — spekülatif risk iştahı yüksek",
        "down": "Altın kriptoya baskın — güvenli varlık tercihi güçlü",
        "flat": "BTC–altın dengeli",
    },
    {
        "pair": "TLT/SPY", "num": "TLT", "den": "SPY",
        "up": "Tahvil hisseye baskın — savunmacı rotasyon",
        "down": "Hisse tahvile baskın — risk-on ortam sürüyor",
        "flat": "Tahvil–hisse dengeli",
    },
    {
        "pair": "HYG/LQD", "num": "HYG", "den": "LQD",
        "up": "HY kredi IG'yi geçiyor — kredi risk iştahı güçlü",
        "down": "IG kredi HY'yi geçiyor — kaliteye kaçış",
        "flat": "HY–IG kredi dengeli",
    },
    {
        "pair": "BTC/DXY", "num": "BTC", "den": "DXY",
        "up": "BTC dolara baskın — dolar zayıflarken kripto canlanıyor",
        "down": "Dolar BTC'ye baskın — güçlü dolar kriptoyu baskılıyor",
        "flat": "BTC–dolar dengeli",
    },
    {
        "pair": "GLD/DXY", "num": "GLD", "den": "DXY",
        "up": "Altın dolara baskın — hedge talebi derin",
        "down": "Dolar altına baskın — güçlü dolar altını baskılıyor",
        "flat": "Altın–dolar dengeli",
    },
]


@dataclass
class ClassScore:
    name: str
    score: float          # -1.5 → +1.5 normalize
    momentum_30d: float   # ana varlığın 30g % değişimi
    direction: str        # GİRİŞ | ÇIKIŞ | NÖTR


@dataclass
class RotationResult:
    available: bool
    score: float = 50.0               # 0–100 (risk-on eğilimi)
    direction: str = "neutral"        # bullish | bearish | neutral
    primary_flow: str = "KARISIK"
    class_scores: list[ClassScore] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
# Matematik (pure python)
# ---------------------------------------------------------------------------

def momentum_30d(series: list[float]) -> float:
    if len(series) < 31:
        return 0.0
    old, new = series[-31], series[-1]
    if old <= 0:
        return 0.0
    return round((new - old) / old * 100, 2)


def _trend(delta: float) -> str:
    if delta > 1.5:
        return "RISING"
    if delta < -1.5:
        return "FALLING"
    return "FLAT"


def _score_class(class_name: str, momenta: dict[str, float]) -> float:
    signals = _FLOW_SIGNALS.get(class_name, [])
    total_weight = sum(abs(w) for _, w in signals)
    if total_weight == 0:
        return 0.0
    score = 0.0
    for sig_key, weight in signals:
        if sig_key in momenta:
            # Normalize: %5 hareket = tam 1 puan (legacy parity)
            m = max(-1.5, min(1.5, momenta[sig_key] / 5.0))
            score += m * weight
    return round(score / total_weight, 4)


def _class_direction(score: float) -> str:
    if score > 0.15:
        return "GİRİŞ"
    if score < -0.15:
        return "ÇIKIŞ"
    return "NÖTR"


def _check_return_quality(momenta: dict[str, float]) -> str | None:
    """5+ varlık aynı momentum'a sahipse veri serileri güvenilir değil
    (legacy sanity guard — cache contamination / aynı seri tespiti)."""
    base = {k: round(v, 2) for k, v in momenta.items() if k in ROTATION_SYMBOLS}
    if len(base) < 5:
        return None
    counts: dict[float, int] = {}
    for v in base.values():
        bucket = round(v * 20) / 20
        counts[bucket] = counts.get(bucket, 0) + 1
    if counts and max(counts.values()) >= 5:
        return "identical_returns_across_assets"
    return None


# ---------------------------------------------------------------------------
# Ana hesap
# ---------------------------------------------------------------------------

def compute(closes: dict[str, list[float]]) -> RotationResult:
    """`closes`: rotasyon anahtarı → 1d kapanış serisi (en az 32 bar).

    Deterministiktir — aynı seriler aynı sonucu üretir.
    """
    usable = {k: v for k, v in closes.items() if len(v) >= 32}
    if len(usable) < 3:
        return RotationResult(
            available=False,
            error=f"data_insufficient: {len(usable)}/9 varlık serisi (min 3)",
        )

    momenta: dict[str, float] = {k: momentum_30d(v) for k, v in usable.items()}

    quality_reason = _check_return_quality(momenta)
    if quality_reason:
        return RotationResult(available=False, error=quality_reason)

    # Oran sinyalleri
    ratio_lines: list[str] = []
    for rd in _RATIO_DEFS:
        num_k, den_k = rd["num"], rd["den"]
        if num_k not in usable or den_k not in usable:
            continue
        num_s, den_s = usable[num_k], usable[den_k]
        n = min(len(num_s), len(den_s))
        if n < 32:
            continue
        ratio = [a / b for a, b in zip(num_s[-n:], den_s[-n:], strict=True) if b > 0]
        if len(ratio) < 32:
            continue
        cur, old = ratio[-1], ratio[-31]
        delta = round((cur - old) / old * 100, 2) if old > 0 else 0.0
        momenta[rd["pair"]] = delta
        t = _trend(delta)
        meaning = rd["up"] if t == "RISING" else (rd["down"] if t == "FALLING" else rd["flat"])
        arrow = "↑" if t == "RISING" else ("↓" if t == "FALLING" else "→")
        ratio_lines.append(f"{rd['pair']} {arrow} {delta:+.1f}%: {meaning}")

    # Sınıf skorları
    scored: list[ClassScore] = []
    for cls in _FLOW_SIGNALS:
        main = _CLASS_MAIN_ASSET[cls]
        if main not in usable:
            continue
        s = _score_class(cls, momenta)
        scored.append(ClassScore(cls, s, momenta.get(main, 0.0), _class_direction(s)))
    scored.sort(key=lambda x: -x.score)

    primary = scored[0].name if scored else "KARISIK"
    gap = (scored[0].score - scored[1].score) if len(scored) > 1 else 0.0
    if int(max(0.0, gap) * 70) < 12:
        primary = "KARISIK"

    # Risk-on eğilimi → 0-100 skor: (HİSSE+BTC) − (ALTIN+TAHVİL+DOLAR_GÜCÜ)
    by_name = {cs.name: cs.score for cs in scored}
    risk_on = [by_name[n] for n in ("HİSSE", "BTC") if n in by_name]
    defensive = [by_name[n] for n in ("ALTIN", "TAHVİL", "DOLAR_GÜCÜ") if n in by_name]
    if not risk_on or not defensive:
        return RotationResult(
            available=False,
            error="data_insufficient: risk-on/defansif sınıf serileri eksik",
        )
    tilt = (sum(risk_on) / len(risk_on)) - (sum(defensive) / len(defensive))
    score = max(0.0, min(100.0, 50.0 + tilt * 25.0))
    direction = "bullish" if score > 55 else ("bearish" if score < 45 else "neutral")

    evidence = [f"Akış: {primary}" if primary != "KARISIK" else "Akış: karışık (tek yön yok)"]
    for cs in scored[:3]:
        evidence.append(
            f"{cs.name}: skor {cs.score:+.2f} ({cs.direction}), 30g {cs.momentum_30d:+.1f}%"
        )
    evidence.extend(ratio_lines[:3])

    return RotationResult(
        available=True,
        score=round(score, 1),
        direction=direction,
        primary_flow=primary,
        class_scores=scored,
        evidence=evidence,
    )
