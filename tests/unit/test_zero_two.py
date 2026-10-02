"""0-2 çizgi dedektörü + karne testleri (owner edge'i, kalibrasyon 2026-07-07).

Sentetik bar geometrileriyle her kural ayrı doğrulanır:
- 0-1-2 aday bulma (yukarı/aşağı) + dalga-2 P0 ihlali eleme
- Geçerlilik: dalga-1 mumu çizgiye değerse İPTAL; dalga 3 P1'i aşmadan
  değme olursa İPTAL; sinyal ancak dalga-3 uzaması SONRASI değmede
- Fitil (WICK_TOUCH) vs kapanış-geçiş (CLOSE_BREAK) sınıflaması
- T2 kırılım işlemi: baktest girişi, 0-noktası stop'u, 1.618 hedefi
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.types import OHLCVBar
from packages.elliott import zero_two

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(i: int, o: float, h: float, lo: float, c: float) -> OHLCVBar:
    return OHLCVBar(
        symbol="TEST", timeframe="4h", ts=_T0 + timedelta(hours=4 * i),
        open=o, high=h, low=lo, close=c, volume=1.0,
    )


def _walk(path: list[float], spread: float = 0.4) -> list[OHLCVBar]:
    """Kapanış patikasından bar üret: high/low kapanışın ± spread'i (fitilsiz değil)."""
    return [_bar(i, c, c + spread, c - spread, c) for i, c in enumerate(path)]


def _up_setup_path() -> list[float]:
    """P0 dip (100) → P1 tepe (110) → P2 dip (105): temiz yukarı 0-1-2.

    Pivot teyidi için uçların iki yanında 3'er bar var; dalga-1 çizgiden
    (P0→P2 doğrusu) uzak dursun diye çıkış dik tutulur.
    """
    return [
        104, 103, 102, 100, 103, 106, 109,   # P0 = index 3 (dip 100), hızlı kalkış
        110, 109, 108, 107, 106, 105,        # P1 = index 7 (tepe 110), iniş
        106, 107, 108,                       # P2 = index 12 (dip 105), dönüş
    ]


def test_find_setups_up_and_down():
    bars = _walk(_up_setup_path())
    setups = zero_two.find_setups(bars)
    ups = [s for s in setups if s.direction == "up"]
    assert ups, "yukarı 0-1-2 bulunmalıydı"
    s = ups[0]
    assert s.p0.price < s.p2.price < s.p1.price
    # ayna: fiyatları 210'dan çıkar → aşağı setup
    mirror = _walk([210 - p for p in _up_setup_path()])
    downs = [s for s in zero_two.find_setups(mirror) if s.direction == "down"]
    assert downs, "aşağı 0-1-2 bulunmalıydı"


def test_wave2_breaching_p0_is_not_a_candidate():
    # P2 (98) P0'ın (100) altına iniyor → Elliott hard-rule ihlali, aday bile değil.
    path = [104, 103, 102, 100, 103, 106, 109, 110, 108, 106, 104, 101, 98, 100, 101, 102]
    setups = zero_two.find_setups(_walk(path))
    assert all(s.direction != "up" or s.p2.price > s.p0.price for s in setups)


def _line_at(s: zero_two.ZeroTwoSetup, j: int) -> float:
    return zero_two.line_value(s, j)


def test_wave1_touch_invalidates():
    """Dalga-1 mumunun fitili 0-2 çizgisine değerse setup İPTAL_DALGA1."""
    bars = _walk(_up_setup_path())
    s = next(x for x in zero_two.find_setups(bars) if x.direction == "up")
    # dalga-1 içinden bir barın low'unu çizgiye indir (fitil değmesi)
    j = s.p0.bar_index + 2
    lv = _line_at(s, j)
    b = bars[j]
    bars[j] = _bar(j, b.open, b.high, lv - 0.01, b.close)
    status, _, touches = zero_two.scan(bars, s)
    assert status == zero_two.STATUS_WAVE1_TOUCH
    assert touches == []


def test_wave3_touch_before_extension_invalidates():
    """P2 sonrası, dalga 3 daha P1'i aşmadan çizgiye değme → İPTAL_DALGA3."""
    path = _up_setup_path()
    bars = _walk(path)
    s = next(x for x in zero_two.find_setups(bars) if x.direction == "up")
    j = len(path)  # P2 sonrası ilk ek bar
    lv = _line_at(s, j)
    bars.append(_bar(j, 108, 108.4, lv - 0.01, 108))  # P1 (110) aşılmadı ama değdi
    status, _, touches = zero_two.scan(bars, s)
    assert status == zero_two.STATUS_WAVE3_TOUCH
    assert touches == []


def _extended_bars() -> tuple[list[OHLCVBar], zero_two.ZeroTwoSetup]:
    """Geçerli setup + P1'i aşan dalga 3 (114'e) → tetikte bekleyen çizgi."""
    path = [*_up_setup_path(), 109, 111, 113, 114, 113, 112]
    bars = _walk(path)
    s = next(x for x in zero_two.find_setups(bars) if x.direction == "up")
    return bars, s


def test_valid_setup_wick_touch_then_close_break():
    bars, s = _extended_bars()
    n = len(bars)
    # düzeltme çizgiye iner: önce fitil değmesi (kapanış üstte kalır)...
    lv1 = _line_at(s, n)
    bars.append(_bar(n, 111, 111.3, lv1 - 0.05, 111))
    # ...sonra kapanışla geçiş
    lv2 = _line_at(s, n + 1)
    bars.append(_bar(n + 1, 110, 110.5, lv2 - 1.0, lv2 - 0.5))
    status, extreme, touches = zero_two.scan(bars, s)
    assert status == zero_two.STATUS_VALID
    assert extreme == 114.4  # dalga-3 ucu (114 + 0.4 spread)
    assert [t.kind for t in touches] == ["WICK_TOUCH", "CLOSE_BREAK"]
    # kapanış-geçişten sonra tarama durur
    assert touches[-1].bar_index == n + 1


def test_wick_touch_needs_wave3_extension_first():
    """Aynı geometri ama dalga 3 P1'i aşmıyor → değme sinyal değil, İPTAL."""
    path = [*_up_setup_path(), 108, 109, 109, 108]  # 110'u aşamadı
    bars = _walk(path)
    s = next(x for x in zero_two.find_setups(bars) if x.direction == "up")
    j = len(bars)
    bars.append(_bar(j, 108, 108.3, _line_at(s, j) - 0.05, 108))
    status, _, touches = zero_two.scan(bars, s)
    assert status == zero_two.STATUS_WAVE3_TOUCH
    assert touches == []


