"""tf_scoring_v4 testleri — owner birleşik formülü (backtest-doğrulanmış ağırlıklar).

Kapsam: RSI uyumsuzluğu (boğa 2'li dip), bölge kapısı (kapısız uyumsuzluk
SAYILMAZ), bölge merceği TF varyantları (1d orantılı / 4h ★3+ eşiği),
ağırlık harmanı + MIN_CONVICTION, konuşmacı seçimi (v2 reuse).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from packages.data.types import OHLCVBar
from packages.scoring import tf_scoring_v4 as v4

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _bars(closes, tf="4h"):
    out = []
    for i, c in enumerate(closes):
        out.append(OHLCVBar(symbol="T", timeframe=tf, ts=_T0 + timedelta(hours=4 * i),
                            open=c, high=c + 0.5, low=c - 0.5, close=c, volume=1.0))
    return out


def _bull_div_closes():
    """Fiyat: sert düşüşle dip (90) → tepki → SIĞ düşüşle daha DÜŞÜK dip (89.5).
    Fiyat LL, RSI HL → boğa uyumsuzluğu."""
    flat = [100.0] * 16                       # RSI ısınması
    steep = [100, 97, 94, 91, 90]             # sert iniş → derin RSI
    bounce = [92, 94]
    shallow = [93, 91, 89.5]                  # sığ iniş → daha yüksek RSI dibi
    tail = [91, 93]                           # pivot sağ-teyidi + tazelik
    return flat + steep + bounce + shallow + tail


def test_rsi_series_direction():
    up = v4.rsi_series([100 + i for i in range(30)])
    dn = v4.rsi_series([100 - i * 0.5 for i in range(30)])
    assert up[-1] > 60 and dn[-1] < 40
    assert v4.rsi_series([1, 2, 3]) is None   # yetersiz → None (uydurma yok)


def test_bullish_divergence_detected():
    lean = v4.rsi_divergence_lean(_bull_div_closes())
    assert lean > 0            # boğa uyumsuzluğu
    assert lean in (0.7, 1.0)  # 2'li ya da 3'lü


def test_divergence_stale_pivot_is_zero():
    closes = _bull_div_closes() + [93.0] * 20   # son pivot 12 bardan eski
    assert v4.rsi_divergence_lean(closes) == 0.0


def test_gated_divergence_requires_zone():
    """Kanıt: ham uyumsuzluk PnL düşürür — bölge kapısı olmadan SAYILMAZ."""
    closes = _bull_div_closes()
    assert v4.gated_divergence(closes, 0.0) == 0.0            # bölge yok → 0
    assert v4.gated_divergence(closes, 0.6) > 0               # bölgede → sayılır


def test_zone_lean_variants():
    zones = [{"low": 95.0, "high": 97.0, "confluence": 3},
             {"low": 110.0, "high": 112.0, "confluence": 5}]
    # 1d: orantılı güç — altta ★3 destek (fiyat 98, %3 içinde) → +3/5
    assert v4.zone_lean(zones, 98.0, "1d") == pytest.approx(0.6)
    # 4h: ★3+ eşiği, tam ses
    assert v4.zone_lean(zones, 98.0, "4h") == 1.0
    # üstte ★5 direnç (fiyat 109) → eksi
    assert v4.zone_lean(zones, 109.0, "1d") == pytest.approx(-1.0)
    # 4h eşiği: ★2 bölge sayılmaz
    assert v4.zone_lean([{"low": 95, "high": 97, "confluence": 2}], 98.0, "4h") == 0.0
    # uzak bölge → 0
    assert v4.zone_lean(zones, 130.0, "1d") == 0.0


def test_tf_direction_weights_and_conviction():
    # 1d: rsi%40+trend%20+bölge%20+uyum%20 — hepsi +1 → +1.0
    full = {"rsi": 1.0, "trend": 1.0, "bolge": 1.0, "uyumsuzluk": 1.0}
    assert v4.tf_direction("1d", full) == 1.0
    # yalnız rsi +1 → 40/100 = 0.4
    assert v4.tf_direction("1d", {"rsi": 1.0}) == pytest.approx(0.4)
    # cılız skor → None (çağrı yok — backtest protokolü)
    assert v4.tf_direction("1d", {"rsi": 0.1}) is None
    # v4 yalnız DIRECTION TF'lerinde tanımlı
    assert v4.tf_direction("15m", full) is None
    # 4h: elliott%36 tek başına → 0.36
    assert v4.tf_direction("4h", {"elliott": 1.0}) == pytest.approx(0.36)


def test_compute_leans_reuses_base_and_gates():
    bars = _bars(_bull_div_closes())
    px = bars[-1].close
    zones = [{"low": px * 0.98, "high": px * 0.99, "confluence": 4}]
    base = {"trend": -1.0, "rsi": 0.3, "structure": 0.5}
    leans = v4.compute_leans("4h", bars, zones, base)
    assert leans["trend"] == -1.0 and leans["rsi"] == 0.3
    assert leans["yapi"] == 0.5                      # structure → yapı eşlemesi
    assert leans["bolge"] == 1.0                     # ★4 destek altta (4h eşik)
    assert leans["uyumsuzluk"] > 0                   # bölgede uyumsuzluk sayıldı
    assert "elliott" in leans                        # 4h formülünde var
    leans_1d = v4.compute_leans("1d", bars, [], base)
    assert leans_1d["bolge"] == 0.0
    assert leans_1d["uyumsuzluk"] == 0.0             # bölge yok → kapı kapalı
    assert "elliott" not in leans_1d                 # 1d formülünde yok (boşa hesap yok)


def test_direction_speaker_reuse():
    scores = {"1d": 0.5, "4h": -0.4}
    assert v4.direction(scores, "UP") == 0.5     # UP → 1d konuşur
    assert v4.direction(scores, "DOWN") == -0.4  # DOWN → 4h konuşur
    assert v4.direction({"1d": 0.5}, "DOWN") is None   # vekâlet yok
    assert v4.direction(scores, None) is None
