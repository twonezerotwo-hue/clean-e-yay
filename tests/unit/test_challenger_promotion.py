"""B-4 — challenger ağırlık terfi kriteri testleri.

- Eşleşmeli kıyas: aynı modül skorları, iki ağırlık vektörü (champion vs
  challenger); yön farkı + piyasa gerçeğiyle ayrışma çözülür.
- Üç kriter (eşleşmiş hacim + çözülmüş ayrışma + Wilson CI ayrıklığı) bağımsız;
  hepsi tutmadan READY olmaz.
- READY → governor defterine STRATEGY_ENABLE paketi (dedupe: tek PENDING).
- KIRMIZI ÇİZGİ: READY olsa bile canlı ağırlık/rebalance'a HİÇBİR ŞEY yazılmaz.
"""
from __future__ import annotations

import pytest

from packages.data.registry.loader import threshold_override
from packages.learning import challenger_promotion as cp

# Düşük eşik: hacim/ayrışma testlerini küçük örneklemle kur.
_LOW_BAR = {
    "challenger_weight_promotion": {
        "min_matched_decisions": 4,
        "min_resolved_disagreements": 5,
    }
}
# İki ağırlık vektörü: fark YALNIZ dağılımda (matematik consensus reuse).
_CHAMP = {"NEUTRAL": {"touche": 0.5, "sentinel": 0.5}}
_CHAL = {"NEUTRAL": {"touche": 0.9, "sentinel": 0.1}}


@pytest.fixture
def cp_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GOVERNOR_PROPOSALS_PATH", str(tmp_path / "proposals.json"))
    return tmp_path


def _rec(regime: str, touche: float, sentinel: float, fr: float) -> dict:
    """2 modüllü challenger kaydı. touche=90/sentinel=0 → champion 0.5/0.5 harmanı
    45 (bearish), challenger 0.9/0.1 harmanı 81 (bullish) → ayrışma."""
    return {
        "regime_label": regime,
        "module_contributions": {
            "touche": {"score": touche, "weight": 0.5, "contribution": 0.0},
            "sentinel": {"score": sentinel, "weight": 0.5, "contribution": 0.0},
        },
        "forward_return": fr,
    }


def _eval(records):
    return cp.evaluate(records=records, challenger_weights=_CHAL, champion_weights=_CHAMP)


# --------------------------------------------------------------- saf matematik

def test_blend_direction_reuses_consensus_math() -> None:
    """Aynı skor, iki ağırlık → farklı yön (champion matematiği reuse)."""
    scores = {"touche": 90.0, "sentinel": 0.0}
    assert cp._blend_direction(scores, _CHAMP["NEUTRAL"], 55.0, 45.0) == "bearish"
    assert cp._blend_direction(scores, _CHAL["NEUTRAL"], 55.0, 45.0) == "bullish"


def test_resolve_semantics() -> None:
    assert cp._resolve("bearish", "bullish", "up") == "challenger_win"
    assert cp._resolve("bullish", "bearish", "up") == "champion_win"
    assert cp._resolve("bullish", "bullish", "up") is None      # hemfikir
    assert cp._resolve("bearish", "bullish", None) is None      # piyasa yönsüz
    assert cp._resolve("neutral", "bullish", "down") is None    # ikisi de tutmadı


# --------------------------------------------------------------- değerlendirme

def test_defaults_empty_not_ready(cp_env) -> None:
    """Enjeksiyon yok → gerçek kaynaklar (boş) → NOT_READY, crash yok."""
    out = cp.evaluate(records=[])
    assert out["status"] == "NOT_READY"
    assert out["checks"]["matched_decisions"]["value"] == 0


def test_ready_when_challenger_beats_champion(cp_env) -> None:
    records = [_rec("NEUTRAL", 90, 0, +0.03) for _ in range(19)] + [
        _rec("NEUTRAL", 90, 0, -0.03)  # champion haklı (bearish, piyasa düştü)
    ]
    with threshold_override(_LOW_BAR):
        out = _eval(records)
    assert out["status"] == "READY"
    assert out["challenger_wins"] == 19 and out["champion_wins"] == 1
    assert out["checks"]["ci_disjoint"]["wilson_low"] > 0.5
    assert out["proposed_regimes"] == ["NEUTRAL"]


