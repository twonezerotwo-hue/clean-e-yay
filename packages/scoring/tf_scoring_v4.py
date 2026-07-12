"""tf_scoring_v4 — BİRLEŞİK skorlayıcı, owner formülü (İZOLE, salt-gözlem).

Owner kararı (2026-07-12): dağınık gölge mercekleri TEK formülde birleştir.
Ağırlıklar 600+ kombinasyonluk yürüyen backtest'le bulundu (9 makro sembol,
%70 eğitim / %30 DOĞRULAMA; metrik maruziyet-ağırlıklı birim getiri):

    4h: elliott %36 + trend %28 + bölge(★3+) %12 + yapı %4 + kapılı-uyum %20
        → doğrulama: %65.7 isabet, +1.113/birim  (al-tut: -0.716)
    1d: rsi %40 + trend %20 + bölge(orantılı) %20 + kapılı-uyum %20
        → doğrulama: %54.5 isabet, +0.491/birim  (al-tut: +0.265)

Mercekler (hepsi mevcut altyapıdan REUSE; kopya yok):
- trend  : EMA 20/50/200 dizilimi (sub_leans "trend") — çağıran geçirir
- rsi    : RSI-50 normalize (sub_leans "rsi") — çağıran geçirir
- yapı   : swing zigzag HH/HL+BOS+CHoCH (market_structure.lean) — çağıran geçirir
- elliott: 0-2 son geçerli setup + 0-2 çizgisi konumu (packages.elliott REUSE)
- bölge  : zone_proposer bölgeleri (artifact REUSE — "katmanlar haberdar"):
           1d = kesişim-orantılı güç (★5 tam ses); 4h = ★3+ eşiği (±1)
           [bölge-eşik deneyi: 1d'de sert eşik doğrulamada battı, 4h'de ★3+ iyi]
- kapılı-uyumsuzluk: RSI 2'li(±0.7)/3'lü(±1.0) dip-tepe uyumsuzluğu, YALNIZ
           bölge yakınındayken sayılır (owner grameri: "uyumsuzluk seviyede
           anlamlı"). HAM uyumsuzluk çürüdü (isabet↑ PnL↓); kapılısı ikisini
           birden artırdı — kapı kaldırılmaz.

Konuşmacı seçimi v2'den AYNEN reuse (UP→1d, DOWN→4h; vekâlet yok). İZOLE:
canlı skora/karara/paper'a SIFIR dokunuş; D6 gölge üretici v2/v3 ile YAN YANA
hesaplar, D7 yarışı beş tasarımı ileri veriyle kıyaslar. Terfi = yarış + owner.
"""
from __future__ import annotations

from itertools import pairwise

from packages.elliott import zero_two
from packages.scoring import tf_scoring_v2 as v2

# Doğrulanmış ağırlıklar (yukarıdaki kanıt; anahtarlar lens sözlüğüyle birebir).
WEIGHTS: dict[str, dict[str, float]] = {
    "4h": {"elliott": 36, "trend": 28, "bolge": 12, "yapi": 4, "uyumsuzluk": 20},
    "1d": {"rsi": 40, "trend": 20, "bolge": 20, "uyumsuzluk": 20},
}
MIN_CONVICTION = 0.05   # altı "çağrı yok" (backtest protokolüyle aynı)
ZONE_PROX = 0.03        # bölgeye yakınlık bandı (oransal)
ZONE_MIN_CONF_4H = 3    # 4h bölge eşiği (★3+); 1d orantılı (eşiksiz)
DIV_RECENT = 12         # uyumsuzlukta son pivot tazeliği (bar)
_RSI_PERIOD = 14


# ---------------------------- mercek hesapları ----------------------------

def rsi_series(closes: list[float], period: int = _RSI_PERIOD) -> list | None:
    """Wilder RSI serisi (uyumsuzluk pivot kıyası için; indicators.rsi tek
    değer döndürür — seri gerektiği için burada, aynı Wilder kuralı)."""
    if len(closes) < period + 2:
        return None
    gains, losses = [], []
    for a, b in pairwise(closes):
        ch = b - a
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    out: list = [None] * (period + 1)
    for g, ls in zip(gains[period:], losses[period:], strict=False):
        ag = (ag * (period - 1) + g) / period
        al = (al * (period - 1) + ls) / period
        out.append(100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al))
    return out

def _pivots(vals: list[float], kind: str, left: int = 2, right: int = 2) -> list[int]:
    idx = []
    for i in range(left, len(vals) - right):
        w = vals[i - left: i + right + 1]
        if vals[i] == (min(w) if kind == "low" else max(w)):
            idx.append(i)
    return idx

