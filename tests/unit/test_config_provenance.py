"""Config köken damgası (yeniden-üretilebilirlik — denetim bulgusu).

Karar log'u artık açılış anındaki weights/thresholds SHA + weights sürümünü
taşır → git commit'inden hangi config'le üretildiği yeniden-üretilebilir.
"""
from __future__ import annotations

from packages.data.registry import loader


def test_config_provenance_shape():
    p = loader.config_provenance()
    assert set(p) == {"weights_version", "weights_sha", "thresholds_sha", "manifest_sha"}
    assert isinstance(p["weights_version"], str)
    # thresholds her zaman var → SHA üretilir (12 hex)
    assert p["thresholds_sha"] is not None and len(p["thresholds_sha"]) == 12


def test_file_sha_deterministic_and_missing_none(tmp_path):
    f = tmp_path / "x.yaml"
    f.write_text("a: 1\n", encoding="utf-8")
    assert loader._file_sha(f) == loader._file_sha(f)  # deterministik
    assert len(loader._file_sha(f)) == 12
    assert loader._file_sha(tmp_path / "yok.yaml") is None  # yok → None (uydurma yok)


def test_decision_log_carries_provenance():
    from types import SimpleNamespace

    from packages.learning import decision_log
    prov = {"weights_version": "1.16.0", "weights_sha": "abc123def456",
            "thresholds_sha": "111222333444", "manifest_sha": None}
    trade = SimpleNamespace(
        id="T1", closed_at="2026-07-15T00:00:00Z", symbol="BTCUSD", side="long",
        timeframe="4h", fingerprint="fp", open_reason="r", snapshot_id="s",
        open_dqs=90.0, open_risk_action="allow", predicted_confidence=0.6,
        raw_confidence=0.5, confidence_source="cal", data_verified=True,
        open_config_provenance=prov, close_reason="tp", lifecycle_status="CLOSED",
        entry_price=100.0, exit_price=110.0, pnl_usd=10.0, opened_at="o",
    )
    entry = decision_log.entry_for(trade)
    assert entry["opening_signal"]["config_provenance"] == prov


def test_decision_log_legacy_trade_provenance_none():
    from types import SimpleNamespace

    from packages.learning import decision_log
    trade = SimpleNamespace(
        id="T2", closed_at="c", symbol="ETHUSD", side="short", timeframe="1d",
        fingerprint=None, open_reason=None, snapshot_id=None, open_dqs=None,
        open_risk_action=None, predicted_confidence=None, raw_confidence=None,
        confidence_source=None, data_verified=False, close_reason="sl",
        lifecycle_status="CLOSED", entry_price=1.0, exit_price=0.9, pnl_usd=-0.1,
        opened_at="o",
    )
    entry = decision_log.entry_for(trade)
    assert entry["opening_signal"]["config_provenance"] is None  # legacy geriye-uyumlu
