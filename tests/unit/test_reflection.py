"""Yansıma/hafıza döngüsü testleri (SALT-GÖZLEM; TradingAgents deseni, 2026-07-08).

Kapanan outcome'lardan ders çıkarma + digest + EVIDENCE-only garantisi:
- Yalnız data_verified + pnl_pct dolu outcome derse girer.
- Ders metni yalnız outcome alanlarından türer (uydurma sayı yok).
- Digest: çapraz + per-sembol, en yeni önce; karara dokunmaz.
"""
from __future__ import annotations

from packages.learning import reflection as rf


class _O:
    """Test için minimal CanonicalOutcome benzeri."""

    def __init__(self, symbol="BTCUSD", timeframe="4h", regime="OFFENSIVE",
                 direction="long", pnl=10.0, pnl_pct=1.2, r_multiple=0.8,
                 dominant_module="sentinel", close_reason="TP_HIT",
                 closed_at="2026-07-08T10:00:00+00:00", data_verified=True):
        self.symbol = symbol
        self.timeframe = timeframe
        self.regime = regime
        self.direction = direction
        self.pnl = pnl
        self.pnl_pct = pnl_pct
        self.r_multiple = r_multiple
        self.dominant_module = dominant_module
        self.close_reason = close_reason
        self.closed_at = closed_at
        self.data_verified = data_verified


def test_lesson_only_from_verified_closed():
    """Doğrulanmamış ya da pnl_pct'siz outcome derse GİRMEZ."""
    assert rf._to_lesson(_O(data_verified=False)) is None
    assert rf._to_lesson(_O(pnl_pct=None)) is None
    ln = rf._to_lesson(_O())
    assert ln is not None and ln.symbol == "BTCUSD" and ln.won is True


def test_lesson_text_is_evidence_only():
    """Ders metni yalnız outcome alanlarını içerir (yön, TF, rejim, %, R, modül)."""
    ln = rf._to_lesson(_O(pnl=-5.0, pnl_pct=-0.9, r_multiple=-1.0, close_reason="SL_HIT"))
    assert "BTCUSD" in ln.text and "long" in ln.text and "4h/OFFENSIVE" in ln.text
    assert "-0.90%" in ln.text and "-1.00R" in ln.text and "sentinel" in ln.text
    assert "kaybetti" in ln.text and "SL_HIT" in ln.text
    assert ln.won is False


def test_recent_lessons_newest_first_and_symbol_filter():
    outs = [
        _O(symbol="BTCUSD", closed_at="2026-07-08T09:00:00+00:00"),
        _O(symbol="ETHUSD", closed_at="2026-07-08T11:00:00+00:00"),
        _O(symbol="BTCUSD", closed_at="2026-07-08T10:00:00+00:00"),
    ]
    allr = rf.recent_lessons(outs, limit=5)
    assert [ln.symbol for ln in allr] == ["ETHUSD", "BTCUSD", "BTCUSD"]  # yeni→eski
    btc = rf.recent_lessons(outs, symbol="BTCUSD", limit=5)
    assert len(btc) == 2 and all(ln.symbol == "BTCUSD" for ln in btc)


def test_symbol_memory_aggregate():
    outs = [
        _O(symbol="BTCUSD", pnl=10, r_multiple=1.0),
        _O(symbol="BTCUSD", pnl=-5, r_multiple=-1.0),
        _O(symbol="BTCUSD", pnl=8, r_multiple=0.5),
    ]
    mem = rf.symbol_memory(outs, "BTCUSD", limit=5)
    assert mem["summary"]["n"] == 3 and mem["summary"]["wins"] == 2
    assert mem["summary"]["win_pct"] == round(2 / 3 * 100, 1)
    assert len(mem["lessons"]) == 3


def test_build_digest_shape_and_no_decision_touch():
    outs = [_O(symbol="BTCUSD"), _O(symbol="ETHUSD"), _O(symbol="NVDA")]
    d = rf.build_digest(outs)
    assert d["engine"] == rf._ENGINE
    assert d["total_lessons"] == 3
    assert isinstance(d["cross_lessons"], list) and len(d["cross_lessons"]) == 3
    assert set(d["per_symbol"].keys()) == {"BTCUSD", "ETHUSD", "NVDA"}
    assert "SALT-GOZLEM" in d["note"]


def test_build_digest_empty_safe():
    d = rf.build_digest([])
    assert d["total_lessons"] == 0 and d["cross_lessons"] == []


def test_write_and_viewmodel(tmp_path, monkeypatch):
    art = tmp_path / "reflection.json"
    monkeypatch.setenv("REFLECTION_PATH", str(art))
    monkeypatch.setattr(
        rf.outcomes_mod, "outcomes_from_state",
        lambda: [_O(symbol="BTCUSD"), _O(symbol="ETHUSD")],
    )
    out = rf.write_digest()
    assert out["status"] == "OK" and out["total_lessons"] == 2
    vm = rf.viewmodel()
    assert vm["status"] == "OK" and vm["shadow_only"] is True
    assert vm["total_lessons"] == 2
