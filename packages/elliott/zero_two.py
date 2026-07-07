"""0-2 çizgi etkileşim dedektörü — owner edge'inin çekirdek primitifi (EVIDENCE only).

Owner'ın takdirî Elliott+Fib yönteminin ilk makineleştirilebilir parçası:
0-1-2 pivot dizisini bulur, 0 ile 2'yi birleştiren çizgiyi ileri uzatır ve
sonraki barların bu çizgiyle etkileşimini İKİLİ DEĞİL, derecelendirilmiş
sınıflar (owner spec'i: "fitil mi kapanış mı" pozisyon büyüklüğü ve stop
mesafesini belirler):

- ``WICK_TOUCH``  : fitil çizgiye değdi, kapanış trend tarafında kaldı → zayıf
- ``CLOSE_BREAK`` : kapanış çizginin öbür tarafına geçti → güçlü

Geçerlilik kuralı (owner, 2026-07-07): 0-2 çizgisine 1. dalganın ve 3.
dalganın HİÇBİR mumu değemez. Yani:
- P0→P1 arası mumlardan biri çizgiye değerse → setup İPTAL (IPTAL_DALGA1).
- P2 sonrası, dalga 3 henüz P1'i aşmadan çizgiye değme olursa → İPTAL
  (IPTAL_DALGA3). Sinyal sayılan değme, ancak dalga 3 P1'i AŞTIKTAN sonra
  geri gelen düzeltmenin (owner sayımıyla ABC) değmesidir.

Bu modül:
- HİÇBİR trade açmaz, hiçbir skora/consensus'a karışmaz, karar hattına bağlı
  DEĞİLDİR (packages/elliott/engine.py ile aynı "EVIDENCE only" deseni).
- Pivot teyidi gecikmelidir: P2 ancak ``right`` bar sonra bilinir; bu yüzden
  etkileşim taraması P2'nin TEYİT edildiği bardan başlar (look-ahead yok).
- Uydurma seviye/pivot yok: yetersiz veri → boş liste (DATA_POLICY).
"""
from __future__ import annotations

from dataclasses import dataclass

from packages.data.types import OHLCVBar
from packages.elliott.pivots import Pivot, alternating_pivots

# Owner yöntemi Fib-bağlamlı: P2'nin dalga-1 geri çekilmesi hangi orana yakın?
_FIB_RATIOS: tuple[float, ...] = (0.382, 0.5, 0.618, 0.786)

TouchKind = str  # "WICK_TOUCH" | "CLOSE_BREAK"


@dataclass(frozen=True)
class ZeroTwoSetup:
    """Teyitli 0-1-2 dizisi + 0-2 çizgisinin geometrisi."""

    direction: str  # "up" (0=low,1=high,2=low) | "down" (ayna)
    p0: Pivot
    p1: Pivot
    p2: Pivot
    retrace_ratio: float  # P2'nin dalga-1'i geri çekme oranı (0..1 arası beklenir)
    nearest_fib: float  # _FIB_RATIOS içinden en yakını
    fib_distance: float  # |retrace_ratio - nearest_fib|


@dataclass(frozen=True)
class LineTouch:
    """Tek barın 0-2 çizgisiyle etkileşimi."""

    bar_index: int
    ts: str | None
    kind: TouchKind
    line_price: float  # çizginin o bardaki değeri
    bar_low: float
    bar_high: float
    bar_close: float
    close_distance_pct: float  # kapanışın çizgiye imzalı uzaklığı (%; + = trend tarafı)


# Setup durumu — owner'ın geçerlilik kuralının sonucu.
STATUS_VALID = "GECERLI"
STATUS_WAVE1_TOUCH = "IPTAL_DALGA1"  # dalga-1 mumu çizgiye değdi
STATUS_WAVE3_TOUCH = "IPTAL_DALGA3"  # dalga 3 P1'i aşmadan çizgiye değme oldu


@dataclass(frozen=True)
class ZeroTwoEvent:
    """Bir setup + geçerlilik durumu + çizgi etkileşimleri (kronolojik).

    ``touches`` yalnız GECERLI setuplarda dolu olabilir ve yalnız dalga 3
    P1'i aştıktan SONRAKİ değmeleri içerir. CLOSE_BREAK görülünce tarama
    durur — çizgi kapanışla kırıldıktan sonra aynı çizgiye yeni "değme"
    saymak yanıltıcı olur.
    """

    setup: ZeroTwoSetup
    status: str
    wave3_extreme: float | None  # P1'i aşan uç fiyat (aştıysa)
    touches: list[LineTouch]


def _nearest_fib(ratio: float) -> tuple[float, float]:
    best = min(_FIB_RATIOS, key=lambda r: abs(ratio - r))
    return best, round(abs(ratio - best), 4)