def test_volume_without_ci_not_ready(cp_env) -> None:
    """Hacim + ayrışma var ama 50-50 → Wilson ayrık değil → NOT_READY."""
    records = [_rec("NEUTRAL", 90, 0, +0.03) for _ in range(5)] + [
        _rec("NEUTRAL", 90, 0, -0.03) for _ in range(5)
    ]
    with threshold_override(_LOW_BAR):
        out = _eval(records)
    assert out["checks"]["matched_decisions"]["pass"] is True
    assert out["checks"]["resolved_disagreements"]["pass"] is True
    assert out["checks"]["ci_disjoint"]["pass"] is False
    assert out["status"] == "NOT_READY"


def test_agreement_matched_but_not_disagreement(cp_env) -> None:
    """İki motor hemfikir (ikisi de bullish) → eşleşme sayılır, ayrışma değil."""
    records = [_rec("NEUTRAL", 90, 90, +0.03) for _ in range(6)]
    with threshold_override(_LOW_BAR):
        out = _eval(records)
    assert out["checks"]["matched_decisions"]["value"] == 6
    assert out["challenger_wins"] == 0 and out["champion_wins"] == 0
    assert out["status"] == "NOT_READY"


def test_flat_market_unresolved(cp_env) -> None:
    """Ayrışma var ama piyasa yönsüz (|fr|≤band) → çözülmez (kanıt değil)."""
    records = [_rec("NEUTRAL", 90, 0, 0.0) for _ in range(6)]
    with threshold_override(_LOW_BAR):
        out = _eval(records)
    assert out["checks"]["matched_decisions"]["value"] == 6
    assert out["challenger_wins"] == 0 and out["champion_wins"] == 0


def test_regime_without_challenger_skipped(cp_env) -> None:
    """Challenger ağırlığı olmayan rejim (DEFENSIVE) eşleşmeye girmez."""
    records = [_rec("DEFENSIVE", 90, 0, +0.03) for _ in range(6)]
    with threshold_override(_LOW_BAR):
        out = _eval(records)
    assert out["checks"]["matched_decisions"]["value"] == 0
    assert out["status"] == "NOT_READY"


# --------------------------------------------------------------- run() sarmalayıcı

_READY_PKG = {
    "status": "READY",
    "challenger_wins": 19,
    "champion_wins": 1,
    "proposed_regimes": ["NEUTRAL"],
    "challenger_weights": {"NEUTRAL": {"touche": 0.9, "sentinel": 0.1}},
    "checks": {"ci_disjoint": {"challenger_win_rate": 0.95, "wilson_low": 0.75}},
}


def test_run_submits_owner_package_once(cp_env, monkeypatch) -> None:
    """READY → governor'a paket; ikinci run YENİ kayıt üretmez (dedupe)."""
    from packages.governor import proposals

    monkeypatch.setattr(cp, "evaluate", lambda: dict(_READY_PKG))
    p1 = cp.run()
    p2 = cp.run()
    assert p1["status"] == "READY" and p1["proposal_id"]
    assert p2["proposal_id"] == p1["proposal_id"]  # dedupe — tek PENDING
    pending = proposals.list_pending()
    assert len(pending) == 1
    assert pending[0]["source"] == "challenger_promotion"
    assert pending[0]["proposal_type"] == "STRATEGY_ENABLE"
    assert pending[0]["requires_owner_approval"] is True
    # promotion_criteria kanalıyla ÇAKIŞMAZ (farklı requested_change anahtarı).
    assert pending[0]["requested_change"] == {"promote_challenger_weights_review": True}


def test_not_ready_does_not_submit(cp_env, monkeypatch) -> None:
    from packages.governor import proposals

    monkeypatch.setattr(cp, "evaluate", lambda: {"status": "NOT_READY", "checks": {}})
    out = cp.run()
    assert "proposal_id" not in out
    assert proposals.list_pending() == []


def test_red_line_no_live_weight_change(cp_env, tmp_path, monkeypatch) -> None:
    """KIRMIZI ÇİZGİ: READY paket sunumu weights/rebalance'a HİÇBİR ŞEY yazmaz."""
    monkeypatch.setenv("REBALANCE_STORE_PATH", str(tmp_path / "rebalance.json"))
    monkeypatch.setenv("WEIGHTS_MANIFEST_PATH", str(tmp_path / "weights_active.json"))
    monkeypatch.setattr(cp, "evaluate", lambda: dict(_READY_PKG))
    cp.run()
    assert not (tmp_path / "rebalance.json").exists()
    assert not (tmp_path / "weights_active.json").exists()
