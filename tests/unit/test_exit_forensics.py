"""Çıkış Otopsisi (exit_forensics) testleri — denetim paketi 2026-07-03.

Dürüstlük garantileri: kapanış-sonrası hiçbir şey hesaplanmaz; $ tahmini
size_usd > notional çıkarımı > None; yalnız AUTO kohort puanlanır;
MIN_BUCKET altı bucket'lar kart üretmez.
"""
from __future__ import annotations

from packages.learning import exit_forensics as ef
from packages.learning.outcomes import CanonicalOutcome

FP = "BTCUSD|v2|1h|NEUTRAL|bullish|S55|C|touche"


def _o(**kw) -> CanonicalOutcome:
    base = dict(
        trade_id="t1", symbol="BTCUSD", timeframe="1h",
        opened_at="2026-07-03T00:00:00+00:00", closed_at="2026-07-03T01:00:00+00:00",
        duration_seconds=3600.0, direction="long", open_price=100.0, close_price=101.0,
        pnl=10.0, pnl_pct=1.0, open_reason="signal", close_reason="TP_HIT",
        fingerprint=FP, regime="NEUTRAL", dominant_module="touche",
        candidate_action="open_long", final_action="open_long", data_verified=True,
        mae_pct=0.2, mfe_pct=1.5,
    )
    base.update(kw)
    return CanonicalOutcome(**base)


# ----------------------------- kategori bazlı matematik -----------------------------

def test_trailing_give_back_and_capture() -> None:
    # Tepe %2.0, gerçekleşen %1.0 → give_back %1.0, capture 0.5.
    d = ef._diagnose(_o(close_reason="TRAILING_STOP_EXIT", pnl_pct=1.0, mfe_pct=2.0,
                        size_usd=1000.0))
    assert d["category"] == "trailing"
    assert d["give_back_pct"] == 1.0
    assert d["capture"] == 0.5
    assert d["give_back_usd_est"] == 10.0  # 1000 × %1


def test_trailing_capture_clamped_to_one() -> None:
    # pnl > mfe (kayıt tuhaflığı) → capture 1.0'da kelepçelenir, give_back 0.
    d = ef._diagnose(_o(close_reason="TRAILING_STOP_EXIT", pnl_pct=2.5, mfe_pct=2.0))
    assert d["capture"] == 1.0
    assert d["give_back_pct"] == 0.0


def test_time_stop_missed_capture_vs_never_worked() -> None:
    # Tepe %1.8 gördü, %0.3 ile kapandı → 1.5 puan bankaya konamadı.
    d = ef._diagnose(_o(close_reason="TIME_STOP_EXIT", pnl_pct=0.3, mfe_pct=1.8))
    assert d["missed_capture_pct"] == 1.5
    assert d["never_worked"] is False
    # Hiç işlemedi (mfe ≤ eşik) → giriş sorunu; çıkış maliyeti atfedilmez.
    d2 = ef._diagnose(_o(close_reason="TIME_STOP_EXIT", pnl_pct=-0.1, mfe_pct=0.02,
                         mae_pct=0.3))
    assert d2["never_worked"] is True
    assert d2["missed_capture_pct"] is None


def test_sl_roundtrip_via_r_path() -> None:
    # risk %1, tepe %0.8 → mfe_r 0.8 ≥ 0.5R → roundtrip; maliyet = mfe − pnl.
    d = ef._diagnose(_o(close_reason="SL_HIT", pnl_pct=-1.0, mfe_pct=0.8,
                        mae_pct=1.0, risk_pct=0.01))
    assert d["sl_class"] == "roundtrip"
    assert d["give_back_pct"] == 1.8  # 0.8 − (−1.0)


def test_sl_roundtrip_via_mae_proxy_path() -> None:
    # risk_pct yok → SL kapanışında mae ≈ SL mesafesi vekili: mfe ≥ 0.5×mae.
    d = ef._diagnose(_o(close_reason="SL_HIT", pnl_pct=-1.0, mfe_pct=0.6,
                        mae_pct=1.0, risk_pct=None))
    assert d["sl_class"] == "roundtrip"


def test_sl_straight_loss_excluded_from_cost() -> None:
    # Hiç lehe gitmedi → giriş/yön sorunu; çıkış-makinesi maliyeti YOK.
    d = ef._diagnose(_o(close_reason="SL_HIT", pnl_pct=-1.0, mfe_pct=0.0,
                        mae_pct=1.0, risk_pct=0.01))
    assert d["sl_class"] == "straight"
    assert d["give_back_pct"] is None


def test_sl_gray_counted_without_cost() -> None:
    d = ef._diagnose(_o(close_reason="SL_HIT", pnl_pct=-1.0, mfe_pct=0.3,
                        mae_pct=1.0, risk_pct=0.01))  # mfe_r=0.3 < 0.5
    assert d["sl_class"] == "gray"
    assert d["give_back_pct"] is None


# ----------------------------- $ tahmini dürüstlüğü -----------------------------

def test_notional_inference_guard_near_breakeven() -> None:
    # pnl_pct ~0 → çıkarım çöker → None (uydurma yok).
    assert ef._notional_usd(_o(pnl=0.02, pnl_pct=0.01, size_usd=None)) is None


