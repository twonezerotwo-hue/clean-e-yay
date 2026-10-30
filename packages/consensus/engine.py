"""Konsensüs motoru — 5 modül, rejim ağırlıklı toplam.

Modüller:
  - touche        (teknik)
  - fundamental   (rejim/makro)
  - news          (haber)
  - sentinel      (volatilite/stres)
  - quantum       (rotasyon)

Not (M5, 2026-07-02): eski `chart_pattern` slotu KALDIRILDI — hiç implement
edilmemişti ve gerçek formasyon tespiti zaten touche içinde çalışıyor
(`technical/timeframe.py` direction_tilt). Ayrı modül aynı kanıtı iki kez
sayardı (M3'teki çifte-sayım hatasının aynısı).

Canlı kanonik akışta eksik modülün ağırlığı artık başka modüle aktarılmaz.
Eksik kanıt yönü nötre çeker; böylece tek bir kalan modül veri yokluğunu
telafi ediyormuş gibi güçlenmez. Eski replay fixture'ları için aktivasyon tarihi
korunur ve tarih öncesi kararlar byte-stable kalır.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

from packages.data.ingestion.pipeline import MarketSnapshot
from packages.data.registry.loader import (
    load_active_weights,
    load_thresholds,
)
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


# T-1 — üst-TF hiza basamağı (Elder triple-screen oranı ~×4-6): her alt dilim
# bir üst basamağın yönüne karşı tartılır. 1d'nin üstü yok (1w snapshot'ta
# hesaplanmıyor — uydurma basamak eklenmez).
_HTF_LADDER = {"15m": "1h", "1h": "4h", "4h": "1d"}
_HTF_NEUTRAL_BAND = 5.0  # üst TF |lean| < 5 → nötr sayılır, sönümleme yok


def _htf_alignment_cfg() -> dict:
    """`technical.htf_alignment` bloğu (enabled default False = bayt-aynı)."""
    try:
        return (load_thresholds().get("technical") or {}).get("htf_alignment") or {}
    except (OSError, KeyError, ValueError, TypeError):
        return {}


def _htf_dampen(
    symbol: str, snap: MarketSnapshot, timeframe: str, score: float
) -> tuple[float, str | None]:
    """T-1 — alt TF skoru üst basamağın yönüne TERSse 50'ye doğru kıs.

    YALNIZ KÜÇÜLTÜR: aynı yön → dokunmaz (boost yok); üst TF nötr/verisiz →
    dokunmaz; yön ASLA çevrilmez (çarpan [min_mult..1.0]). Çarpan her karşıtlıkta
    hesaplanıp warning satırına yazılır (shadow); yalnız flag açıkken uygulanır."""
    htf = _HTF_LADDER.get(timeframe)
    if htf is None:
        return score, None
    t = (snap.technicals_by_tf or {}).get(symbol, {}).get(htf)
    ds = getattr(t, "direction_score", None) if t is not None else None
    if ds is None:
        return score, None
    ltf_lean = score - 50.0
    htf_lean = float(ds) - 50.0
    if ltf_lean == 0.0 or abs(htf_lean) < _HTF_NEUTRAL_BAND:
        return score, None
    if (ltf_lean > 0) == (htf_lean > 0):
        return score, None  # aynı yön — asla boost edilmez
    cfg = _htf_alignment_cfg()
    try:
        min_mult = min(1.0, max(0.0, float(cfg.get("min_mult", 0.6))))
    except (TypeError, ValueError):
        min_mult = 0.6
    strength = min(1.0, abs(htf_lean) / 50.0)  # üst TF ne kadar kararlı
    mult = 1.0 - (1.0 - min_mult) * strength
    adjusted = 50.0 + ltf_lean * mult
    enabled = bool(cfg.get("enabled", False))
    tag = "htf_alignment" if enabled else "htf_alignment_shadow"
    warning = (
        f"{tag}:{symbol}:{timeframe}vs{htf}:htf_score={float(ds):.1f}:"
        f"mult={mult:.3f}:raw={score:.2f}:used={adjusted if enabled else score:.2f}"
    )
    return (adjusted if enabled else score), warning


def _touche(
    symbol: str,
    snap: MarketSnapshot,
    timeframe: str = "1d",
) -> tuple[float, list[str]]:
    """Technical module score for one (symbol, timeframe).

    T-1: taban skor `_touche_base`'ten gelir; üst-TF karşıtlığında flag'li
    sönümleme (`_htf_dampen`) uygulanır — shadow satırı her karşıtlıkta yazılır."""
    score, warnings = _touche_base(symbol, snap, timeframe)
    adjusted, htf_warning = _htf_dampen(symbol, snap, timeframe, score)
    if htf_warning is not None:
        warnings.append(htf_warning)
    return adjusted, warnings


def _touche_base(
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


def _fundamental_v2(regime: RegimeOutput) -> float | None:
    """M3 — fundamental v2: Kripto Momentum katmanı HARİÇ (likidite + rotasyon).

    v1'de BTC'nin 1d teknik skoru hem touche modülünde hem fundamental'in
    içindeki Kripto Momentum katmanında sayılıyordu (çifte sayım). v2 makroyu
    saf tutar. Katman kalmazsa None → modül düşer (redistribute)."""
    layers = [
        layer for layer in regime.layers
        if layer.name not in ("Risk İştahı", "Kripto Momentum")
    ]
    if not layers:
        return None
    return sum(layer.score for layer in layers) / len(layers)


# NOT: fundamental_v3 (rotasyonsuz saf-Likidite) 2026-07-15'te SÖKÜLDÜ — 5y
# tezgâh ÇÜRÜTTÜ (BTC için TERS gösterge, M15 hükmü). Yerine v4.1 momentum
# formülü geldi (rotasyon çifte-sayımını o da çözer, üstelik pozitif edge'le).
# Tezgâh kıyas kaydı macro_backtest.fund_v3'te documented reference olarak kalır.


# v4 memoize: DXY/US10Y bar arşivi dosya-imzası (boyut+mtime) değişmedikçe tick
# içi 20+ hücre tek hesabı paylaşır (sıcak yol; zaman-bağımsız → test-flake yok).
_FUND_V4_MEMO: dict = {"key": None, "val": None}


def _fundamental_v4() -> float | None:
    """Fundamental v4 (GÖLGE) — DEĞİŞİM-bazlı makro likidite (ADAY B, 5y tezgâh).

    2026-07-13 Basamak-4: mevcut Likidite formülü mutlak seviyeye çapalıydı (5y'da
    1118/1118 gün ≥55 — hiç bearish olamıyor). v4 DXY + 10y faizin çoklu-ufuk
    vol-norm momentumundan gelir (yükseliyorsa sıkılaşma = risk-off). Üretici
    `flow.liquidity_momentum_score` (tek kaynak; macro_backtest ADAY B birebir).
    Seri bar arşivinden (asset-level); arşiv yok/kapalı/yetersiz → None → kademe
    v3/v2/v1'e düşer (dürüst degrade). Salt-okur; lazy import."""
    try:
        from packages.data.providers.ohlcv import history

        def _sig(sym: str):
            try:
                st = history._path(sym, "1d").stat()
                return (st.st_size, int(st.st_mtime))
            except OSError:
                return None

        key = (history.enabled(), _sig("DXY"), _sig("US10Y"))
        if _FUND_V4_MEMO["key"] == key:
            return _FUND_V4_MEMO["val"]
        from packages.data.providers.rotation import flow

        dxy = [b.close for b in history.load("DXY", "1d")]
        us10y = [b.close for b in history.load("US10Y", "1d")]
        val = flow.liquidity_momentum_score(dxy, us10y)
        _FUND_V4_MEMO["key"], _FUND_V4_MEMO["val"] = key, val
        return val
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _news_evidence_gap(snap: MarketSnapshot, symbol: str | None) -> str | None:
    """Sembole etkili doğrulanmış başlık yoksa sebep etiketi, varsa None."""
    if symbol is None:
        return "no_symbol"
    has = any(h.verified and symbol in h.asset_impact for h in snap.headlines)
    return None if has else "no_relevant_headlines"


