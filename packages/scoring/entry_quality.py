"""Giriş kalitesi + dönüş riski — YÖN ≠ GİRİŞ ZAMANLAMASI (YALNIZ KISITLAYICI).

Yön skoru (konsensüs) "hangi yön tercih ediliyor"u söyler; "hemen gir" demek değildir.
Bu katman şu soruyu cevaplar: *yön doğru olsa bile şimdi bu işleme girmek mantıklı mı?*

    yön = bearish  ∧ giriş_kalitesi yüksek ∧ dönüş_riski düşük  → SHORT (değişmez)
    yön = bearish  ∧ giriş_kalitesi düşük                       → WAIT
    yön = bearish  ∧ dönüş_riski yüksek                         → WAIT

KÖTÜ GİRİŞ ASLA ZIT YÖNE ÇEVRİLMEZ: çıktı yalnızca ``ok`` / ``reduce`` (boyut ≤ 1.0) /
``wait`` (aday korunur ama açılmaz). RiskGate'i gevşetmez, boyutu artırmaz, yön üretmez.

Girdi ``entry_context.build`` sözlüğüdür (anlık görüntüye gömülü; yeniden oynatılabilir).
Giriş kalitesi iki parçadan oluşur:

* ``loc``  — işlemin yönündeki aralık ucuna yakınlık (20/60/120 bar). Short için aralığın
  alt ucu, long için üst ucu. TEK BAŞINA ceza değildir: güçlü trendde fiyat uzun süre
  uçta kalır ve devam işlemleri çalışır.
* ``chase`` — uzamayı KANITLAYAN terimlerin noisy-OR birleşimi: ATR-normalize EMA20/EMA50/VWAP
  mesafesi, RSI bandı (yön oyu değil, tükenme/uzama bilgisi), Bollinger konumu, 5-bar hareket
  ve ardışık yönlü impulsive mumlar.

    ceza = chase × (loc_floor + (1 − loc_floor) × loc)       kalite = 1 − ceza

Uç konum + uzama kanıtı birlikteyken ceza tam; yalnız uç konum cezalandırılmaz.
Dönüş riski ``reversal_events.risk_against`` (CHoCH, süpürme, uyumsuzluk, red mumu, geçerli
0-2 kırılımı, climax; yaşa göre sönümlü, noisy-OR).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from packages.data.registry.loader import load_thresholds
from packages.scoring import reversal_events

MODES = ("off", "shadow", "active")
VERDICTS = ("ok", "reduce", "wait")


@dataclass(frozen=True)
class EntryQualityConfig:
    mode: str = "off"
    zero_two_canonical: bool = False
    # --- konum
    range_extreme: float = 0.20
    range_weights: dict[str, float] = field(
        default_factory=lambda: {"20": 0.2, "60": 0.5, "120": 0.3}
    )
    loc_floor: float = 0.4
    # --- uzama terimleri: (başlangıç, tam) ve ağırlık
    ema20: tuple[float, float] = (1.5, 3.5)     # ATR cinsinden yön-yönünde uzaklık
    ema50: tuple[float, float] = (2.5, 6.0)
    vwap: tuple[float, float] = (1.5, 3.5)
    rsi_short: tuple[float, float] = (35.0, 20.0)   # short: RSI düştükçe uzama
    rsi_long: tuple[float, float] = (65.0, 80.0)
    bb_short: tuple[float, float] = (0.10, -0.10)   # %b: alt banda göre
    bb_long: tuple[float, float] = (0.90, 1.10)
    move5: tuple[float, float] = (3.0, 6.0)         # 5-bar hareket (ATR)
    run: tuple[int, int] = (1, 4)                   # ardışık impulsive mum sayısı
    term_weights: dict[str, float] = field(default_factory=lambda: {
        "ema20": 0.5, "ema50": 0.3, "vwap": 0.3, "rsi": 0.5, "bb": 0.4, "move5": 0.4, "run": 0.4,
    })
    # --- karar
    q_wait: float = 0.45
    q_full: float = 0.75
    reversal_wait: float = 0.60
    reversal_reduce_start: float = 0.35
    min_size_factor: float = 0.5
    pullback_bonus: float = 0.10
    pullback_max_age: int = 5
    # Teknik-fallback gecikme bütçesi (ms): değerlendirme bunu aşarsa yeni motor "timeout"
    # sayılır ve legacy zincire düşülür. Saf CPU işi (hazır bağlam) mikrosaniyeler sürer;
    # bütçe yalnız patolojik takılmaları yakalar. Önleyici (preemptive) değil, ölçüm sonrası.
    fallback_max_latency_ms: float = 1000.0


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _ramp(x: float | None, start: float, full: float) -> float:
    """start→0, full→1 doğrusal (full < start ise ters yön de desteklenir)."""
    if x is None or start == full:
        return 0.0
    return _clamp01((x - start) / (full - start))


def config() -> EntryQualityConfig:
    """``thresholds.entry_quality_v2`` → config (blok yok/bozuk → varsayılan = KAPALI)."""
    try:
        raw = load_thresholds().get("entry_quality_v2") or {}
    except (OSError, KeyError, ValueError, TypeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    base = EntryQualityConfig()
    kwargs: dict = {}
    for name in EntryQualityConfig.__dataclass_fields__:
        if name not in raw:
            continue
        default = getattr(base, name)
        v = raw[name]
        try:
            if isinstance(default, tuple):
                kwargs[name] = tuple(type(default[0])(x) for x in v)
            elif isinstance(default, dict):
                kwargs[name] = {str(k): float(x) for k, x in v.items()}
            elif isinstance(default, bool):
                kwargs[name] = bool(v)
            elif isinstance(default, int):
                kwargs[name] = int(v)
            elif isinstance(default, float):
                kwargs[name] = float(v)
            else:
                kwargs[name] = str(v)
        except (TypeError, ValueError):
            continue
    cfg = EntryQualityConfig(**kwargs)
    if cfg.mode not in MODES:
        return EntryQualityConfig()
    return cfg


def mode() -> str:
    return config().mode


def zero_two_canonical() -> bool:
    return config().zero_two_canonical


def _has_non_finite(obj: object) -> bool:
    """Sözlük/liste içinde NaN/±inf var mı? (`_clamp01(NaN)` sessizce 1.0 verir → NaN bir
    bağlam "azami uzama" sayılıp sahte WAIT üretirdi; teknik hata olarak ayrıştırılır.)"""
    if isinstance(obj, bool):
        return False
    if isinstance(obj, float):
        return not math.isfinite(obj)
    if isinstance(obj, dict):
        return any(_has_non_finite(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(_has_non_finite(v) for v in obj)
    return False


def context_problem(ctx: object) -> str | None:
    """Yeni motorun GİRDİSİ teknik olarak kullanılamıyorsa sebep (aksi None).

    Bu bir *piyasa* görüşü değildir: eksik/bozuk veri ``WAIT`` değil, legacy'ye düşme
    (teknik fallback) sebebidir. Sebepler: ``missing_context`` | ``malformed_context`` |
    ``non_finite_context``."""
    if not isinstance(ctx, dict) or not ctx:
        return "missing_context"
    rp = ctx.get("range_pos")
    if not isinstance(rp, dict) or not any(isinstance(v, (int, float)) for v in rp.values()):
        return "missing_context"
    if not isinstance(ctx.get("events", []), list):
        return "malformed_context"
    if _has_non_finite(ctx):
        return "non_finite_context"
    return None


def report_problem(rep: object) -> str | None:
    """``assess`` çıktısı teknik olarak geçersizse sebep (aksi None). Geçerli ``wait`` /
    ``reduce`` burada HATA DEĞİLDİR. Sebepler: ``malformed_report`` | ``invalid_verdict`` |
    ``invalid_<alan>``."""
    if not isinstance(rep, dict):
        return "malformed_report"
    if rep.get("verdict") not in VERDICTS:
        return "invalid_verdict"
    for key in ("entry_quality", "reversal_risk", "size_factor"):
        v = rep.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) \
                or v < 0.0 or v > 1.0:
            return f"invalid_{key}"
    if rep["verdict"] == "reduce" and not 0.0 < rep["size_factor"] <= 1.0:
        return "invalid_size_factor"
    return None


def _location(side: str, rp: dict, cfg: EntryQualityConfig) -> tuple[float, dict]:
    """İşlemin yönündeki aralık ucuna yakınlık (0..1). Short: alt uç, long: üst uç."""
    num = den = 0.0
    detail: dict[str, float] = {}
    for key, w in cfg.range_weights.items():
        p = rp.get(key)
        if p is None:
            continue
        near = p if side == "short" else 1.0 - p            # 0 = ucun tam üstünde
        pen = _clamp01((cfg.range_extreme - near) / cfg.range_extreme) if cfg.range_extreme > 0 else 0.0
        detail[key] = round(pen, 4)
        num += w * pen
        den += w
    return (num / den if den > 0 else 0.0), detail


def _chase(side: str, ctx: dict, cfg: EntryQualityConfig) -> tuple[float, dict]:
    """Uzamayı kanıtlayan terimlerin noisy-OR birleşimi (0..1)."""
    sgn = -1.0 if side == "short" else 1.0    # işlem yönü işareti (fiyat hareketi)
    terms: dict[str, float] = {}

    def _dir_ext(v: float | None) -> float | None:
        return None if v is None else sgn * v   # fiyatın işlem yönünde ortalamadan uzaklığı

    terms["ema20"] = _ramp(_dir_ext(ctx.get("ext_ema20")), *cfg.ema20)
    terms["ema50"] = _ramp(_dir_ext(ctx.get("ext_ema50")), *cfg.ema50)
    terms["vwap"] = _ramp(_dir_ext(ctx.get("ext_vwap")), *cfg.vwap)
    terms["rsi"] = _ramp(ctx.get("rsi"), *(cfg.rsi_short if side == "short" else cfg.rsi_long))
    terms["bb"] = _ramp(ctx.get("bb_pctb"), *(cfg.bb_short if side == "short" else cfg.bb_long))
    terms["move5"] = _ramp(_dir_ext(ctx.get("move5_atr")), *cfg.move5)
    run_dir = ctx.get("run_dir", 0)
    want = 1 if side == "long" else -1
    terms["run"] = _ramp(float(ctx.get("run_len", 0)), *cfg.run) if run_dir == want else 0.0

    prod = 1.0
    for k, s in terms.items():
        prod *= 1.0 - cfg.term_weights.get(k, 0.0) * s
    return 1.0 - prod, {k: round(v, 4) for k, v in terms.items() if v > 0}


def assess(side: str, ctx: dict | None, cfg: EntryQualityConfig | None = None) -> dict:
    """Giriş kalitesi + dönüş riski + karar önerisi (``ok`` | ``reduce`` | ``wait``).

    ``side``: "long" | "short". ``ctx`` yok/eksik → ``ok`` (uydurma ceza yok; sebep yazılır).
    Dönen ``size_factor`` HER ZAMAN ≤ 1.0 (yalnız kısıtlayıcı)."""
    cfg = cfg or config()
    report: dict = {
        "side": side, "entry_quality": None, "reversal_risk": None, "verdict": "ok",
        "size_factor": 1.0, "reasons": [], "location": None, "chase": None,
        "terms": {}, "range_penalty": {}, "events": [],
    }
    if side not in ("long", "short") or not ctx:
        report["reasons"].append("no_context")
        return report

    loc, loc_detail = _location(side, ctx.get("range_pos") or {}, cfg)
    chase, terms = _chase(side, ctx, cfg)
    penalty = chase * (cfg.loc_floor + (1.0 - cfg.loc_floor) * loc)
    quality = 1.0 - penalty

    pb = ctx.get("pullback")
    want_dir = "bullish" if side == "long" else "bearish"
    if pb and pb.get("direction") == want_dir and int(pb.get("age", 99)) <= cfg.pullback_max_age:
        quality = min(1.0, quality + cfg.pullback_bonus)
        report["reasons"].append("zero_two_pullback_bonus")

    risk, labels = reversal_events.risk_against(ctx.get("events") or [], side)

    report.update(
        entry_quality=round(quality, 4), reversal_risk=round(risk, 4),
        location=round(loc, 4), chase=round(chase, 4), terms=terms,
        range_penalty=loc_detail, events=labels,
    )

    factor = 1.0
    verdict = "ok"
    if risk >= cfg.reversal_wait:
        verdict = "wait"
        report["reasons"].append(f"reversal_risk:{risk:.2f}")
    if quality < cfg.q_wait:
        verdict = "wait"
        report["reasons"].append(f"entry_quality:{quality:.2f}")
    if verdict != "wait":
        if quality < cfg.q_full:
            f_q = cfg.min_size_factor + (1.0 - cfg.min_size_factor) * (
                (quality - cfg.q_wait) / max(1e-9, cfg.q_full - cfg.q_wait)
            )
            factor = min(factor, f_q)
        if risk > cfg.reversal_reduce_start:
            f_r = 1.0 - (1.0 - cfg.min_size_factor) * (
                (risk - cfg.reversal_reduce_start)
                / max(1e-9, cfg.reversal_wait - cfg.reversal_reduce_start)
            )
            factor = min(factor, f_r)
        if factor < 1.0:
            verdict = "reduce"
    else:
        factor = 0.0
    report["verdict"] = verdict
    report["size_factor"] = round(max(0.0, min(1.0, factor)), 4)
    return report


__all__ = [
    "MODES",
    "VERDICTS",
    "EntryQualityConfig",
    "assess",
    "config",
    "context_problem",
    "mode",
    "report_problem",
    "zero_two_canonical",
]
