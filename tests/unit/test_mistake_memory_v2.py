"""F3-3 — mistake memory v2 (kalıcı kaynak + hiyerarşik fallback + Wilson).

- Flag KAPALI (default): recent_trades + exact-match + nokta tahmini — eski
  davranış birebir (1W/2L → AVOID aynen kalır).
- Flag AÇIK: decision_log dahil kalıcı kaynak; exact imza yetersizse L1
  (symbol|tf|rejim|yön) → L2 (symbol|yön) kovası; AVOID/BOOST Wilson güven
  sınırıyla (az veri aceleci blok üretemez).
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper_state.json"))
    monkeypatch.setenv("DECISION_LOG_PATH", str(tmp_path / "decision_log.jsonl"))
    from packages.paper import state as ps
    importlib.reload(ps)
    from packages.learning import mistake_memory as mm
    return ps, mm


def _trade(ps, i: int, fingerprint: str, pnl: float, closed_at: str) -> None:
    state = ps.load()
    state.recent_trades.append(
        ps.Trade(
            id=f"t{i}", symbol="BTCUSD", side="long",
            entry_price=100.0, exit_price=101.0, pnl_usd=pnl,
            opened_at="2026-06-11T00:00:00+00:00", closed_at=closed_at,
            close_reason="TP_HIT", fingerprint=fingerprint, data_verified=True,
        )
    )
    ps.save(state)


_FP = "BTCUSD|v2|4h|NEUTRAL|bullish|S65|C|touche"       # exact aday imzası
_FP_SIBLING = "BTCUSD|v2|4h|NEUTRAL|bullish|S55|X|news"  # aynı L1 kovası, farklı imza
_FP_OTHER_DIR = "BTCUSD|v2|1d|CRISIS|bearish|S35|X|touche"  # yalnız L2'de komşu değil (yön farklı)


def test_wilson_bounds_sanity() -> None:
    from packages.learning import mistake_memory as mm
    lo0, hi0 = mm.wilson_bounds(0, 3)
    assert lo0 == 0.0 and 0.5 < hi0 < 0.65      # 0/3 kötü OLABİLİR ama emin değiliz
    _, hi1 = mm.wilson_bounds(0, 10)
    assert hi1 < 0.35                             # 0/10 → artık eminiz
    lo2, _ = mm.wilson_bounds(20, 20)
    assert lo2 > 0.80                             # 20/20 → gerçekten iyi


def test_flag_off_byte_same_point_estimate_avoid(tmp_path, monkeypatch) -> None:
    """Eski davranış: 1W/2L (wr=0.333) nokta tahminiyle AVOID."""
    ps, mm = _fresh(tmp_path, monkeypatch)
    monkeypatch.delenv("MISTAKE_MEMORY_V2", raising=False)
    _trade(ps, 0, _FP, +50.0, "2026-06-11T01:00:00+00:00")
    _trade(ps, 1, _FP, -50.0, "2026-06-11T02:00:00+00:00")
    _trade(ps, 2, _FP, -50.0, "2026-06-11T03:00:00+00:00")
    v = mm.evaluate(_FP)
    assert v.action == "AVOID"
    # sentetik kova kayıtları da üretilmez
    assert all(not m.fingerprint.startswith("~L") for m in mm.summary())


def test_flag_on_wilson_demotes_hasty_avoid_to_warning(tmp_path, monkeypatch) -> None:
    """1W/2L: kötü OLABİLİR ama kanıt yetersiz → AVOID değil WARNING (0.7 size)."""
    ps, mm = _fresh(tmp_path, monkeypatch)
    monkeypatch.setenv("MISTAKE_MEMORY_V2", "1")
    _trade(ps, 0, _FP, +50.0, "2026-06-11T01:00:00+00:00")
    _trade(ps, 1, _FP, -50.0, "2026-06-11T02:00:00+00:00")
    _trade(ps, 2, _FP, -50.0, "2026-06-11T03:00:00+00:00")
    v = mm.evaluate(_FP)
    assert v.action == "WARNING"
    assert v.size_factor == pytest.approx(0.7)


def test_flag_on_confident_avoid_still_fires(tmp_path, monkeypatch) -> None:
    """1W/9L: Wilson üst sınırı da eşiğin altında → AVOID haklı olarak kalır."""
    ps, mm = _fresh(tmp_path, monkeypatch)
    monkeypatch.setenv("MISTAKE_MEMORY_V2", "1")
    _trade(ps, 0, _FP, +50.0, "2026-06-11T00:30:00+00:00")
    for i in range(1, 10):
        _trade(ps, i, _FP, -50.0, f"2026-06-11T0{min(i, 9)}:00:00+00:00")
    v = mm.evaluate(_FP)
    assert v.action == "AVOID"  # streak=9 da tetikler; her iki yol da AVOID


def test_flag_on_hierarchical_l1_fallback(tmp_path, monkeypatch) -> None:
    """Exact imzada tek işlem var (yetersiz) ama aynı sembol+TF+rejim+yön
    kovasında 10 kayıp birikmiş → L1 kovasından AVOID."""
    ps, mm = _fresh(tmp_path, monkeypatch)
    monkeypatch.setenv("MISTAKE_MEMORY_V2", "1")
    _trade(ps, 0, _FP, -50.0, "2026-06-11T01:00:00+00:00")
    for i in range(1, 11):
        _trade(ps, i, _FP_SIBLING, -50.0, f"2026-06-1{1 + i // 10}T02:00:00+00:00")
    v = mm.evaluate(_FP)
    assert v.action == "AVOID"
    assert v.reason.startswith("[L1]")
    assert any(e.startswith("bucket=~L1|BTCUSD|4h|NEUTRAL|bullish") for e in v.evidence)


def test_flag_on_l1_bucket_respects_direction(tmp_path, monkeypatch) -> None:
    """Farklı yön/TF/rejim işlemleri kovaya sızmaz — komşu değiller."""
    ps, mm = _fresh(tmp_path, monkeypatch)
    monkeypatch.setenv("MISTAKE_MEMORY_V2", "1")
    _trade(ps, 0, _FP, -50.0, "2026-06-11T01:00:00+00:00")
    for i in range(1, 11):
        _trade(ps, i, _FP_OTHER_DIR, -50.0, "2026-06-11T02:00:00+00:00")
    v = mm.evaluate(_FP)
    assert v.action == "NEUTRAL"
    assert v.reason == "yetersiz veri"


def test_flag_on_reads_durable_outcomes(tmp_path, monkeypatch) -> None:
    """Kalıcı kaynak: decision_log'dan gelen CanonicalOutcome kayıtları (pnl
    alanı, pnl_usd değil) hafızaya girer."""
    _, mm = _fresh(tmp_path, monkeypatch)
    monkeypatch.setenv("MISTAKE_MEMORY_V2", "1")
    from packages.learning import outcomes as om
    outs = [
        SimpleNamespace(fingerprint=_FP, pnl=-50.0, data_verified=True,
                        closed_at=f"2026-06-11T0{i}:00:00+00:00")
        for i in range(1, 9)
    ]
    monkeypatch.setattr(om, "outcomes_from_state", lambda *a, **k: outs)
    v = mm.evaluate(_FP)
    assert v.action == "AVOID"  # 0/8: wilson üst < 0.35 + streak
    rec = next(m for m in mm.summary() if m.fingerprint == _FP)
    assert rec.trades == 8 and rec.total_pnl == pytest.approx(-400.0)