def _news(snap: MarketSnapshot, symbol: str | None = None) -> float | None:
    """Haber modülü skoru (0-100, 50 = nötr): yalnız sembole etkili doğrulanmış başlıklar.

    Yön sembole özgü etkiden gelir (ör. şahin Fed haberi DXY için +1). İlgili
    başlık yoksa modül oy kullanmaz (None → düşer; kanıtsız nötr-50 uydurulmaz)."""
    if symbol is None:
        return None
    vals = [float(h.asset_impact[symbol]) for h in snap.headlines if h.verified and symbol in h.asset_impact]
    if not vals:
        return None
    return 50.0 + (sum(vals) / len(vals)) * 25.0


def _sentinel(regime: RegimeOutput) -> float | None:
    # F2-3: Risk İştahı katmanı düştüyse (VIX verisi yok) nötr-50 uydurulmaz;
    # modül düşer, ağırlığı redistribute edilir. Flag kapalıyken katman hep var.
    return next(
        (layer.score for layer in regime.layers if layer.name == "Risk İştahı"),
        None,
    )


# M4 — sentinel v2: tek-gösterge VIX yerine çok-girdili stres kompoziti.
# Tüm girdiler snapshot'ta ZATEN hesaplanıyor (yeni ağ çağrısı yok); v2 yalnız
# bunları tek 0-100 eksende (yüksek = sakin / risk iştahı) birleştirir.
# Eksik girdi ağırlığı kalanlara redistribute edilir (quantum deseni; DATA_POLICY:
# eksik girdi için skor uydurulmaz). Bileşen ağırlıkları config'ten okunur.
_SENTINEL_V2_DEFAULT_WEIGHTS = {
    "vix": 0.5,          # makro korku endeksi (mevcut v1 girdisi)
    "volatility": 0.25,  # sembolün (symbol, tf) realized-vol z-skoru + shock
    "derivatives": 0.15, # kripto squeeze proxy (yalnız kripto sembolleri)
    "options": 0.10,     # BTC/ETH IV/skew/term stres rejimi
}

