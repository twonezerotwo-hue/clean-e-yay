"""F5-2 — champion/challenger terfi kriteri testleri.

- Üç kriter (eşleşmiş hacim + ayrışma kanıtı + Wilson CI ayrıklığı) bağımsız
  değerlendirilir; hepsi tutmadan READY olmaz.
- READY → governor defterine owner paketi sunulur (dedupe: tek PENDING).
- KIRMIZI ÇİZGİ: READY olsa bile hiçbir canlı config/weights DEĞİŞMEZ.
"""
from __future__ import annotations

import json

import pytest

from packages.data.registry.loader import threshold_override
from packages.learning import promotion_criteria as pc

_LOW_BAR = {"promotion_criteria": {"min_matched_decisions": 4, "min_resolved_disagreements": 5}}


@pytest.fixture
def promo_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "shadow.jsonl"))
    monkeypatch.setenv("MISSED_OPP_LOG_PATH", str(tmp_path / "missed_opp.jsonl"))
    monkeypatch.setenv("GOVERNOR_PROPOSALS_PATH", str(tmp_path / "proposals.json"))
    return tmp_path


def _write_shadow(tmp_path, n_records: int, symbols_per_record: int = 2) -> None:
    rows = []
    for _i in range(n_records):
        rows.append({
            "symbols": [
                {"symbol": f"S{j}", "agreement": "AGREE_FLAT" if j % 2 else "SHADOW_ONLY_ENTRY"}
                for j in range(symbols_per_record)
            ]
        })
    (tmp_path / "shadow.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
    )


def _write_resolves(tmp_path, wins: int, losses: int) -> None:
    rows = [
        {"event": "resolve", "id": f"w{i}", "outcome": "missed_win", "timeframe": "1h"}
        for i in range(wins)
    ] + [
        {"event": "resolve", "id": f"l{i}", "outcome": "avoided_loss", "timeframe": "1h"}
        for i in range(losses)
    ]
    (tmp_path / "missed_opp.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
    )


def test_empty_logs_not_ready(promo_env) -> None:
    out = pc.evaluate()
    assert out["status"] == "NOT_READY"
    assert not out["checks"]["matched_decisions"]["pass"]
    assert not out["checks"]["ci_disjoint"]["pass"]  # n=0 → CI iddiası yok


def test_volume_without_ci_not_ready(promo_env) -> None:
    """Hacim var ama challenger isabeti 50-50 → CI ayrık değil → NOT_READY."""
    _write_shadow(promo_env, 3)  # 6 eşleşmiş karar ≥ 4
    _write_resolves(promo_env, wins=5, losses=5)  # 10 ≥ 5 ama p=0.5
    with threshold_override(_LOW_BAR):
        out = pc.evaluate()
    assert out["checks"]["matched_decisions"]["pass"] is True
    assert out["checks"]["resolved_disagreements"]["pass"] is True
    assert out["checks"]["ci_disjoint"]["pass"] is False
    assert out["status"] == "NOT_READY"


def test_ready_when_all_criteria_hold(promo_env) -> None:
    _write_shadow(promo_env, 3)
    _write_resolves(promo_env, wins=19, losses=1)  # p=0.95, n=20 → Wilson alt >0.5
    with threshold_override(_LOW_BAR):
        out = pc.evaluate()
    assert out["status"] == "READY"
    ci = out["checks"]["ci_disjoint"]
    assert ci["wilson_low"] > 0.5
    assert out["challenger_wins"] == 19 and out["champion_wins"] == 1


def test_run_submits_owner_package_once(promo_env) -> None:
    """READY → governor'a paket; ikinci run YENİ kayıt üretmez (dedupe)."""
    from packages.governor import proposals

    _write_shadow(promo_env, 3)
    _write_resolves(promo_env, wins=19, losses=1)
    with threshold_override(_LOW_BAR):
        p1 = pc.run()
        p2 = pc.run()
    assert p1["status"] == "READY" and p1["proposal_id"]
    assert p2["proposal_id"] == p1["proposal_id"]  # dedupe — tek PENDING
    pending = proposals.list_pending()
    assert len(pending) == 1
    assert pending[0]["source"] == "promotion_criteria"
    assert pending[0]["proposal_type"] == "STRATEGY_ENABLE"
    assert pending[0]["requires_owner_approval"] is True


def test_red_line_no_live_change_on_ready(promo_env, tmp_path, monkeypatch) -> None:
    """KIRMIZI ÇİZGİ: READY paket sunumu weights/rebalance'a HİÇBİR ŞEY yazmaz."""
    monkeypatch.setenv("REBALANCE_STORE_PATH", str(tmp_path / "rebalance.json"))
    monkeypatch.setenv("WEIGHTS_MANIFEST_PATH", str(tmp_path / "weights_active.json"))
    _write_shadow(promo_env, 3)
    _write_resolves(promo_env, wins=19, losses=1)
    with threshold_override(_LOW_BAR):
        pc.run()
    assert not (tmp_path / "rebalance.json").exists()
    assert not (tmp_path / "weights_active.json").exists()


def test_not_ready_does_not_submit(promo_env) -> None:
    from packages.governor import proposals

    _write_shadow(promo_env, 1)
    with threshold_override(_LOW_BAR):
        out = pc.run()
    assert out["status"] == "NOT_READY"
    assert "proposal_id" not in out
    assert proposals.list_pending() == []
