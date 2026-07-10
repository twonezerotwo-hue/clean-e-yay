"""D — dinamik korelasyon vetosu testleri (P1).

Kritik güvenceler:
- Çelişki mantığı: pozitif rho → akraba aynı yön beklenir; negatif rho → ters.
  Beklenenden sapma = veto.
- Shadow-first: enabled kapalıyken active=False (rapor dolu ama karar değişmez).
- Saf/defansif: güçlü akraba yok / akraba nötr → veto YOK.
- YALNIZ ENGELLER: boyut artırmaz; engine'de flag açıkken hold döner.
"""
from __future__ import annotations

import importlib

import pytest

from packages.decision import correlation_veto as cv


def _patch_neighbors(monkeypatch, *, partner, rho, plean):
    monkeypatch.setattr(cv, "nearest_relative", lambda *a, **k: (partner, rho))
    monkeypatch.setattr(cv, "partner_lean", lambda sym: plean)


def test_no_strong_relative_returns_empty(monkeypatch):
    """Güçlü akraba yok → boş dict (veto konusu değil, gözlem gürültüsü yok)."""
    monkeypatch.setattr(cv, "nearest_relative", lambda *a, **k: (None, 0.2))
    assert cv.assess("BTCUSD", "long", ["XAUUSD"], {"enabled": True}) == {}


def test_neutral_partner_no_veto(monkeypatch):
    """Akraba yön nötr → çelişki tespit edilemez → veto yok."""
    _patch_neighbors(monkeypatch, partner="XAGUSD", rho=0.8, plean=0.0)
    r = cv.assess("XAUUSD", "long", ["XAGUSD"], {"enabled": True})
    assert r["vetoed"] is False and r["partner"] == "XAGUSD"


def test_positive_rho_same_direction_aligned(monkeypatch):
    """Pozitif rho + akraba AYNI yön → uyumlu (veto YOK)."""
    _patch_neighbors(monkeypatch, partner="XAGUSD", rho=0.8, plean=0.6)
    r = cv.assess("XAUUSD", "long", ["XAGUSD"], {"enabled": True})
    assert r["vetoed"] is False


def test_positive_rho_opposite_direction_vetoes(monkeypatch):
    """Pozitif rho + akraba TERS yön → çelişki → VETO. (altın long, gümüş short)."""
    _patch_neighbors(monkeypatch, partner="XAGUSD", rho=0.8, plean=-0.6)
    r = cv.assess("XAUUSD", "long", ["XAGUSD"], {"enabled": True})
    assert r["vetoed"] is True and r["expected_partner_sign"] == 1.0


def test_negative_rho_same_direction_vetoes(monkeypatch):
    """Negatif rho + akraba AYNI yön → çelişki (ters bekleniyordu) → VETO."""
    _patch_neighbors(monkeypatch, partner="DXY", rho=-0.7, plean=0.5)
    r = cv.assess("XAUUSD", "long", ["DXY"], {"enabled": True})
    assert r["vetoed"] is True and r["expected_partner_sign"] == -1.0


def test_negative_rho_opposite_direction_aligned(monkeypatch):
    """Negatif rho + akraba TERS yön → uyumlu (dolar düşerken altın long) → veto YOK."""
    _patch_neighbors(monkeypatch, partner="DXY", rho=-0.7, plean=-0.5)
    r = cv.assess("XAUUSD", "long", ["DXY"], {"enabled": True})
    assert r["vetoed"] is False


def test_shadow_disabled_reports_but_inactive(monkeypatch):
    """enabled kapalı → active=False (rapor dolu, karar katmanı ELE ALMAZ = shadow)."""
    _patch_neighbors(monkeypatch, partner="XAGUSD", rho=0.8, plean=-0.6)
    r = cv.assess("XAUUSD", "long", ["XAGUSD"], {"enabled": False})
    assert r["active"] is False and r["vetoed"] is True   # çelişki görülür ama pasif