# Options stres rejimi → sakinlik skoru (0-100). Sıralama gerekçesi:
# PUT_SKEW_STRESS en stresli (çöküş hedge talebi), RICH_VOL/TERM_STRESS
# yüksek stres, CALL_SKEW_EUPHORIA aşırı iyimserlik (nötr-altı sağlıklı
# değil), CHEAP_VOL/NORMAL sakin.
_OPTIONS_REGIME_CALM = {
    "NORMAL": 70.0,
    "CHEAP_VOL": 60.0,
    "CALL_SKEW_EUPHORIA": 50.0,
    "RICH_VOL": 30.0,
    "TERM_STRESS": 30.0,
    "PUT_SKEW_STRESS": 25.0,
}


def _sentinel_v2_cfg() -> dict:
    """`sentinel_v2` config bloğu (enabled default False = v1 birebir)."""
    try:
        return load_thresholds().get("sentinel_v2") or {}
    except (OSError, KeyError, ValueError, TypeError):
        return {}


def _sentinel_v2(
    regime: RegimeOutput, snap: MarketSnapshot, symbol: str, timeframe: str
) -> float | None:
    """M4 — stres kompoziti (0-100, yüksek = sakin). Girdi yoksa None → modül düşer.

    DATA_POLICY: VIX dışındaki girdiler yalnız verified + status OK ise sayılır
    (fixture/degraded veri karar zincirine girmez)."""
    parts: dict[str, float] = {}
    vix = _sentinel(regime)
    if vix is not None:
        parts["vix"] = float(vix)
    v = (getattr(snap, "volatility", None) or {}).get(symbol, {}).get(timeframe)
    if (
        v is not None
        and getattr(v, "status", None) == "OK"
        and getattr(v, "verified", False)
        and v.vol_zscore is not None
    ):
        # z=0 → 50 nötr; z=-2 (çok sakin) → 100; z=+2 (extreme) → 0. Shock
        # durumunda tavan 25 (ani hareket sakinlik sayılamaz).
        s = max(0.0, min(100.0, 50.0 - 25.0 * float(v.vol_zscore)))
        if getattr(v, "vol_state", "") == "shock":
            s = min(s, 25.0)
        parts["volatility"] = s
    d = (getattr(snap, "derivatives", None) or {}).get(symbol)
    if (
        d is not None
        and getattr(d, "status", None) == "OK"
        and getattr(d, "verified", False)
        and d.squeeze_proxy is not None
    ):
        # squeeze_proxy 0-100 (yüksek = squeeze baskısı) → sakinlik = 100 − proxy.
        parts["derivatives"] = max(0.0, min(100.0, 100.0 - float(d.squeeze_proxy)))
    o = (getattr(snap, "options", None) or {}).get(symbol)
    if o is not None and getattr(o, "status", None) == "OK" and getattr(o, "verified", False):
        calm = _OPTIONS_REGIME_CALM.get(str(getattr(o, "regime", "")))
        if calm is not None:
            parts["options"] = calm
    if not parts:
        return None
    cfg_w = _sentinel_v2_cfg().get("weights") or {}
    base = {
        k: float(cfg_w.get(k, dv)) for k, dv in _SENTINEL_V2_DEFAULT_WEIGHTS.items()
    }
    w = _redistribute(base, set(parts))
    return sum(parts[k] * w.get(k, 0.0) for k in parts)


