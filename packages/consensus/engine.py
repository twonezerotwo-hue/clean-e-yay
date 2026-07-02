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
from datetime import UTC, datetime

from packages.data.ingestion.pipeline import MarketSnapshot
from packages.data.registry.loader import load_active_weights, load_thresholds
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


def _direction(s: float, bullish_min: float = 55.0, bearish_max: float = 45.0) -> str:
    """Yön etiketi — trade aksiyon eşikleriyle (consensus.bullish_min/bearish_max)
    AYNI banttan okunur. Eskiden 60/40 sabitti ama aksiyon eşiği 55/45'e
    gevşetilmişti (2026-06-20); bu uyumsuzluk [40,45] ölü-bandında "neutral signal"
    yazıp short açtırıyordu. Artık etiket ↔ aksiyon tek kaynak: short açılan her
    skor (≤bearish_max) "bearish", long açılan her skor (≥bullish_min) "bullish"."""
    if s >= bullish_min:
        return "bullish"
    if s <= bearish_max:
        return "bearish"
    return "neutral"


def _redistribute(weights: dict[str, float], available: set[str]) -> dict[str, float]:
    keep = {k: v for k, v in weights.items() if k in available}
    total = sum(keep.values())
    if total <= 0:
        # eşit dağıt
        return {k: 1.0 / max(1, len(available)) for k in available}
    return {k: v / total for k, v in keep.items()}


_STALE_AFTER_SEC = {
    "15m": 1800,
    "1h": 7200,
    "4h": 28800,
    "1d": 172800,
    "1w": 864000,
}


def _technical_degraded_reasons(t: object, timeframe: str) -> list[str]:
    reasons: list[str] = []
    bars_used = int(getattr(t, "bars_used", 0) or 0)
    if bars_used <= 0:
        reasons.append("no_bars")
    elif bars_used < 200:
        reasons.append(f"limited_bars:{bars_used}")
    if getattr(t, "rsi", None) is None:
        reasons.append("rsi_missing")
    if getattr(t, "macd", None) is None:
        reasons.append("macd_missing")
    if getattr(t, "atr", None) is None:
        reasons.append("atr_missing")
    if getattr(t, "ema_stack", None) is None:
        reasons.append("ema_stack_missing")

    ts = getattr(t, "ts", None)
    stale_after = _STALE_AFTER_SEC.get(timeframe)
    if isinstance(ts, datetime) and stale_after is not None:
        ts_utc = ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
        age_sec = (datetime.now(UTC) - ts_utc.astimezone(UTC)).total_seconds()
        if age_sec > stale_after:
            reasons.append(f"stale_bar:{int(age_sec)}s")
    return reasons or ["degraded"]


def _degraded_direction_score(raw_score: float, reasons: list[str]) -> tuple[float, float]:
    """Use degraded technical direction, but pull it toward neutral confidence."""
    factor = 0.80
    if any(r in reasons for r in ("no_bars", "rsi_missing", "macd_missing", "atr_missing")):
        factor = min(factor, 0.55)
    if any(r.startswith("stale_bar:") for r in reasons):
        factor = min(factor, 0.70)
    if any(r.startswith("limited_bars:") for r in reasons):
        factor = min(factor, 0.80)
    if "ema_stack_missing" in reasons:
        factor = min(factor, 0.80)
    adjusted = 50.0 + ((raw_score - 50.0) * factor)
    return max(0.0, min(100.0, adjusted)), factor


