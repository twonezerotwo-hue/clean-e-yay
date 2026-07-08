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
from packages.learning import zero_two_scorecard

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


def test_t2_break_retest_trade_hits_fib_target():
    """T2: kapanış-geçiş → baktest → giriş; hedef 1.618, stop 0 noktası.

    Aşağı setup'ın (düşen çizgi) yukarı kırılımı → LONG (owner semantiği:
    işlem kırılım yönüne). Baktest sonrası fiyat 1.618 hedefine yürür.
    """
    up = _up_setup_path()
    down_path = [210 - p for p in up] + [101, 99, 97, 96, 97, 98]  # dalga 3 aşağı (96 < P1=100)
    bars = _walk(down_path)
    s = next(x for x in zero_two.find_setups(bars) if x.direction == "down")
    n = len(bars)
    # kapanışla yukarı geçiş (CLOSE_BREAK)
    lv = _line_at(s, n)
    bars.append(_bar(n, 99, lv + 1.0, 98.8, lv + 0.8))
    # baktest: çizgiye değ + üstünde kapan
    lv2 = _line_at(s, n + 1)
    bars.append(_bar(n + 1, lv2 + 0.5, lv2 + 0.7, lv2 - 0.1, lv2 + 0.6))
    # rally: hedefe yürü (bolca yukarı bar)
    for k in range(2, 12):
        base = lv2 + 0.6 + k * 1.5
        bars.append(_bar(n + k, base, base + 1.0, base - 0.5, base + 0.8))
    events = [e for e in zero_two.analyze(bars) if e.setup == s]
    assert events and events[0].status == zero_two.STATUS_VALID
    trade = zero_two_scorecard.t2_trade(bars, events[0])
    assert trade is not None
    assert trade["hit"] == "hedef"
    assert trade["r"] > 0


def test_t1_wick_trade_break_direction():
    """T1: fitil değmesi → kırılım yönüne, fitil-ucu tetikli işlem üretir."""
    bars, s = _extended_bars()
    n = len(bars)
    lv1 = _line_at(s, n)
    bars.append(_bar(n, 111, 111.3, lv1 - 0.05, 111))  # fitil değmesi
    # sonraki bar fitil barının ALTINI kırar (yukarı setup → short tetiği)...
    touch_low = lv1 - 0.05
    bars.append(_bar(n + 1, 110.8, 110.9, touch_low - 0.3, touch_low - 0.2))
    # ...ve aşağı yürüyüş (1R+ hedefleri doldursun)
    for k in range(2, 10):
        base = touch_low - 0.2 - k * 1.2
        bars.append(_bar(n + k, base + 0.3, base + 0.5, base - 0.5, base))
    events = [e for e in zero_two.analyze(bars) if e.setup == s]
    assert events and events[0].status == zero_two.STATUS_VALID
    trades = zero_two_scorecard.t1_trades(bars, events[0])
    assert trades, "fitil işlemi üretilmeliydi"
    assert trades[0]["results"][1.0] >= 1.0  # 1R hedefi doldu


def test_elliott_flags_on_t2_setup():
    """Elliott teyit bayrakları: dalga1/dalga3 oranları + P2 fib uyumu.

    Sentetik aşağı setup: dalga1 = 10 (110→100), dalga3 ucu 95.6 → |dalga3| =
    9.4 < dalga1 → en-kısa-değil kuralı TUTMAZ; P2 geri çekilmesi %50 → fib
    uyumlu (0.5'e sapma 0.014).
    """
    up = _up_setup_path()
    down_path = [210 - p for p in up] + [101, 99, 97, 96, 97, 98]
    bars = _walk(down_path)
    s = next(x for x in zero_two.find_setups(bars) if x.direction == "down")
    n = len(bars)
    lv = _line_at(s, n)
    bars.append(_bar(n, 99, lv + 1.0, 98.8, lv + 0.8))
    ev = next(e for e in zero_two.analyze(bars) if e.setup == s)
    assert ev.status == zero_two.STATUS_VALID
    flags = zero_two_scorecard.elliott_flags(ev)
    assert flags["dalga3_en_kisa_degil"] is False  # 9.4 < 10
    assert flags["dalga3_uzatmali"] is False
    assert flags["p2_fib_uyumlu"] is True  # retrace 0.5, sapma 0.014 ≤ 0.05


def test_run_if_due_skip_fresh(tmp_path, monkeypatch):
    """Taze artifact varken yeniden ölçmez (interval kapısı)."""
    art = tmp_path / "zero_two_scorecard.json"
    monkeypatch.setenv("ZERO_TWO_SCORECARD_PATH", str(art))
    art.write_text(
        f'{{"generated_at": "{datetime.now(UTC).isoformat()}", "engine": "{zero_two_scorecard._ENGINE}"}}',
        encoding="utf-8",
    )
    out = zero_two_scorecard.run_if_due()
    assert out["status"] == "SKIP_FRESH"