def _quantum(snap: MarketSnapshot) -> float:
    return snap.rotation.score


def _quantum_v2(snap: MarketSnapshot, symbol: str) -> float | None:
    """Sembolün kesitsel göreceli-güç (para akışı) skoru (0-100) veya None.

    rotation.per_symbol'dan okur (rotation motoru üretir); sembol yoksa/veri
    yetersizse None → çağıran v1 makro tilte düşer (dürüst). getattr ile savunmacı
    (eski kayıt/test snap'inde alan olmayabilir → v1)."""
    per_symbol = getattr(snap.rotation, "per_symbol", None) or {}
    val = per_symbol.get(symbol)
    return float(val) if val is not None else None


_QUANTUM_GATE_DEFAULT_REGIMES = ("OFFENSIVE",)


def _quantum_gate_allowed_regimes() -> set[str]:
    """Quantum'un oy kullanabildiği rejimler (config; default yalnız OFFENSIVE —
    challenger karnesinde kanıtın pozitif olduğu tek rejim; NEUTRAL'da ters)."""
    try:
        raw = load_thresholds().get("consensus", {}).get("quantum_gate_allowed_regimes")
        vals = [str(x).strip().upper() for x in (raw or _QUANTUM_GATE_DEFAULT_REGIMES)]
        return {v for v in vals if v}
    except (OSError, KeyError, ValueError, TypeError):
        return set(_QUANTUM_GATE_DEFAULT_REGIMES)


