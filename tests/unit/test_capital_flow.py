"""capital_flow motoru (packages.data.providers.rotation.flow) birim testleri.

Rotasyon motorunun 5 zaafini kapatan yeni cekirdek — coklu-ufuk, hacim-onayli,
tum sinyaller, kredi ekseni, kanit-agirlikli. Pure; look-ahead yok.
"""
from __future__ import annotations

from packages.data.providers.rotation import flow


def _rising(n=140, start=100.0, step=0.5):
    return [start + step * i for i in range(n)]


def _falling(n=140, start=200.0, step=0.5):
    return [start - step * i for i in range(n)]


# ── vol_norm_momentum ────────────────────────────────────────────────────────

def test_momentum_sign_and_clamp():
    assert flow.vol_norm_momentum(_rising()) > 0
    assert flow.vol_norm_momentum(_falling()) < 0
    # duz-yukari + dusuk vol → buyuk ama _SIGNAL_CLAMP'e kirpik
    assert abs(flow.vol_norm_momentum(_rising())) <= flow._SIGNAL_CLAMP


def test_momentum_insufficient_history():
    assert flow.vol_norm_momentum(_rising(n=50)) is None
    assert flow.vol_norm_momentum([]) is None


# ── volume_confirm ───────────────────────────────────────────────────────────

def test_volume_confirm_high_recent_boosts():
    base = [100.0] * 40
    spike = base[:-5] + [300.0] * 5   # son 5 bar hacim patlamasi
    assert flow.volume_confirm(spike) > 1.0
    assert flow.volume_confirm(base) == 1.0            # sabit → notr
    assert flow.volume_confirm(None) == 1.0            # yok → notr (degrade)
    assert flow.volume_confirm([1.0] * 5) == 1.0       # yetersiz → notr


# ── asset_signal (hacim yalniz guvenilir sembolde) ───────────────────────────

def test_asset_signal_volume_only_for_reliable():
    # Momentum clamp'e OTURMASIN diye gurultulu-iniş serisi (carpan gorunur kalsin).
    closes = [100.0 - 0.1 * i + (2.0 if i % 3 == 0 else -2.0) for i in range(140)]
    lo_vol = [100.0] * 140
    hi_vol = [100.0] * 135 + [400.0] * 5
    # SPY guvenilir (rotasyon anahtari) → hacim carpani uygulanir (sinyal degisir)
    s_reliable = flow.asset_signal("SPY", closes, hi_vol)
    s_plain = flow.asset_signal("SPY", closes, lo_vol)
    assert s_reliable != s_plain
    # BTC guvenilmez → hacim yok sayilir (carpandan bagimsiz, ayni)
    assert flow.asset_signal("BTC", closes, hi_vol) == flow.asset_signal("BTC", closes, None)


# ── credit_signal (HYG/LQD orani) ────────────────────────────────────────────

def test_credit_signal_hy_outperform_is_riskon():
    hyg = _rising(step=0.6)   # HY daha hizli → oran yukari → risk-on (+)
    lqd = _rising(step=0.2)
    assert flow.credit_signal(hyg, lqd) > 0
    assert flow.credit_signal(_rising(n=50), _rising(n=50)) is None  # yetersiz


# ── flow_score (agirlikli ortalama, bounded) ─────────────────────────────────

def test_flow_score_weighted_and_bounded():
    # Tum risk-on sinyaller pozitif → skor > 50; defansif negatif katkiyla dengeli.
    sig = {"BTC": 2.0, "SPY": 2.0, "CREDIT": 2.0, "GLD": -2.0, "TLT": -2.0}
    s = flow.flow_score(sig)
    assert 50.0 < s <= 100.0
    # Ters: defansifler yukselirse (risk-off) skor < 50
    sig2 = {"BTC": -2.0, "SPY": -2.0, "GLD": 2.0, "TLT": 2.0, "DXY": 2.0}
    assert flow.flow_score(sig2) < 50.0


def test_flow_score_none_when_no_active_weight():
    # Yalniz agirligi 0 olan sinyaller → None (uydurma yon yok)
    assert flow.flow_score({"XAG": 2.0, "OIL": 2.0}) is None
    assert flow.flow_score({}) is None


def test_flow_score_custom_weights():
    # Backtest agirliklari enjekte edilebilir (kanit-agirlikli sozlesme)
    s = flow.flow_score({"BTC": 2.0}, weights={"BTC": 2.0})
    assert s > 50.0


# ── build_signals (ham seri → SIGNAL_KEYS) ───────────────────────────────────

def test_build_signals_produces_keys_and_credit():
    closes = {
        "BTC": _rising(), "GLD": _falling(), "SPY": _rising(),
        "HYG": _rising(step=0.6), "LQD": _rising(step=0.2),
        "TLT": _rising(n=50),  # yetersiz → atlanir
    }
    sig = flow.build_signals(closes)
    assert "BTC" in sig and "SPY" in sig and "CREDIT" in sig
    assert "TLT" not in sig            # yetersiz veri → uydurma yok
    assert all(k in flow.SIGNAL_KEYS for k in sig)
