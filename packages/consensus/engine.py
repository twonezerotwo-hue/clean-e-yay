"""Konsensüs motoru — 5+1 modül, rejim ağırlıklı toplam.

Modüller:
  - touche        (teknik)
  - fundamental   (rejim/makro)
  - news          (haber)
  - sentinel      (volatilite/stres)
  - quantum       (rotasyon)
  - chart_pattern (opsiyonel — yoksa ağırlık yeniden dağıtılır)

Eski projede `_redistribute_weights` davranışı korundu: eksik modül varsa
ağırlık otomatik yeniden dağıtılır.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from packages.data.ingestion.pipeline import MarketSnapshot
from packages.data.registry.loader import load_active_weights
from packages.regime.classifier import RegimeOutput


@dataclass
class ModuleScore:
    name: str
    score: float
    weight: float
    contribution: float


@dataclass
class ConsensusResult:
    symbol: str
    score: float                        # 0–100
    direction: str                      # bullish/bearish/neutral
    modules: list[ModuleScore]
    confluence_aligned: bool
    dominant_module: str
    timeframe: str = "1d"               # T2 — (symbol, timeframe) sinyal uzayı
    warnings: list[str] = field(default_factory=list)  # T2 additive


def _direction(s: float) -> str:
    if s >= 60:
        return "bullish"
    if s <= 40:
        return "bearish"
    return "neutral"


def _redistribute(weights: dict[str, float], available: set[str]) -> dict[str, float]:
    keep = {k: v for k, v in weights.items() if k in available}
    total = sum(keep.values())
    if total <= 0:
        # eşit dağıt
        return {k: 1.0 / max(1, len(available)) for k in available}
    return {k: v / total for k, v in keep.items()}


def _touche(
    symbol: str,
    snap: MarketSnapshot,
    timeframe: str = "1d",
) -> tuple[float, list[str]]:
    """Teknik modül skoru — T2: (symbol, timeframe) çiftinden okur.

    Öncelik: technicals_by_tf[symbol][timeframe] → legacy technicals[symbol].
    DEGRADED teknik → nötr 50 + uyarı (doğrulanmamış sinyalle yön üretme —
    DATA_POLICY).
    """
    warnings: list[str] = []
    t = None
    if snap.technicals_by_tf and symbol in snap.technicals_by_tf:
        t = snap.technicals_by_tf[symbol].get(timeframe)
    if t is None:
        t = snap.technicals.get(symbol)
        if t is not None and timeframe != t.timeframe:
            warnings.append(f"touche_fallback_legacy:{symbol}:{timeframe}")
    if t is None:
        warnings.append(f"touche_no_technicals:{symbol}:{timeframe}")
        return 50.0, warnings
    if getattr(t, "status", "OK") == "DEGRADED":
        warnings.append(f"touche_degraded_neutral:{symbol}:{t.timeframe}")
        return 50.0, warnings
    return t.score, warnings


def _fundamental(regime: RegimeOutput) -> float:
    # likidite + crypto + rotation layer'larının ortalaması
    layers = [layer for layer in regime.layers if layer.name != "Risk İştahı"]
    return sum(layer.score for layer in layers) / max(1, len(layers))


def _news(snap: MarketSnapshot) -> float:
    tally = {"bullish": 0, "bearish": 0, "neutral": 0}
    for h in snap.headlines:
        if h.sentiment:
            tally[h.sentiment] += 1
    total = sum(tally.values())
    if not total:
        return 50.0
    return 50.0 + (tally["bullish"] - tally["bearish"]) / total * 25.0


def _sentinel(regime: RegimeOutput) -> float:
    appetite = next(
        (layer.score for layer in regime.layers if layer.name == "Risk İştahı"),
        50.0,
    )
    return appetite


def _quantum(snap: MarketSnapshot) -> float:
    return snap.rotation.score


MODULE_ORDER = ["touche", "fundamental", "news", "sentinel", "quantum", "chart_pattern"]


def build(
    symbol: str,
    snap: MarketSnapshot,
    regime: RegimeOutput,
    timeframe: str = "1d",
) -> ConsensusResult:
    # T2 — timeframe yalnızca teknik (touche) modülünü farklılaştırır;
    # makro/haber/rotasyon katmanları asset-level kalır. Default "1d" ile
    # mevcut asset-level davranış birebir korunur.
    touche_score, tf_warnings = _touche(symbol, snap, timeframe)
    raw = {
        "touche": touche_score,
        "fundamental": _fundamental(regime),
        "news": _news(snap),
        "sentinel": _sentinel(regime),
        "quantum": _quantum(snap),
        # chart_pattern: şimdilik yok — ağırlığı redistribute edilir
    }
    weights_cfg = load_active_weights()
    base = weights_cfg["regimes"].get(regime.label, weights_cfg["regimes"]["NEUTRAL"])
    available = set(raw.keys())
    w = _redistribute(base, available)
    modules = []
    weighted = 0.0
    for name in MODULE_ORDER:
        if name not in raw:
            continue
        s = raw[name]
        wt = w.get(name, 0.0)
        c = s * wt
        weighted += c
        modules.append(ModuleScore(name=name, score=round(s, 2), weight=round(wt, 4), contribution=round(c, 3)))
    dominant = max(modules, key=lambda m: m.contribution).name if modules else ""
    final = max(0.0, min(100.0, weighted))
    # Confluence: en az 3 modül 50'nin üstünde veya altında aynı yönde
    above = sum(1 for m in modules if m.score >= 55)
    below = sum(1 for m in modules if m.score <= 45)
    confluence = above >= 3 or below >= 3
    return ConsensusResult(
        symbol=symbol,
        score=round(final, 1),
        direction=_direction(final),
        modules=modules,
        confluence_aligned=confluence,
        dominant_module=dominant,
        timeframe=timeframe,
        warnings=tf_warnings,
    )