def _min_module_coverage() -> float:
    """`consensus.min_module_coverage` (default 0.0 = KAPALI = bayt-aynı).

    2026-07-13 dış denetim P1 bulgusu: modül düşünce `_redistribute` ağırlığını
    kalanlara TAM dağıtıyor — veri azaldıkça kalan kanıtlar güçleniyor (ters
    davranış; CRISIS'te sentinel düşerse ~%53 ağırlık diğerlerine şişer).
    0'dan büyükse: mevcut modüllerin TABAN ağırlık toplamı (kapsama) bu eşiğin
    altına düşerse yön nötre zorlanır (işlem açılmaz; skor/modüller raporda
    aynen kalır — yalnız yön kararı kısıtlanır). Kapsama her eksik-modüllü
    hücrede `coverage_observe` satırıyla flag'siz izlenir. Geri-alma = 0.0."""
    try:
        v = load_thresholds().get("consensus", {}).get("min_module_coverage", 0.0)
        return float(v or 0.0)
    except (OSError, KeyError, ValueError, TypeError):
        return 0.0


def _timeframe_module_drop(timeframe: str, generated_at: object | None = None) -> set[str]:
    """Return modules kept observational for a specific timeframe.

    The gate is deliberately narrow and reversible: it removes only modules
    proven inverse in that timeframe, then reuses the existing weight
    redistribution and coverage rules for the remaining evidence.
    """
    try:
        cfg = load_thresholds().get("consensus", {}).get("timeframe_module_drop") or {}
        active_after = cfg.get("active_after")
        if active_after:
            # Historical replays and older synthetic snapshots must retain the
            # legacy decision byte. A live snapshot always carries a timezone-
            # aware generated_at watermark; missing timestamps are legacy-safe.
            if generated_at is None:
                return set()
            from datetime import datetime

            cutoff = datetime.fromisoformat(str(active_after).replace("Z", "+00:00"))
            stamp = generated_at
            if getattr(stamp, "tzinfo", None) is None:
                stamp = stamp.replace(tzinfo=UTC)
            if stamp < cutoff:
                return set()
        raw = cfg.get(str(timeframe)) or []
        return {str(item).strip().lower() for item in raw if str(item).strip()}
    except (OSError, KeyError, TypeError, ValueError):
        return set()


MODULE_ORDER = ["touche", "fundamental", "news", "sentinel", "quantum"]

# Public vocabulary. ``quantum`` is retained as a read/fixture alias so old
# snapshots and weights remain loadable, but every new read model can expose
# the evidence in the name users actually understand.
CANONICAL_MODULE_NAMES = {
    "quantum": "relative_strength_rotation",
}


def canonical_module_name(name: str) -> str:
    return CANONICAL_MODULE_NAMES.get(str(name), str(name))


def _canonical_runtime_enabled() -> bool:
    """Canlı süreç bayrağı (E_YAY_CANONICAL_RUNTIME).

    pytest ve golden replay altında kapalıdır ki geçmiş tekrar üretilebilir
    kalsın. Canlı yolu sınayan testler yalnız bu fonksiyonu monkeypatch'ler;
    politika mantığının geri kalanı aynen koşar.
    """
    if "pytest" in sys.modules:
        return False
    return os.environ.get("E_YAY_CANONICAL_RUNTIME", "").strip().lower() in {"1", "true", "yes", "on"}


def _strict_missing_modules_active(generated_at: object | None) -> bool:
    """Live policy: fixed weights + neutral on missing evidence.

    Historical replay must remain reproducible; live snapshots generated after
    the policy watermark use the strict path. No score is fabricated and no
    remaining module receives a boost.
    """
    if not _canonical_runtime_enabled():
        return False
    try:
        cfg = load_thresholds().get("consensus", {}).get("missing_module_policy") or {}
        if str(cfg.get("mode", "redistribute")).lower() != "fixed":
            return False
        active_after = cfg.get("active_after")
        if not active_after or generated_at is None:
            return False
        cutoff = datetime.fromisoformat(str(active_after).replace("Z", "+00:00"))
        stamp = generated_at
        if getattr(stamp, "tzinfo", None) is None:
            stamp = stamp.replace(tzinfo=UTC)
        return stamp >= cutoff
    except (OSError, KeyError, TypeError, ValueError):
        return False


