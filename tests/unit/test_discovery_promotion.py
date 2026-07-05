"""K-4 — keşif adayı terfi kriteri testleri.

- Üç kriter (çözülmüş hacim + TF çeşitliliği + Wilson CI ayrıklığı) bağımsız;
  hepsi tutmadan aday READY olmaz.
- READY aday → governor defterine STRATEGY_ENABLE paketi (aday başına dedupe).
- KIRMIZI ÇİZGİ: READY olsa bile canlı evren (custom_assets/assets.yaml) DEĞİŞMEZ.
"""
from __future__ import annotations

import pytest

from packages.discovery import promotion as dp


@pytest.fixture
def gov_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GOVERNOR_PROPOSALS_PATH", str(tmp_path / "proposals.json"))
    return tmp_path


def _cand(missed: int, avoided: int, tfs: list[str], expired: int = 0) -> dict:
    n = missed + avoided + expired
    dec = missed + avoided
    return {
        "n_signals": n, "resolved": n,
        "missed_win": missed, "avoided_loss": avoided, "expired": expired,
        "cf_win_rate": round(missed / dec, 4) if dec else None,
        "avg_r": None, "timeframes": tfs, "last_signal_at": None,
    }


# --------------------------------------------------------------- değerlendirme

def test_empty_not_ready() -> None:
    out = dp.evaluate(candidates={})
    assert out["status"] == "NOT_READY"
    assert out["ready_symbols"] == []


def test_ready_when_all_criteria_hold() -> None:
    cands = {"XLV": _cand(19, 1, ["1h", "4h"])}  # dec=20, cf=0.95, 2 TF
    out = dp.evaluate(candidates=cands)
    assert out["status"] == "READY"
    ev = out["per_candidate"]["XLV"]
    assert ev["checks"]["resolved_decisive"]["pass"] is True
    assert ev["checks"]["timeframe_spread"]["pass"] is True
    assert ev["checks"]["ci_disjoint"]["pass"] is True
    assert ev["checks"]["ci_disjoint"]["wilson_low"] > 0.5


def test_volume_without_ci_not_ready() -> None:
    """Hacim + TF var ama isabet 50-50 → Wilson ayrık değil → NOT_READY."""
    cands = {"XLE": _cand(10, 10, ["1h", "4h"])}  # dec=20, cf=0.5
    out = dp.evaluate(candidates=cands)
    ev = out["per_candidate"]["XLE"]
    assert ev["checks"]["resolved_decisive"]["pass"] is True
    assert ev["checks"]["timeframe_spread"]["pass"] is True
    assert ev["checks"]["ci_disjoint"]["pass"] is False
    assert out["status"] == "NOT_READY"


def test_single_timeframe_not_ready() -> None:
    """İsabet + hacim güçlü ama tek TF → çeşitlilik kriteri düşer."""
    cands = {"IYT": _cand(19, 1, ["1h"])}
    out = dp.evaluate(candidates=cands)
    ev = out["per_candidate"]["IYT"]
    assert ev["checks"]["ci_disjoint"]["pass"] is True
    assert ev["checks"]["timeframe_spread"]["pass"] is False
    assert out["status"] == "NOT_READY"


def test_insufficient_volume_not_ready() -> None:
    cands = {"XLF": _cand(8, 1, ["1h", "4h"])}  # dec=9 < 20
    out = dp.evaluate(candidates=cands)
    ev = out["per_candidate"]["XLF"]
    assert ev["checks"]["resolved_decisive"]["pass"] is False
    assert out["status"] == "NOT_READY"


def test_expired_not_counted_in_decisive() -> None:
    """expired paydaya girmez: 19/1 kararlı + 50 expired hâlâ dec=20."""
    cands = {"XLK": _cand(19, 1, ["1h", "4h"], expired=50)}
    out = dp.evaluate(candidates=cands)
    ev = out["per_candidate"]["XLK"]
    assert ev["checks"]["resolved_decisive"]["value"] == 20
    assert out["status"] == "READY"


# --------------------------------------------------------------- run() sarmalayıcı

_READY_PKG = {
    "status": "READY",
    "ready_symbols": ["XLV"],
    "per_candidate": {
        "XLV": {
            "symbol": "XLV", "status": "READY",
            "missed_win": 19, "avoided_loss": 1, "timeframes": ["1h", "4h"],
            "checks": {"ci_disjoint": {"cf_win_rate": 0.95, "wilson_low": 0.75}},
        }
    },
}


def test_run_submits_owner_package_once(gov_env, monkeypatch) -> None:
    """READY aday → governor'a paket; ikinci run YENİ kayıt üretmez (dedupe)."""
    from packages.governor import proposals

    monkeypatch.setattr(dp, "evaluate", lambda: {k: v for k, v in _READY_PKG.items()})
    p1 = dp.run()
    p2 = dp.run()
    assert p1["proposal_ids"] and p1["proposal_ids"] == p2["proposal_ids"]
    pending = proposals.list_pending()
    assert len(pending) == 1
    assert pending[0]["source"] == "discovery_promotion"
    assert pending[0]["proposal_type"] == "STRATEGY_ENABLE"
    assert pending[0]["requested_change"] == {"add_custom_asset": "XLV"}
    assert pending[0]["requires_owner_approval"] is True


def test_not_ready_does_not_submit(gov_env, monkeypatch) -> None:
    from packages.governor import proposals

    monkeypatch.setattr(dp, "evaluate", lambda: {"status": "NOT_READY", "ready_symbols": []})
    out = dp.run()
    assert out["proposal_ids"] == []
    assert proposals.list_pending() == []


def test_red_line_no_universe_change(gov_env, tmp_path, monkeypatch) -> None:
    """KIRMIZI ÇİZGİ: READY paket sunumu custom_assets/assets'e HİÇBİR ŞEY yazmaz."""
    monkeypatch.setenv("CUSTOM_ASSETS_PATH", str(tmp_path / "custom_assets.yaml"))
    monkeypatch.setattr(dp, "evaluate", lambda: {k: v for k, v in _READY_PKG.items()})
    dp.run()
    assert not (tmp_path / "custom_assets.yaml").exists()
