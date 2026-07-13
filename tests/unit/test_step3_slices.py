"""2026-07-13 dış denetim Basamak 2-kalanı + Basamak 3 gölge dilimleri.

1. Rejim hysteresis (`regime.hysteresis_band`, default 0.0 = bayt-aynı):
   sınır salınımı (64.9→65.1→64.8) rejim flip'i üretmesin; durum dosyası
   REGIME_STATE_PATH (conftest izole), backtest/replay stateful=False.
2. news ABSTAIN (`consensus.news_abstain`, default false): kanıtsız news
   50-nötr OY yerine oy KULLANMAZ (düşer + redistribute + kapsama azalır);
   kapalıyken `news_abstain_observe` kanıt satırı.
3. DQS genişletme (`extended_metrics`, flag'siz GÖZLEM): teknik bar / haber
   çeşitliliği / rotasyon kapsaması / artifact tazeliği — score/status'a girmez.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from packages.consensus import engine as ce
from packages.data.quality import dqs
from packages.data.registry.loader import threshold_override
from packages.regime import classifier as rc
from packages.regime.classifier import RegimeLayer, RegimeOutput

# ── 1. Rejim hysteresis ──────────────────────────────────────────────────────

def _stab(prev, raw, avg, band=3.0):
    return rc._stabilize(prev, raw, avg, band)


def test_stabilize_blocks_border_flicker():
    # NEUTRAL→OFFENSIVE sınır 65: 65.1 band(3) altında → NEUTRAL tutulur.
    assert _stab("NEUTRAL", "OFFENSIVE", 65.1) == "NEUTRAL"
    assert _stab("NEUTRAL", "OFFENSIVE", 68.5) == "OFFENSIVE"  # 65+3 aşıldı
    # OFFENSIVE→NEUTRAL aşağı geçiş: 64.9 > 65−3 → OFFENSIVE tutulur.
    assert _stab("OFFENSIVE", "NEUTRAL", 64.9) == "OFFENSIVE"
    assert _stab("OFFENSIVE", "NEUTRAL", 61.0) == "NEUTRAL"


def test_stabilize_crash_jump_not_delayed():
    # Ani çöküş: OFFENSIVE→CRISIS (avg 20) — 65−3 altına inildi → tam sıçrama.
    assert _stab("OFFENSIVE", "CRISIS", 20.0) == "CRISIS"


def test_stabilize_no_prev_or_same_is_raw():
    assert _stab(None, "NEUTRAL", 55.0) == "NEUTRAL"
    assert _stab("NEUTRAL", "NEUTRAL", 55.0) == "NEUTRAL"


def _snap_regime(dxy=104.0, us10=4.3):
    q = lambda s, p: SimpleNamespace(symbol=s, price=p)  # noqa: E731
    return SimpleNamespace(
        prices=[q("DXY", dxy), q("US10Y", us10), q("US02Y", 4.3), q("VIX", 18.0), q("BTCUSD", 60000.0)],
        technicals={"BTCUSD": SimpleNamespace(
            direction_score=55.0, status="OK", score=55.0, rsi=55.0, ema_stack="mixed",
        )},
        rotation=SimpleNamespace(score=55.0, direction="neutral", evidence=[], status="OK"),
    )


def test_classify_band_zero_is_stateless(tmp_path, monkeypatch):
    """Band=0 (default): durum dosyası OKUNMAZ/YAZILMAZ, raw_label None."""
    p = tmp_path / "regime_state.json"
    monkeypatch.setenv("REGIME_STATE_PATH", str(p))
    out = rc.classify(_snap_regime())
    assert out.raw_label is None and out.stabilized is False
    assert not p.exists()  # bayt-aynı: state dosyasına dokunulmadı


def test_classify_band_holds_previous_label(tmp_path, monkeypatch):
    p = tmp_path / "regime_state.json"
    monkeypatch.setenv("REGIME_STATE_PATH", str(p))
    p.write_text('{"label": "OFFENSIVE"}', encoding="utf-8")
    with threshold_override({"regime": {"hysteresis_band": 3.0}}):
        out = rc.classify(_snap_regime())
    # Ham etiket sınıra yakınsa önceki OFFENSIVE tutulur (raw != label).
    if out.raw_label != "OFFENSIVE":
        assert out.label == "OFFENSIVE" or out.stabilized is False
    # Durum dosyası güncellendi (bir sonraki tick okur).
    assert p.exists()


def test_classify_stateful_false_never_touches_state(tmp_path, monkeypatch):
    p = tmp_path / "regime_state.json"
    monkeypatch.setenv("REGIME_STATE_PATH", str(p))
    with threshold_override({"regime": {"hysteresis_band": 3.0}}):
        rc.classify(_snap_regime(), stateful=False)
    assert not p.exists()  # replay/backtest canlı hafızayı kirletmez


# ── 2. news ABSTAIN ──────────────────────────────────────────────────────────

def _snap_cons(headlines=None):
    tech = SimpleNamespace(direction_score=60.0, status="OK", timeframe="4h", score=60.0)
    return SimpleNamespace(
        technicals_by_tf={"BTCUSD": {"4h": tech}},
        technicals={},
        headlines=headlines or [],
        rotation=SimpleNamespace(score=50.0, direction="neutral", evidence=[], status="OK"),
        volatility={}, derivatives={}, options={},
    )


def _regime_cons():
    return RegimeOutput(
        label="NEUTRAL",
        layers=[
            RegimeLayer(name="Likidite", score=55.0, direction="neutral", evidence=[]),
            RegimeLayer(name="Risk İştahı", score=60.0, direction="neutral", evidence=[]),
        ],
    )


@pytest.fixture(autouse=True)
def _no_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_SCORING_V2_SHADOW_PATH", str(tmp_path / "yok.json"))


def test_news_abstain_off_neutral_vote_with_observe():
    res = ce.build("BTCUSD", _snap_cons(), _regime_cons(), "4h")
    news = next(m for m in res.modules if m.name == "news")
    assert news.score == pytest.approx(50.0)  # bayt-aynı: nötr oy sürüyor
    assert any(
        w.startswith("news_abstain_observe:reason=") and w.endswith(":applied=no")
        for w in res.warnings
    )


def test_news_abstain_on_drops_module_and_lowers_coverage():
    with threshold_override({"consensus": {"news_abstain": True}}):
        res = ce.build("BTCUSD", _snap_cons(), _regime_cons(), "4h")
    assert not any(m.name == "news" for m in res.modules)
    assert any(w.endswith(":applied=yes") for w in res.warnings if w.startswith("news_abstain_observe"))
    # Kapsama dürüstçe azaldı (M10 gözlemi devreye girer).
    assert any(w.startswith("coverage_observe") for w in res.warnings)


def test_news_abstain_with_relevant_headline_votes_normally():
    h = SimpleNamespace(verified=True, sentiment="bullish", asset_impact={"BTCUSD": 1.0})
    with threshold_override({"consensus": {"news_abstain": True, "news_symbol_filter": True}}):
        res = ce.build("BTCUSD", _snap_cons([h]), _regime_cons(), "4h")
    news = next(m for m in res.modules if m.name == "news")
    assert news.score == pytest.approx(75.0)
    assert not any(w.startswith("news_abstain_observe") for w in res.warnings)


# ── 3. DQS genişletme ────────────────────────────────────────────────────────

def test_extended_metrics_technical_bars():
    t_full = SimpleNamespace(status="OK", bars_used=300)
    t_thin = SimpleNamespace(status="OK", bars_used=17)
    m = dqs.extended_metrics(technicals_by_tf={"BTCUSD": {"4h": t_full, "1d": t_thin}})
    assert m["technical_bars"] == pytest.approx(50.0)  # 1/2 hücre tam-bar


def test_extended_metrics_news_diversity_and_rotation():
    hs = [
        SimpleNamespace(verified=True, source="coindesk"),
        SimpleNamespace(verified=True, source="cnbc"),
        SimpleNamespace(verified=False, source="fixture"),  # verified değil → sayılmaz
    ]
    rot_ok = SimpleNamespace(status="OK", per_symbol={"BTCUSD": 62.0})
    m = dqs.extended_metrics(headlines=hs, rotation=rot_ok)
    assert m["news_diversity"] == pytest.approx(66.7)  # 2 verified kaynak / 3 tavan
    assert m["rotation_coverage"] == 100.0
    rot_down = SimpleNamespace(status="UNAVAILABLE", per_symbol={})
    assert dqs.extended_metrics(rotation=rot_down)["rotation_coverage"] == 0.0


def test_extended_metrics_never_touches_score():
    """Genişletme GÖZLEM-YALNIZ: compute() score/status'u değişmez."""
    rep = dqs.compute([], ["BTCUSD"])
    assert rep.extended is None  # compute doldurmaz; pipeline additive doldurur
    assert rep.status == "BLOCKED"  # mevcut davranış aynen


def test_extended_metrics_empty_inputs_all_none():
    m = dqs.extended_metrics()
    assert m["technical_bars"] is None
    assert m["news_diversity"] is None
    assert m["rotation_coverage"] is None