def build(
    symbol: str,
    snap: MarketSnapshot,
    regime: RegimeOutput,
    timeframe: str = "1d",
) -> ConsensusResult:
    # Teknik modül yalnız (symbol, timeframe) ile değişir; makro, haber ve
    # rotasyon katmanları varlık düzeyindedir. Her modülde tek canlı yol vardır.
    touche_score, tf_warnings = _touche(symbol, snap, timeframe)
    raw = {"touche": touche_score}
    # Politika gereği oy dışı kalan modüller (haber çekimserliği, rejim kapısı,
    # TF düşürme). "Eksik veri" sayılmaz: ağırlıkları kalanlara dağılır.
    policy_dropped: set[str] = set()
    news_score = _news(snap, symbol)
    if news_score is not None:
        raw["news"] = news_score
    else:
        policy_dropped.add("news")
        tf_warnings.append(f"news_abstain:reason={_news_evidence_gap(snap, symbol)}")
    # Temel: v4 (DXY + 10y faiz momentumu); bar arşivi yoksa v2 (likidite + rotasyon).
    fund_v4 = _fundamental_v4()
    fundamental = fund_v4 if fund_v4 is not None else _fundamental_v2(regime)
    if fund_v4 is None and fundamental is not None:
        tf_warnings.append(f"fundamental_fallback:v2:{symbol}:{timeframe}")
    if fundamental is not None:
        raw["fundamental"] = fundamental
    else:
        tf_warnings.append(f"fundamental_dropped:no_macro_layers:{symbol}:{timeframe}")
    # Sentinel: çok girdili stres kompoziti (VIX + oynaklık + türev + opsiyon).
    sentinel = _sentinel_v2(regime, snap, symbol, timeframe)
    if sentinel is not None:
        raw["sentinel"] = sentinel
    else:
        tf_warnings.append(f"sentinel_dropped:no_risk_appetite_layer:{symbol}:{timeframe}")
    # Quantum: sembol-başı göreceli güç (veri yoksa makro eğim); yalnız izinli
    # rejimlerde oy kullanır, aksi halde düşer (nötr-50 uydurulmaz).
    if snap.rotation.status != "UNAVAILABLE":
        q2 = _quantum_v2(snap, symbol)
        q_score = q2 if q2 is not None else _quantum(snap)
        if regime.label in _quantum_gate_allowed_regimes():
            raw["quantum"] = q_score
        else:
            tf_warnings.append(f"quantum_dropped:regime_gate:{regime.label}:{symbol}")
            policy_dropped.add("quantum")

    # Timeframe calibration gate: the current clean cohort marks selected
    # modules inverse on 4h. Keep their scores in the shadow trace, but remove
    # them from that timeframe's live vote until a new canary proves otherwise.
    # Weight redistribution and the existing coverage guard remain authoritative.
    for module in sorted(_timeframe_module_drop(timeframe, getattr(snap, "generated_at", None))):
        policy_dropped.add(module)
        if module in raw:
            dropped_score = float(raw.pop(module))
            # The live vote no longer uses this inverse module, but retain its
            # measured value in the warning stream so shadow/replay telemetry
            # can prove when the calibration gate should be removed.
            tf_warnings.append(
                f"timeframe_module_drop:{timeframe}:{module}:score={dropped_score:.1f}"
            )

    weights_cfg = load_active_weights()
    base = weights_cfg["regimes"].get(regime.label, weights_cfg["regimes"]["NEUTRAL"])
    available = set(raw.keys())
    # Coverage is always reported against the configured base weights. In the
    # live canonical policy, missing evidence keeps its configured weight at
    # zero (no redistribution) and the cell is forced neutral. Historical
    # snapshots retain the old normalized path for golden-replay stability.
    base_total = sum(float(v) for v in base.values()) or 1.0
    coverage = sum(float(base.get(k, 0.0)) for k in available) / base_total
    min_cov = _min_module_coverage()
    coverage_forced_neutral = bool(min_cov > 0.0 and coverage < min_cov)
    if coverage < 1.0 - 1e-9:
        tf_warnings.append(
            f"coverage_observe:cov={coverage:.2f}:min={min_cov:.2f}:"
            f"applied={'yes' if coverage_forced_neutral else 'no'}"
        )
    # Verisi gelmeyen modüller (politika düşürmesi değil). Sabit-ağırlık
    # politikasında bunlar kendi ağırlıklarıyla nötr 50 sayılır: ölçek korunur,
    # yön uydurulmaz, kalan modüllere ağırlık şişirilmez ve hücre nötre zorlanır.
    data_missing = sorted(
        name for name in base
        if name not in available and name not in policy_dropped and float(base.get(name, 0.0)) > 0
    )
    neutral_fill: dict[str, float] = {}
    strict_missing = _strict_missing_modules_active(getattr(snap, "generated_at", None))
    if strict_missing and data_missing:
        voting = _redistribute(base, available | set(data_missing))
        w = {name: voting[name] for name in available}
        neutral_fill = {name: voting[name] for name in data_missing}
        tf_warnings.append("missing_module_policy:fixed:neutral_fill=" + ",".join(data_missing))
        coverage_forced_neutral = True
        tf_warnings.append("coverage_gate:forced_neutral:reason=missing_module")
    else:
        w = _redistribute(base, available)
    modules = []
    weighted = 50.0 * sum(neutral_fill.values())
    for name in MODULE_ORDER:
        if name not in raw:
            continue
        s = raw[name]
        wt = w.get(name, 0.0)
        c = s * wt
        weighted += c
        modules.append(ModuleScore(name=name, score=round(s, 2), weight=round(wt, 4), contribution=round(c, 3)))
    # Baskın modül: nötr-50 merkezli yön katkısı |skor−50|×ağırlık (ayı modül de baskın olabilir).
    dominant = max(modules, key=lambda m: abs((m.score - 50.0) * m.weight)).name if modules else ""
    final = max(0.0, min(100.0, weighted))
    # Yön etiketi trade aksiyon eşikleriyle aynı banttan (tek kaynak) okunur.
    cons_th = load_thresholds().get("consensus", {})
    bullish_min = float(cons_th.get("bullish_min", 55.0))
    bearish_max = float(cons_th.get("bearish_max", 45.0))
    # Confluence (bugfix 2026-07-02, owner onayı): en az 3 modül SİNYALİN KENDİ
    # yönünde hemfikir olmalı. Eski kod yön ayrımı yapmıyordu (above>=3 OR
    # below>=3) — 3 modül işlemin TERSİNE hizalıyken bile "uyumlu" sayıp boyut
    # yarılamasını atlıyordu. Nötr sinyalde taraf yok → False (işlem de yok).
    # Modül eşikleri de artık aksiyon eşikleriyle aynı config bandından okunur
    # (eskiden 55/45 sabitti — owner eşiği değiştirince sessizce ayrışırdı).
    above = sum(1 for m in modules if m.score >= bullish_min)
    below = sum(1 for m in modules if m.score <= bearish_max)
    if final >= bullish_min:
        confluence = above >= 3
    elif final <= bearish_max:
        confluence = below >= 3
    else:
        confluence = False
    direction = _direction(final, bullish_min, bearish_max)
    if coverage_forced_neutral and direction != "neutral":
        # Kapsama eşiği altı: kanıt tabanı incelmiş — yön kararı verilmez
        # (skor/modüller raporda aynen kalır; yalnız işlem-açıcı yön kısıtlanır).
        tf_warnings.append(f"coverage_gate:forced_neutral:was={direction}")
        direction = "neutral"
        confluence = False
    return ConsensusResult(
        symbol=symbol,
        score=round(final, 1),
        direction=direction,
        modules=modules,
        confluence_aligned=confluence,
        dominant_module=dominant,
        timeframe=timeframe,
        warnings=tf_warnings,
    )