def rsi_divergence_lean(closes: list[float]) -> float:
    """RSI uyumsuzluğu: fiyat düşen dip + RSI yükselen dip → boğa (2'li +0.7,
    3'lü +1.0); tepe tarafı ayna (eksi). Son pivot DIV_RECENT'ten eskiyse 0.
    NOT: tek başına KULLANILMAZ — yalnız bölge kapısıyla (gated_divergence)."""
    rs = rsi_series(closes)
    if rs is None:
        return 0.0
    n = len(closes)
    best = 0.0
    for kind, sign in (("low", 1.0), ("high", -1.0)):
        piv = [i for i in _pivots(closes, kind) if rs[i] is not None]
        if len(piv) < 2 or n - 1 - piv[-1] > DIV_RECENT:
            continue
        p = piv[-3:]
        if kind == "low":
            two = closes[p[-1]] < closes[p[-2]] and rs[p[-1]] > rs[p[-2]]
            three = (len(p) == 3 and two and closes[p[-2]] < closes[p[-3]]
                     and rs[p[-2]] > rs[p[-3]])
        else:
            two = closes[p[-1]] > closes[p[-2]] and rs[p[-1]] < rs[p[-2]]
            three = (len(p) == 3 and two and closes[p[-2]] > closes[p[-3]]
                     and rs[p[-2]] < rs[p[-3]])
        if three:
            best = sign * 1.0
        elif two and best == 0.0:
            best = sign * 0.7
    return best

def zone_lean(zones: list[dict], px: float, timeframe: str) -> float:
    """Bölge merceği: altımızda yakın bölge = destek (+), üstümüzde = direnç (−).
    1d: güç = kesişim/5 (orantılı — sert eşik doğrulamada battı);
    4h: yalnız ★3+ bölgeler, tam ses (deney: ★3+ en iyi)."""
    out = 0.0
    for z in zones or []:
        try:
            lo, hi, conf = float(z["low"]), float(z["high"]), int(z.get("confluence", 0))
        except (KeyError, TypeError, ValueError):
            continue
        if timeframe == "4h":
            if conf < ZONE_MIN_CONF_4H:
                continue
            c = 1.0
        else:
            c = min(1.0, conf / 5.0)
        if hi <= px and (px - hi) / px <= ZONE_PROX:
            out = c
        elif lo >= px and (lo - px) / px <= ZONE_PROX:
            out = -c
    return out

def gated_divergence(closes: list[float], zone_lean_value: float) -> float:
    """Kapılı uyumsuzluk: bölge yakınında değilsek (zone_lean=0) uyumsuzluk
    SAYILMAZ. Kanıt: ham hâli PnL düşürüyor, kapılısı isabet+PnL artırıyor."""
    if zone_lean_value == 0.0:
        return 0.0
    return rsi_divergence_lean(closes)

def elliott_lean(bars: list) -> float:
    """0-2 merceği: penceredeki en taze geçerli setup — up + fiyat 0-2 çizgisi
    üstünde → +1; down + altında → −1; yoksa/çizgisizse 0 (uydurma yok)."""
    try:
        setups = zero_two.find_setups(bars, left=2, right=2)
    except Exception:
        return 0.0
    if not setups:
        return 0.0
    s = setups[-1]
    lv = zero_two.line_value(s, len(bars) - 1)
    px = bars[-1].close
    if s.direction == "up" and lv > 0 and px > lv:
        return 1.0
    if s.direction == "down" and lv > 0 and px < lv:
        return -1.0
    return 0.0


# ------------------------------- skorlama ---------------------------------

def compute_leans(timeframe: str, bars: list, zones: list[dict],
                  base_leans: dict[str, float]) -> dict[str, float]:
    """v4 lens sözlüğü. `base_leans` = v2.collect_leans çıktısı (trend/rsi/
    structure REUSE — yeniden hesaplanmaz); elliott yalnız 4h'de hesaplanır
    (formülde yalnız orada ağırlığı var — boşa hesap yok)."""
    closes = [b.close for b in bars]
    px = closes[-1] if closes else 0.0
    zl = zone_lean(zones, px, timeframe) if px > 0 else 0.0
    out = {
        "trend": base_leans.get("trend", 0.0),
        "rsi": base_leans.get("rsi", 0.0),
        "yapi": base_leans.get("structure", 0.0),
        "bolge": zl,
        "uyumsuzluk": gated_divergence(closes, zl),
    }
    if timeframe in WEIGHTS and "elliott" in WEIGHTS[timeframe]:
        out["elliott"] = elliott_lean(bars)
    return out

def tf_direction(timeframe: str, leans: dict[str, float]) -> float | None:
    """Bir TF'in v4 yön skoru: sabit doğrulanmış ağırlıklarla harman.
    |skor| < MIN_CONVICTION → None (backtest protokolüyle aynı: çağrı yok)."""
    w = WEIGHTS.get(timeframe)
    if not w:
        return None  # v4 yalnız DIRECTION TF'lerinde tanımlı
    tot = sum(w.values())
    s = sum(wi * leans.get(name, 0.0) for name, wi in w.items()) / tot
    if abs(s) < MIN_CONVICTION:
        return None
    return max(-1.0, min(1.0, s))

def direction(tf_scores: dict[str, float], regime: str | None) -> float | None:
    """Konuşmacı seçimi v2'den AYNEN reuse: UP→1d, DOWN→4h; vekâlet yok."""
    return v2.regime_directed(tf_scores, regime)


__all__ = [
    "MIN_CONVICTION",
    "WEIGHTS",
    "compute_leans",
    "direction",
    "elliott_lean",
    "gated_divergence",
    "rsi_divergence_lean",
    "rsi_series",
    "tf_direction",
    "zone_lean",
]
