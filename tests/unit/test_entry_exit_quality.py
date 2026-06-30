"""CP4 (slice 1) — entry_exit_quality (giriş/çıkış kalitesi öğrenicisi) testleri."""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from packages.learning import entry_exit_quality as eeq
from packages.learning.outcomes import CanonicalOutcome


def _outcome(
    *,
    module: str = "touche",
    tf: str = "4h",
    pnl: float,
    pnl_pct: float,
    mae_pct: float,
    mfe_pct: float,
    close_reason: str = "TRAILING_STOP_EXIT",
) -> CanonicalOutcome:
    """Excursion alanları dolu minimal verified outcome (analiz girdisi)."""
    return CanonicalOutcome(
        trade_id="t", symbol="X", timeframe=tf, opened_at=None, closed_at=None,
        duration_seconds=None, direction="long", open_price=1.0, close_price=1.0,
        pnl=pnl, pnl_pct=pnl_pct, open_reason=None, close_reason=close_reason,
        fingerprint=None, regime="NEUTRAL", dominant_module=module,
        candidate_action=None, final_action=None, data_verified=True,
        mae_pct=mae_pct, mfe_pct=mfe_pct,
    )


def test_exit_early_flagged() -> None:
    # Kazananlar tepe +3% MFE'ye ulaşıp +0.5%'te kapanıyor → düşük yakalama +
    # yüksek bırakılan kâr → EXIT_EARLY.
    outs = [
        _outcome(pnl=5.0, pnl_pct=0.5, mae_pct=0.2, mfe_pct=3.0) for _ in range(5)
    ]
    m = eeq._bucket_metrics(outs)
    codes = {v["code"] for v in eeq._verdicts(m)}
    assert "EXIT_EARLY" in codes
    assert m["avg_capture_ratio"] is not None and m["avg_capture_ratio"] < 0.5


def test_stop_too_tight_flagged() -> None:
    # Kazananlar +2% MFE riding ediyor ama stop'lar yalnız 0.4% adverse'ta tetikleniyor
    # → stop kazanan-hareketin içinde → STOP_TOO_TIGHT.
    winners = [
        _outcome(pnl=2.0, pnl_pct=2.0, mae_pct=0.1, mfe_pct=2.0) for _ in range(4)
    ]
    stops = [
        _outcome(pnl=-0.4, pnl_pct=-0.4, mae_pct=0.4, mfe_pct=0.3,
                 close_reason="SL_HIT") for _ in range(3)
    ]
    m = eeq._bucket_metrics(winners + stops)
    codes = {v["code"] for v in eeq._verdicts(m)}
    assert "STOP_TOO_TIGHT" in codes
    assert m["avg_sl_adverse_pct"] < m["avg_winner_mfe_pct"]


def test_enter_early_flagged() -> None:
    # Kazananlar lehe dönmeden önce MFE'lerinin %80'i kadar aleyhte dalıyor → ENTER_EARLY.
    outs = [
        _outcome(pnl=1.0, pnl_pct=1.0, mae_pct=1.6, mfe_pct=2.0) for _ in range(5)
    ]
    codes = {v["code"] for v in eeq._verdicts(eeq._bucket_metrics(outs))}
    assert "ENTER_EARLY" in codes


def test_clean_bucket_no_verdict() -> None:
    # Tüm hareketi yakalayan, dar olmayan stop, temiz giriş → ders yok.
    outs = [
        _outcome(pnl=1.0, pnl_pct=1.0, mae_pct=0.1, mfe_pct=1.0) for _ in range(5)
    ]
    assert eeq._verdicts(eeq._bucket_metrics(outs)) == []


def test_min_bucket_guard_silent() -> None:
    # Yetersiz örnek (< _MIN_BUCKET) → ders üretme (gürültü/uydurma yok).
    outs = [_outcome(pnl=5.0, pnl_pct=0.5, mae_pct=0.2, mfe_pct=3.0)]
    assert eeq._verdicts(eeq._bucket_metrics(outs)) == []


def test_zero_excursion_excluded() -> None:
    # 0/0 (hareketsiz/legacy) kayıtlar usable sayılmaz → istatistiği kirletmez.
    outs = [_outcome(pnl=0.0, pnl_pct=0.0, mae_pct=0.0, mfe_pct=0.0) for _ in range(5)]
    m = eeq._bucket_metrics(outs)
    assert m["n_usable"] == 0
    assert eeq._verdicts(m) == []


@pytest.fixture
def fresh_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("DECISION_LOG_PATH", str(tmp_path / "decision_log.jsonl"))
    from packages.paper import state as ps
    importlib.reload(ps)
    return ps


def test_report_shape_empty(fresh_env) -> None:
    r = eeq.report()
    assert r["total"] == 0
    assert r["buckets"] == []
    assert r["flagged_count"] == 0
    assert "thresholds" in r


def test_endpoint(fresh_env) -> None:
    from apps.api.main import app
    client = TestClient(app)
    resp = client.get("/api/v1/learning/entry-exit-quality")
    assert resp.status_code == 200
    body = resp.json()
    assert "buckets" in body and "verdict_counts" in body