def test_nearest_relative_picks_strongest(monkeypatch):
    """En yüksek |rho|'lu sembol seçilir; eşik altındaysa None."""
    series = {"BTCUSD": {}, "SP500": {}, "XAUUSD": {}}
    monkeypatch.setattr(cv.correlation, "price_return_series", lambda *a, **k: series)
    rhos = {("BTCUSD", "SP500"): 0.42, ("BTCUSD", "XAUUSD"): 0.11}
    monkeypatch.setattr(cv.correlation, "_pair_price_rho",
                        lambda a, b, s: (rhos.get((a, b)), 90))
    p, rho = cv.nearest_relative("BTCUSD", ["BTCUSD", "SP500", "XAUUSD"],
                                 min_abs_rho=0.3, window_days=90)
    assert p == "SP500" and rho == 0.42
    # eşik 0.5 → hiçbiri geçmez
    p2, _ = cv.nearest_relative("BTCUSD", ["BTCUSD", "SP500", "XAUUSD"],
                                min_abs_rho=0.5, window_days=90)
    assert p2 is None


# ---------------- engine entegrasyonu (end-to-end) ----------------

@pytest.fixture
def fresh_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("CALIBRATION_STORE_PATH", str(tmp_path / "platt.json"))
    monkeypatch.setenv("GUARD_OVERRIDES_PATH", str(tmp_path / "guard_overrides.json"))
    from packages.paper import state as ps
    importlib.reload(ps)
    return ps


def _force_pass(monkeypatch, *, score=85.0):
    from packages.consensus.engine import ConsensusResult, ModuleScore
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision import engine as dec
    from packages.regime.classifier import classify
    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    fake = ConsensusResult(
        symbol="BTCUSD", score=score, direction="bullish", confluence_aligned=True,
        dominant_module="touche",
        modules=[ModuleScore(name="touche", score=score, weight=1.0, contribution=score)],
    )
    monkeypatch.setattr(dec, "build_consensus", lambda *a, **kw: fake)
    return dec, snap, regime


def test_engine_shadow_default_no_veto(fresh_env, monkeypatch):
    """Default (flag kapalı): korelasyon vetosu KARARI DÜŞÜRMEZ (shadow)."""
    from packages.risk.engine import RiskDecision
    dec, snap, regime = _force_pass(monkeypatch)
    # akraba çelişse bile flag kapalı → active False → geçer
    monkeypatch.setattr(dec.correlation_veto, "assess",
                        lambda *a, **k: {"active": False, "vetoed": True, "partner": "SP500"})
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])
    d = dec.decide_for_symbol("BTCUSD", snap, regime, hold_risk, equity_usd=100_000)
    assert d.action == "open_long"
    assert "correlation_veto" not in d.blocked_by
    assert d.correlation_veto_report.get("vetoed") is True  # gözlem taşınır


def test_engine_veto_on_blocks(fresh_env, monkeypatch):
    """Flag açık + akraba çelişkisi → işlem ENGELLENİR (hold)."""
    from packages.risk.engine import RiskDecision
    dec, snap, regime = _force_pass(monkeypatch)
    monkeypatch.setattr(dec.correlation_veto, "assess", lambda *a, **k: {
        "active": True, "vetoed": True, "partner": "SP500", "rho": 0.62,
        "partner_lean": -0.5, "reason": "SP500 (rho=+0.62) ilişkiyle çelişiyor"})
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])
    d = dec.decide_for_symbol("BTCUSD", snap, regime, hold_risk, equity_usd=100_000)
    assert d.action == "hold"
    assert "correlation_veto" in d.blocked_by
    assert d.correlation_veto_report["partner"] == "SP500"


def test_engine_veto_on_but_aligned_passes(fresh_env, monkeypatch):
    """Flag açık ama akraba UYUMLU (vetoed False) → işlem geçer."""
    from packages.risk.engine import RiskDecision
    dec, snap, regime = _force_pass(monkeypatch)
    monkeypatch.setattr(dec.correlation_veto, "assess", lambda *a, **k: {
        "active": True, "vetoed": False, "partner": "SP500", "rho": 0.62})
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])
    d = dec.decide_for_symbol("BTCUSD", snap, regime, hold_risk, equity_usd=100_000)
    assert d.action == "open_long"
    assert "correlation_veto" not in d.blocked_by