def find_setups(
    bars: list[OHLCVBar], *, left: int = 3, right: int = 3
) -> list[ZeroTwoSetup]:
    """Alternatif pivot dizisinden geçerli 0-1-2 adaylarını çıkar.

    Geçerlilik = Elliott hard-rule'unun 0-2 kısmı: dalga 2, dalga 1'in
    başlangıcını (P0) İHLAL EDEMEZ; ederse o dizi aday bile değildir.
    """
    piv = alternating_pivots(bars, left=left, right=right)
    out: list[ZeroTwoSetup] = []
    for a, b, c in zip(piv, piv[1:], piv[2:], strict=False):
        if c.bar_index <= a.bar_index:
            continue  # aynı barda çift pivot birleşimi — geometri çizilemez
        if a.kind == "low" and b.kind == "high" and c.kind == "low":
            if b.price > a.price and a.price < c.price < b.price:
                ratio = (b.price - c.price) / (b.price - a.price)
                fib, dist = _nearest_fib(ratio)
                out.append(
                    ZeroTwoSetup("up", a, b, c, round(ratio, 3), fib, dist)
                )
        elif a.kind == "high" and b.kind == "low" and c.kind == "high":
            if b.price < a.price and b.price < c.price < a.price:
                ratio = (c.price - b.price) / (a.price - b.price)
                fib, dist = _nearest_fib(ratio)
                out.append(
                    ZeroTwoSetup("down", a, b, c, round(ratio, 3), fib, dist)
                )
    return out


def line_value(setup: ZeroTwoSetup, bar_index: int) -> float:
    """0-2 çizgisinin verilen bar indeksindeki fiyatı (ileri uzatılmış)."""
    span = setup.p2.bar_index - setup.p0.bar_index
    slope = (setup.p2.price - setup.p0.price) / span
    return setup.p0.price + slope * (bar_index - setup.p0.bar_index)


def wave1_clean(bars: list[OHLCVBar], setup: ZeroTwoSetup) -> bool:
    """Dalga-1 mumları (P0 hariç, P1 dahil) çizgiye değmemiş mi?

    P0 barı çizgiyi tanımladığı için değme sayılmaz; P1 dahil aradaki her
    mumun fitili bile çizgiye değerse kural ihlalidir (owner: "hiçbir mumu").
    """
    up = setup.direction == "up"
    for j in range(setup.p0.bar_index + 1, setup.p1.bar_index + 1):
        lv = line_value(setup, j)
        if (bars[j].low <= lv) if up else (bars[j].high >= lv):
            return False
    return True


def scan(
    bars: list[OHLCVBar],
    setup: ZeroTwoSetup,
    *,
    right: int = 3,
    max_bars: int | None = None,
) -> tuple[str, float | None, list[LineTouch]]:
    """P2 sonrası durum makinesi → (status, wave3_extreme, touches).

    Fazlar:
    - DALGA-3 BEKLENİYOR: P1 henüz aşılmadı. Bu fazda çizgiye değme →
      IPTAL_DALGA3 (dalga-3 mumu çizgiye değemez). Aynı barda hem P1 aşımı
      hem değme varsa muhafazakâr yorum: değme sayılır, iptal.
    - KURULU (armed): dalga 3 P1'i aştı; artık geri gelen düzeltmenin
      değmeleri SİNYALDİR. Sinyal ancak P2 pivot teyidinden sonra
      (``p2.bar_index + right`` sonrası) raporlanır — look-ahead yok.
      CLOSE_BREAK'te tarama durur.
    """
    if not wave1_clean(bars, setup):
        return STATUS_WAVE1_TOUCH, None, []

    up = setup.direction == "up"
    p1 = setup.p1.price
    confirm_from = setup.p2.bar_index + right + 1
    end = len(bars)
    if max_bars is not None:
        end = min(end, setup.p2.bar_index + 1 + max_bars)

    armed = False
    extreme: float | None = None
    out: list[LineTouch] = []
    for j in range(setup.p2.bar_index + 1, end):
        lv = line_value(setup, j)
        if lv <= 0:
            break  # çizgi anlamsız bölgeye uzadı (dik negatif eğim)
        bar = bars[j]
        touched = bar.low <= lv if up else bar.high >= lv
        if not armed:
            if touched:
                return STATUS_WAVE3_TOUCH, extreme, []
            if (bar.high > p1) if up else (bar.low < p1):
                armed = True
                extreme = bar.high if up else bar.low
            continue
        extreme = max(extreme, bar.high) if up else min(extreme, bar.low)  # type: ignore[arg-type]
        if not touched or j < confirm_from:
            continue
        broke = bar.close < lv if up else bar.close > lv
        signed = (bar.close - lv) / lv * 100.0
        out.append(
            LineTouch(
                bar_index=j,
                ts=bar.ts.isoformat() if bar.ts else None,
                kind="CLOSE_BREAK" if broke else "WICK_TOUCH",
                line_price=round(lv, 6),
                bar_low=bar.low,
                bar_high=bar.high,
                bar_close=bar.close,
                close_distance_pct=round(signed if up else -signed, 4),
            )
        )
        if broke:
            break
    return STATUS_VALID, extreme, out


def analyze(
    bars: list[OHLCVBar],
    *,
    left: int = 3,
    right: int = 3,
    max_scan_bars: int | None = None,
) -> list[ZeroTwoEvent]:
    """Tüm 0-1-2 setuplarını bul, geçerlilik kuralını uygula, değmeleri döndür."""
    out: list[ZeroTwoEvent] = []
    for s in find_setups(bars, left=left, right=right):
        status, extreme, touches = scan(bars, s, right=right, max_bars=max_scan_bars)
        out.append(ZeroTwoEvent(setup=s, status=status, wave3_extreme=extreme, touches=touches))
    return out


__all__ = [
    "STATUS_VALID",
    "STATUS_WAVE1_TOUCH",
    "STATUS_WAVE3_TOUCH",
    "LineTouch",
    "ZeroTwoEvent",
    "ZeroTwoSetup",
    "analyze",
    "find_setups",
    "line_value",
    "scan",
    "wave1_clean",
]
