"""Dönüş (reversal) OLAYLARI — durum değil olay: yön, bar, güç, güven, YAŞ, sönüm.

Neden: mevcut katmanlar dönüş bilgisini "kalıcı durum" olarak taşır (``reversal.bias``,
``market_structure.choch`` fiyat seviyenin ötesinde kaldıkça 50+ bar aktif kalır) ve
skoru en çok ×0.6 kısar. Bu modül her kanıtı bir OLAY olarak üretir (kaç bar önce,
ne kadar güçlü) ve ağırlığı deterministik olarak yaşla söndürür: eski sinyal sonsuza
kadar aktif kalmaz.

Olay türleri (hepsi çağıranın verdiği KAPANMIŞ barlardan; look-ahead yok — olay,
sistemin onu gerçekten bilebileceği barda damgalanır):

- ``choch``          : karakter değişimi (market_structure.break_events — tek tanım)
- ``failed_break``   : teyitli swing seviyesinin fitille süpürülüp kapanışla geri
                       alınması (likidite süpürme / BOS başarısızlığı)
- ``divergence``     : RSI uyumsuzluğu (tf_scoring_v4.rsi_divergence_events — tek tanım)
- ``rejection``      : swing seviyesinde dönüş mumu (candles: pin bar / engulfing)
- ``zero_two_break`` : GEÇERLİ 0-2 setup'ında çizginin kapanışla kırılması
                       (zero_two.analyze — tek geçerlilik tanımı; geçersiz setup olay üretmez)
- ``climax``         : yönlü büyük mum (≥1.5 ATR) + aşırı hacim (≥2×) / menzil (≥2.5 ATR) /
                       ATR genişlemesi (≥1.6×) + 60-bar aralığın ucu (tükenme/capitulation olayı)

Ayrıca ``pullback`` bilgisi (geçerli, kurulu 0-2'de ÇİZGİYE FİTİL değmesi = trend
yönünde geri çekilme girişi) döner; dönüş değil devam kanıtıdır.

SAF fonksiyonlar; karara bağlı DEĞİL — ``entry_quality`` yalnızca KISITLAYICI okur.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from packages.data.providers.technical import candles, indicators
from packages.data.types import OHLCVBar
from packages.elliott import zero_two
from packages.scoring import tf_scoring_v4
from packages.signals import market_structure

# Olay yarı-ömrü (bar) ve güven önceliği (türün tarihsel güvenilirlik varsayımı;
# 5y çok-rejim ölçümü olmadan "kanıtlandı" denmez → bunlar BAŞLANGIÇ varsayımıdır,
# ölçüm raporu docs/ içinde; ağırlıklar owner/karne ile değişir).
HALF_LIFE_BARS: dict[str, float] = {
    "choch": 8.0,
    "failed_break": 5.0,
    "divergence": 10.0,
    "rejection": 4.0,
    "zero_two_break": 8.0,
    "climax": 4.0,
}
CONFIDENCE: dict[str, float] = {
    "choch": 0.70,
    "failed_break": 0.60,
    "divergence": 0.50,
    "rejection": 0.45,
    "zero_two_break": 0.50,
    "climax": 0.40,
}
# Yaş bu kat × yarı-ömrü aşınca olay tamamen düşer (sonsuz aktiflik yok).
MAX_AGE_HALF_LIVES = 3.0

_MIN_BARS = 30
_SCAN_BARS = 8          # failed_break / climax / rejection için geriye bakış
_ZERO_TWO_WINDOW = 400  # 0-2 taraması penceresi (canlı bar penceresiyle aynı mertebe)
_ZERO_TWO_MAX_SETUP_AGE = 120  # P2'den bu kadar bar sonra setup bayat


@dataclass(frozen=True)
class ReversalEvent:
    kind: str
    direction: str       # bullish (fiyat yukarı dönebilir) | bearish
    bar_index: int
    age: int             # son bara göre kaç bar önce bilindi
    strength: float      # 0..1 ham kanıt gücü
    confidence: float    # 0..1 türün güvenilirlik varsayımı
    ts: str | None = None   # olayın bilindiği barın zamanı (ISO)

    def weight(self) -> float:
        """Yaşla deterministik sönümlü ağırlık: güç × güven × 0.5^(yaş/yarı-ömür)."""
        hl = HALF_LIFE_BARS[self.kind]
        if self.age < 0 or self.age > MAX_AGE_HALF_LIVES * hl:
            return 0.0
        return self.strength * self.confidence * 0.5 ** (self.age / hl)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "direction": self.direction, "age": self.age, "ts": self.ts,
            "strength": round(self.strength, 4), "confidence": round(self.confidence, 4),
            "half_life": HALF_LIFE_BARS[self.kind], "weight": round(self.weight(), 4),
        }


def decayed_weight(kind: str, age: int, strength: float, confidence: float | None = None) -> float:
    """Anlık görüntüden (dict) okunan olay için aynı sönüm formülü — tek tanım."""
    conf = CONFIDENCE[kind] if confidence is None else confidence
    return ReversalEvent(kind, "bullish", 0, age, strength, conf).weight()


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _choch_events(bars: list[OHLCVBar], atr: float) -> list[ReversalEvent]:
    out: list[ReversalEvent] = []
    n = len(bars)
    for br in market_structure.break_events(bars):
        if br.kind != "choch":
            continue
        margin_atr = (br.margin / atr) if atr > 0 else 0.0
        strength = 0.6 + 0.2 * _clamp01(margin_atr) + 0.2 * _clamp01(br.prior_streak / 4.0)
        if not br.still_beyond:
            strength *= 0.5  # kırılım sonradan geri alınmış: kanıt zayıf
        out.append(ReversalEvent(
            "choch", br.direction, br.bar_index, (n - 1) - br.bar_index,
            _clamp01(strength), CONFIDENCE["choch"],
        ))
    return out


def _failed_break_events(bars: list[OHLCVBar], atr: float) -> list[ReversalEvent]:
    """Teyitli swing tepesi fitille aşılıp kapanış seviyenin ALTINA dönerse bearish
    (dip için ayna bullish). Kapanışın seviyenin ötesine geçip ≤3 bar içinde geri
    dönmesi (BOS başarısızlığı) da aynı olaydır. Olay, geri-alan kapanış barında bilinir."""
    n = len(bars)
    out: list[ReversalEvent] = []
    highs, lows = market_structure.swing_levels(bars)
    right = 2
    for kind_levels, bearish in ((highs[-3:], True), (lows[-3:], False)):
        best: ReversalEvent | None = None
        for p_idx, level in kind_levels:
            for j in range(max(p_idx + right + 1, n - _SCAN_BARS), n):
                b = bars[j]
                pierced = (b.high > level) if bearish else (b.low < level)
                if not pierced:
                    continue
                # geri-alan kapanış: aynı bar veya sonraki ≤3 bar
                for k in range(j, min(n, j + 4)):
                    reclaimed = (bars[k].close < level) if bearish else (bars[k].close > level)
                    if reclaimed:
                        excess = (b.high - level) if bearish else (level - b.low)
                        s = 0.5 + 0.5 * _clamp01(excess / atr if atr > 0 else 0.0)
                        ev = ReversalEvent(
                            "failed_break", "bearish" if bearish else "bullish",
                            k, (n - 1) - k, s, CONFIDENCE["failed_break"],
                        )
                        if best is None or ev.bar_index > best.bar_index:
                            best = ev
                        break
        if best is not None:
            out.append(best)
    return out


def _divergence_events(bars: list[OHLCVBar]) -> list[ReversalEvent]:
    closes = [b.close for b in bars]
    n = len(closes)
    out: list[ReversalEvent] = []
    for signed, piv_idx in tf_scoring_v4.rsi_divergence_events(closes):
        known = min(n - 1, piv_idx + 2)   # pivot right=2 bar sonra teyit olur
        out.append(ReversalEvent(
            "divergence", "bullish" if signed > 0 else "bearish",
            known, (n - 1) - known, abs(signed), CONFIDENCE["divergence"],
        ))
    return out


def _rejection_events(bars: list[OHLCVBar], atr: float) -> list[ReversalEvent]:
    """Son birkaç barda dönüş mumu, YALNIZ teyitli swing seviyesine ≤1 ATR uzaktaysa
    (seviyede değilse mum gürültüdür — candles.py modül notuyla aynı ilke)."""
    n = len(bars)
    if atr <= 0:
        return []
    highs, lows = market_structure.swing_levels(bars)
    out: list[ReversalEvent] = []
    seen: set[str] = set()
    for age in range(0, 3):
        end = n - age
        if end < 3:
            break
        sig = candles.detect(bars[:end])
        if sig is None:
            continue
        b = bars[end - 1]
        if sig.bias == "BULLISH":
            near = any(abs(b.low - lv) <= atr for _, lv in lows[-4:])
            direction = "bullish"
        else:
            near = any(abs(b.high - lv) <= atr for _, lv in highs[-4:])
            direction = "bearish"
        if near and direction not in seen:
            seen.add(direction)
            strength = 0.7 if "engulfing" in sig.name else 0.5
            out.append(ReversalEvent(
                "rejection", direction, end - 1, age, strength, CONFIDENCE["rejection"],
            ))
    return out


def _zero_two(bars: list[OHLCVBar]) -> tuple[list[ReversalEvent], dict | None]:
    """GEÇERLİ setup'lardan dönüş olayı + devam (pullback) bilgisi. Geçersiz/bayat
    setup hiçbir şey üretmez (tek geçerlilik tanımı: zero_two.analyze)."""
    window = bars[-_ZERO_TWO_WINDOW:]
    n = len(window)
    events: list[ReversalEvent] = []
    pullback: dict | None = None
    try:
        analyzed = zero_two.analyze(window)
    except Exception:
        return [], None
    for ev in analyzed:
        if ev.status != zero_two.STATUS_VALID or ev.wave3_extreme is None:
            continue   # geçersiz veya dalga 3 henüz P1'i aşmadı → kurulu değil
        if (n - 1) - ev.setup.p2.bar_index > _ZERO_TWO_MAX_SETUP_AGE:
            continue   # bayat
        for t in ev.touches:
            age = (n - 1) - t.bar_index
            if t.kind == "CLOSE_BREAK":
                direction = "bearish" if ev.setup.direction == "up" else "bullish"
                events.append(ReversalEvent(
                    "zero_two_break", direction, t.bar_index, age,
                    0.7, CONFIDENCE["zero_two_break"],
                ))
            elif t.kind == "WICK_TOUCH":
                cand = {"direction": "bullish" if ev.setup.direction == "up" else "bearish",
                        "age": age}
                if pullback is None or age < pullback["age"]:
                    pullback = cand
    # her yönde en taze olay
    best: dict[str, ReversalEvent] = {}
    for e in events:
        if e.direction not in best or e.age < best[e.direction].age:
            best[e.direction] = e
    return list(best.values()), pullback


def volume_ratio(bars: list[OHLCVBar], i: int) -> float | None:
    """Barın hacmi / önceki 20 barın ortalaması. Hacim yoksa (FX/CFD) None — uydurma yok."""
    b = bars[i]
    if b.volume is None or i < 10:
        return None
    vols = [x.volume for x in bars[max(0, i - 20):i] if x.volume is not None]
    if len(vols) < 10:
        return None
    mean = sum(vols) / len(vols)
    return (b.volume / mean) if mean > 0 else None


def atr_expansion(bars: list[OHLCVBar]) -> float | None:
    """Kısa (5) / uzun (14) ortalama gerçek aralık oranı — oynaklık patlaması göstergesi."""
    if len(bars) < 16:
        return None
    trs = [
        max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
        for p, c in zip(bars[-15:-1], bars[-14:], strict=True)
    ]
    long_ = sum(trs) / len(trs)
    return (sum(trs[-5:]) / 5.0) / long_ if long_ > 0 else None


def _climax_events(bars: list[OHLCVBar], atr: float) -> list[ReversalEvent]:
    """Tükenme olayı: büyük yönlü gövde (≥1.5 ATR) + aşırı hacim (≥2×) YA DA aşırı menzil
    (≥2.5 ATR) + 60-bar aralığın ucu. Aşağı climax → bullish dönüş adayı (ayna)."""
    n = len(bars)
    if atr <= 0 or n < 60:
        return []
    out: list[ReversalEvent] = []
    for age in range(0, _SCAN_BARS):
        i = n - 1 - age
        if i < 60:
            break
        b = bars[i]
        body = (b.close - b.open) / atr
        rng = (b.high - b.low) / atr
        vr = volume_ratio(bars, i)
        ar = atr_expansion(bars[:i + 1])
        loud = (vr is not None and vr >= 2.0) or rng >= 2.5 or (ar is not None and ar >= 1.6)
        if not loud or abs(body) < 1.5:
            continue
        win = bars[i - 59:i + 1]
        lo = min(x.low for x in win)
        hi = max(x.high for x in win)
        pos = (b.close - lo) / (hi - lo) if hi > lo else 0.5
        if body < 0 and pos <= 0.20:
            out.append(ReversalEvent("climax", "bullish", i, age, _clamp01(abs(body) / 3.0), CONFIDENCE["climax"]))
        elif body > 0 and pos >= 0.80:
            out.append(ReversalEvent("climax", "bearish", i, age, _clamp01(abs(body) / 3.0), CONFIDENCE["climax"]))
    best: dict[str, ReversalEvent] = {}
    for e in out:
        if e.direction not in best or e.age < best[e.direction].age:
            best[e.direction] = e
    return list(best.values())


def detect(bars: list[OHLCVBar]) -> tuple[list[ReversalEvent], dict | None]:
    """Tüm dönüş olayları + (varsa) 0-2 pullback bilgisi. Yetersiz veri → ([], None)."""
    if len(bars) < _MIN_BARS:
        return [], None
    atr = indicators.atr(bars) or 0.0
    events: list[ReversalEvent] = []
    events += _choch_events(bars, atr)
    events += _failed_break_events(bars, atr)
    events += _divergence_events(bars)
    events += _rejection_events(bars, atr)
    zz_events, pullback = _zero_two(bars)
    events += zz_events
    events += _climax_events(bars, atr)
    events = [
        replace(e, ts=bars[e.bar_index].ts.isoformat()) if 0 <= e.bar_index < len(bars) else e
        for e in events
    ]
    return events, pullback


def risk_against(events: list[dict] | list[ReversalEvent], side: str) -> tuple[float, list[str]]:
    """``side`` işlemine karşı dönüş riski (0..1) + katkı yapan olayların etiketleri.

    Short için BULLISH, long için BEARISH olaylar risktir. Her tür için en güçlü (sönümlü)
    olay alınır; türler arası birleşim noisy-OR: 1 − Π(1 − w). Böylece bağımsız kanıt
    türleri (CHoCH + uyumsuzluk + süpürme ...) birikir, aynı türün tekrarı birikmez."""
    against = "bullish" if side == "short" else "bearish"
    per_kind: dict[str, float] = {}
    for e in events:
        if isinstance(e, ReversalEvent):
            kind, direction, w = e.kind, e.direction, e.weight()
        else:
            kind, direction = e["kind"], e["direction"]
            w = decayed_weight(kind, int(e["age"]), float(e["strength"]), e.get("confidence"))
        if direction != against or w <= 0.0:
            continue
        per_kind[kind] = max(per_kind.get(kind, 0.0), w)
    prod = 1.0
    for w in per_kind.values():
        prod *= 1.0 - w
    labels = [f"{k}:{w:.2f}" for k, w in sorted(per_kind.items(), key=lambda kv: -kv[1])]
    return 1.0 - prod, labels


__all__ = [
    "CONFIDENCE",
    "HALF_LIFE_BARS",
    "ReversalEvent",
    "atr_expansion",
    "decayed_weight",
    "detect",
    "risk_against",
    "volume_ratio",
]
