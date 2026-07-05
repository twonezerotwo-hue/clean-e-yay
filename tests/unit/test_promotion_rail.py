"""I4 — Terfi Hattı testleri.

- count_check / wilson_check / status_of ortak kapı şekillerini üretir.
- wilson_check n=0 sınırında düşmez (rate None, pass False).
- submit_enable STRATEGY_ENABLE owner-onay zarfını + dedupe'u kurar.
- BAYT-AYNI: üç modülün mevcut testleri (test_promotion_criteria /
  test_challenger_promotion / test_discovery_promotion) değişmeden yeşil kalır —
  bu dosya rail'in kendi sözleşmesini kilitler.
"""
from __future__ import annotations

from packages.learning import promotion_rail as rail


def test_count_check_shape() -> None:
    assert rail.count_check(5, 4) == {"value": 5, "required": 4, "pass": True}
    assert rail.count_check(3, 4) == {"value": 3, "required": 4, "pass": False}
    # eşitlik geçer (≥)
    assert rail.count_check(4, 4)["pass"] is True


def test_wilson_check_strong_signal() -> None:
    chk = rail.wilson_check(19, 20, rate_key="challenger_win_rate")
    assert chk["challenger_win_rate"] == 0.95
    assert chk["required"] == "wilson_low > 0.5"
    assert chk["wilson_low"] > 0.5 and chk["pass"] is True
    assert chk["wilson_high"] >= chk["wilson_low"]


def test_wilson_check_coinflip_not_disjoint() -> None:
    chk = rail.wilson_check(5, 10, rate_key="cf_win_rate")
    assert chk["cf_win_rate"] == 0.5
    assert chk["pass"] is False  # 50-50 → alt sınır 0.5 altında


def test_wilson_check_empty_is_safe() -> None:
    chk = rail.wilson_check(0, 0, rate_key="cf_win_rate")
    assert chk["cf_win_rate"] is None
    assert chk["pass"] is False  # n=0 → CI iddiası yok


def test_wilson_check_rate_key_is_dynamic() -> None:
    assert "cf_win_rate" in rail.wilson_check(1, 2, rate_key="cf_win_rate")
    assert "challenger_win_rate" in rail.wilson_check(1, 2, rate_key="challenger_win_rate")


def test_status_of() -> None:
    all_pass = {"a": {"pass": True}, "b": {"pass": True}}
    one_fail = {"a": {"pass": True}, "b": {"pass": False}}
    assert rail.status_of(all_pass) == "READY"
    assert rail.status_of(one_fail) == "NOT_READY"


def test_submit_enable_wraps_strategy_enable(tmp_path, monkeypatch) -> None:
    from packages.governor import proposals

    monkeypatch.setenv("GOVERNOR_PROPOSALS_PATH", str(tmp_path / "proposals.json"))
    out = rail.submit_enable(
        title="t", summary="s", evidence={"x": 1},
        requested_change={"promote_review": True},
        rollback_plan="rb", source="unit_rail",
    )
    assert out and out.get("proposal_id")
    pending = proposals.list_pending()
    assert len(pending) == 1
    p = pending[0]
    assert p["proposal_type"] == "STRATEGY_ENABLE"
    assert p["source"] == "unit_rail"
    assert p["requested_change"] == {"promote_review": True}
    assert p["requires_owner_approval"] is True


def test_submit_enable_dedupes_on_requested_change(tmp_path, monkeypatch) -> None:
    from packages.governor import proposals

    monkeypatch.setenv("GOVERNOR_PROPOSALS_PATH", str(tmp_path / "proposals.json"))
    kw = dict(title="t", summary="s", evidence={}, requested_change={"k": True},
              rollback_plan="rb", source="unit_rail")
    p1 = rail.submit_enable(**kw)
    p2 = rail.submit_enable(**kw)
    assert p1["proposal_id"] == p2["proposal_id"]  # aynı anahtar → tek PENDING
    assert len(proposals.list_pending()) == 1