def test_size_usd_preferred_over_inference() -> None:
    # Çıkarım 500 verirdi (10/0.02) ama size_usd kesin → 750.
    o = _o(pnl=10.0, pnl_pct=2.0, size_usd=750.0)
    assert ef._notional_usd(o) == 750.0
    assert ef._notional_usd(_o(pnl=10.0, pnl_pct=2.0, size_usd=None)) == 500.0


# ----------------------------- kohort + rapor -----------------------------

def test_non_auto_excluded_from_report() -> None:
    outs = [
        _o(trade_id="a1"),                                          # AUTO
        _o(trade_id="m1", fingerprint=None, open_reason="owner_manual"),  # MANUAL
        _o(trade_id="x1", fingerprint=None, open_reason=None),      # EXCLUDED
        _o(trade_id="u1", data_verified=False),                     # fingerprint var ama unverified
    ]
    rep = ef.report(outs)
    assert rep["usable"] == 1
    assert rep["excluded"]["manual"] == 1
    assert rep["excluded"]["non_auto"] == 2


def test_min_bucket_silence_in_top_costs() -> None:
    # 3 trailing outcome (< MIN_BUCKET=5) → bucket var ama kart yok.
    outs = [_o(trade_id=f"t{i}", close_reason="TRAILING_STOP_EXIT",
               pnl_pct=0.5, mfe_pct=2.0) for i in range(3)]
    rep = ef.report(outs)
    assert any(b["category"] == "trailing" for b in rep["buckets"])
    assert rep["top_costs"] == []


def test_top_costs_ranked_by_usd() -> None:
    outs = (
        # 1h trailing: 5 işlem, $1000 × %1.5 geri = $15/işlem → $75 toplam.
        [_o(trade_id=f"tr{i}", close_reason="TRAILING_STOP_EXIT", pnl_pct=0.5,
            mfe_pct=2.0, size_usd=1000.0) for i in range(5)]
        # 4h time_stop: 5 işlem, daha küçük maliyet.
        + [_o(trade_id=f"ts{i}", timeframe="4h", close_reason="TIME_STOP_EXIT",
              pnl_pct=0.1, mfe_pct=0.4, size_usd=500.0) for i in range(5)]
    )
    rep = ef.report(outs)
    cards = rep["top_costs"]
    assert len(cards) == 2
    assert cards[0]["kind"] == "TRAILING_GIVEBACK"  # $75 > $7.5
    assert cards[0]["cost_usd_est"] == 75.0
    assert "tahmini" in cards[0]["label"]


def test_no_excursion_legacy_skipped() -> None:
    rep = ef.report([_o(trade_id="l1", mae_pct=0.0, mfe_pct=0.0)])
    assert rep["excluded"]["no_excursion"] == 1


# ----------------------------- trainer_evidence -----------------------------

def test_trainer_evidence_ratios_and_empty_on_insufficient() -> None:
    outs = [_o(trade_id=f"tr{i}", close_reason="TRAILING_STOP_EXIT",
               pnl_pct=0.5, mfe_pct=2.0) for i in range(5)]
    ev = ef.trainer_evidence(outs)
    assert "1h" in ev
    assert 0.0 <= ev["1h"]["trailing_giveback_ratio"] <= 1.0
    # Yetersiz veri → {} (trainer sabit adıma düşer, fake yok).
    assert ef.trainer_evidence([_o(trade_id="one")]) == {}


def test_trainer_evidence_sl_roundtrip_share() -> None:
    outs = (
        [_o(trade_id=f"r{i}", close_reason="SL_HIT", pnl_pct=-1.0, mfe_pct=0.8,
            mae_pct=1.0, risk_pct=0.01) for i in range(3)]
        + [_o(trade_id=f"s{i}", close_reason="SL_HIT", pnl_pct=-1.0, mfe_pct=0.0,
              mae_pct=1.0, risk_pct=0.01) for i in range(2)]
    )
    ev = ef.trainer_evidence(outs)
    assert ev["1h"]["sl_roundtrip_share"] == 0.6  # 3/5


# ----------------------------- snapshot -----------------------------

def test_write_snapshot_history_cap(tmp_path, monkeypatch) -> None:
    path = tmp_path / "exit_forensics.json"
    monkeypatch.setenv("EXIT_FORENSICS_OUT_PATH", str(path))
    outs = [_o(trade_id=f"t{i}", close_reason="TRAILING_STOP_EXIT",
               pnl_pct=0.5, mfe_pct=2.0, size_usd=1000.0) for i in range(5)]
    for _ in range(ef.HISTORY_MAX + 5):
        payload = ef.write_snapshot(outs)
    assert len(payload["history"]) == ef.HISTORY_MAX
    assert payload["latest"]["usable"] == 5
    assert payload["history"][-1]["total_bad_exit_cost_usd_est"] == 75.0
    assert payload["history"][-1]["per_tf_capture"]["1h"] == 0.25


def test_write_snapshot_survives_corrupt_previous(tmp_path, monkeypatch) -> None:
    path = tmp_path / "exit_forensics.json"
    path.write_text("{bozuk json", encoding="utf-8")
    monkeypatch.setenv("EXIT_FORENSICS_OUT_PATH", str(path))
    payload = ef.write_snapshot([_o(trade_id="t1")])
    assert len(payload["history"]) == 1  # geçmiş sıfırdan, crash yok


def test_report_empty_outcomes_safe() -> None:
    rep = ef.report([])
    assert rep["usable"] == 0
    assert rep["buckets"] == []
    assert rep["top_costs"] == []