def _touche(
    symbol: str,
    snap: MarketSnapshot,
    timeframe: str = "1d",
) -> tuple[float, list[str]]:
    """Technical module score for one (symbol, timeframe).

    Priority: technicals_by_tf[symbol][timeframe] -> legacy technicals[symbol].
    DEGRADED snapshots with direction_score keep direction but are dampened toward
    neutral and surfaced through warnings. Without direction_score, fallback is 50.
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
    # Top-down gated direction (momentum trigger + location/pattern/volume gate) is
    # the authoritative technical read; fall back to legacy `score` (RSI+MACD only)
    # when the gated score is unavailable (older snapshots / insufficient momentum).
    ds = getattr(t, "direction_score", None)
    if getattr(t, "status", "OK") == "DEGRADED":
        if ds is not None:
            reasons = _technical_degraded_reasons(t, timeframe)
            adjusted, factor = _degraded_direction_score(float(ds), reasons)
            warnings.append(
                "touche_degraded_dampened:"
                f"{symbol}:{t.timeframe}:raw={float(ds):.2f}:used={adjusted:.2f}:"
                f"factor={factor:.2f}:reasons={','.join(reasons)}"
            )
            return adjusted, warnings
        warnings.append(f"touche_degraded_neutral:{symbol}:{t.timeframe}:no_direction_score")
        return 50.0, warnings
    if ds is not None:
        return ds, warnings
    warnings.append(f"touche_legacy_score_fallback:{symbol}:{t.timeframe}")
    return t.score, warnings


def _fundamental(regime: RegimeOutput) -> float:
    # likidite + crypto + rotation layer'larının ortalaması
    layers = [layer for layer in regime.layers if layer.name != "Risk İştahı"]
    return sum(layer.score for layer in layers) / max(1, len(layers))


def _news_symbol_filter_enabled() -> bool:
    """consensus.news_symbol_filter — owner-flag (default KAPALI = eski davranış).

    Açıkken _news yalnız o sembole `asset_impact` taşıyan VERIFIED başlıkları
    sayar (DATA_POLICY: verified=False consensus'a girmez). Kapalıyken global
    sentiment tally'si birebir korunur (bozulma yok, tek satır geri dönüş)."""
    try:
        return bool(load_thresholds().get("consensus", {}).get("news_symbol_filter", False))
    except (OSError, KeyError, ValueError, TypeError):
        return False


def _news(snap: MarketSnapshot, symbol: str | None = None) -> float:
    """Haber modülü skoru (0-100, 50 = nötr).

    Sembol-ilişkili mod (news_symbol_filter açık + symbol verilmiş): yalnız
    `headline.asset_impact[symbol]` taşıyan verified başlıklar sayılır; yön
    global sentiment yerine sembole özgü impact'ten gelir (örn. hawkish Fed
    haberi bearish sentiment'lidir ama DXY için +1). İlgili başlık yoksa 50
    (nötr) — asset_impact haritasında olmayan semboller (örn. custom hisseler)
    alakasız küresel haber gürültüsüyle OYNAMAZ.

    Legacy mod (flag kapalı veya symbol None): tüm başlıkların sentiment
    tally'si — mevcut davranış birebir."""
    if symbol is not None and _news_symbol_filter_enabled():
        vals = [
            float(h.asset_impact[symbol])
            for h in snap.headlines
            if h.verified and symbol in h.asset_impact
        ]
        if not vals:
            return 50.0
        return 50.0 + (sum(vals) / len(vals)) * 25.0
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
        "news": _news(snap, symbol),
        "sentinel": _sentinel(regime),
        # chart_pattern: şimdilik yok — ağırlığı redistribute edilir
    }
    # Rotasyon UNAVAILABLE ise quantum modülü düşer; ağırlığı _redistribute
    # ile diğer modüllere dağıtılır (mock skor karar zincirine girmez).
    if snap.rotation.status != "UNAVAILABLE":
        raw["quantum"] = _quantum(snap)
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
    # Yön etiketi trade aksiyon eşikleriyle aynı banttan (tek kaynak) okunur.
    cons_th = load_thresholds().get("consensus", {})
    return ConsensusResult(
        symbol=symbol,
        score=round(final, 1),
        direction=_direction(
            final,
            float(cons_th.get("bullish_min", 55.0)),
            float(cons_th.get("bearish_max", 45.0)),
        ),
        modules=modules,
        confluence_aligned=confluence,
        dominant_module=dominant,
        timeframe=timeframe,
        warnings=tf_warnings,
    )
