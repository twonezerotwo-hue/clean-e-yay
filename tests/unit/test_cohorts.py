"""Denetim 2026-07-03 — AUTO/MANUAL/EXCLUDED kohort ayrımı.

Bulgu: tek bir manuel pending emir (+$2,456) tüm learning özetini kârlı
gösteriyordu. cohorts.py bu kayıtları ayırır; summary additive gömer.
"""
from __future__ import annotations

from packages.learning import cohorts
from packages.learning.outcomes import CanonicalOutcome


def _oc(
    *,
    pnl: float = 0.0,
    fingerprint: str | None = "bullish|touche|NEUTRAL",
    verified: bool = True,
    open_reason: str | None = None,
    close_reason: str | None = "TP_HIT",
    timeframe: str = "1h",
) -> CanonicalOutcome:
    return CanonicalOutcome(
        trade_id="t",
        symbol="BTCUSD",
        timeframe=timeframe,
        opened_at=None,
        closed_at=None,
        duration_seconds=None,
        direction="long",
        open_price=None,
        close_price=None,
        pnl=pnl,
        pnl_pct=None,
        open_reason=open_reason,
        close_reason=close_reason,
        fingerprint=fingerprint,
        regime="NEUTRAL",
        dominant_module="touche",
        candidate_action="open_long",
        final_action="open_long",
        data_verified=verified,
    )


# ── classify: üç kohortun sınırları ───────────────────────────────────────────

def test_fingerprint_and_verified_is_auto():
    assert cohorts.classify(_oc()) == cohorts.AUTO


def test_owner_manual_is_manual():
    o = _oc(fingerprint=None, open_reason="owner_manual")
    assert cohorts.classify(o) == cohorts.MANUAL


def test_owner_flip_and_pending_are_manual():
    assert cohorts.classify(_oc(fingerprint=None, verified=False, open_reason="owner_flip")) == cohorts.MANUAL
    assert cohorts.classify(_oc(fingerprint=None, verified=False, open_reason="pending_stop_limit")) == cohorts.MANUAL


def test_no_fingerprint_no_reason_is_excluded():
    """+$2,456'lık yanılsamanın kaynağı: reason'sız, fingerprint'siz kayıt."""
    o = _oc(fingerprint=None, verified=False, open_reason=None, pnl=2456.36)
    assert cohorts.classify(o) == cohorts.EXCLUDED


def test_fingerprint_but_unverified_is_excluded():
    """Fingerprint var ama veri doğrulanmamış → auto sayılmaz (trainer'la hizalı)."""
    o = _oc(verified=False)
    assert cohorts.classify(o) == cohorts.EXCLUDED


# ── cohort_summary: istatistikler ─────────────────────────────────────────────

def test_summary_splits_pnl_by_cohort():
    outs = [
        _oc(pnl=10.0),                                                        # auto win
        _oc(pnl=-30.0),                                                       # auto loss
        _oc(pnl=0.0),                                                         # auto breakeven
        _oc(fingerprint=None, open_reason="owner_manual", pnl=-15.0),         # manual
        _oc(fingerprint=None, verified=False, open_reason=None, pnl=500.0),   # excluded
    ]
    per = cohorts.cohort_summary(outs)
    assert per["auto"]["trades"] == 3
    assert per["auto"]["total_pnl"] == -20.0
    assert per["auto"]["breakeven"] == 1
    # F1-2 deseni: BE payda dışı → 1 win / 2 kararlı işlem
    assert per["auto"]["win_rate"] == 0.5
    assert per["manual"]["trades"] == 1
    assert per["manual"]["total_pnl"] == -15.0
    assert per["excluded"]["trades"] == 1
    assert per["excluded"]["total_pnl"] == 500.0


def test_auto_by_timeframe_isolated_from_manual():
    """1d yanılsaması: manuel 1d kârı auto 1d bucket'ına SIZMAZ."""
    outs = [
        _oc(timeframe="1d", pnl=-10.0),
        _oc(timeframe="1d", fingerprint=None, open_reason="pending_stop_limit", pnl=2456.0, verified=False),
    ]
    per = cohorts.cohort_summary(outs)
    assert per["auto"]["by_timeframe"]["1d"]["total_pnl"] == -10.0
    assert per["manual"]["total_pnl"] == 2456.0


def test_manual_closed_counts_owner_exits_on_auto_trades():
    outs = [
        _oc(close_reason="MANUAL"),
        _oc(close_reason="TP_HIT"),
        _oc(fingerprint=None, open_reason="owner_manual", close_reason="MANUAL"),  # manual kohort — sayılmaz
    ]
    per = cohorts.cohort_summary(outs)
    assert per["auto"]["manual_closed"] == 1


def test_empty_is_safe():
    per = cohorts.cohort_summary([])
    assert per["auto"]["trades"] == 0
    assert per["auto"]["win_rate"] == 0.0
    assert per["auto"]["by_timeframe"] == {}
    assert per["manual"]["trades"] == 0
    assert per["excluded"]["trades"] == 0


def test_build_summary_embeds_cohorts_additively():
    """summary.build_summary mevcut alanları değiştirmeden cohorts ekler."""
    from packages.learning import summary as summary_mod

    out = summary_mod.build_summary()
    assert "cohorts" in out
    assert set(out["cohorts"].keys()) == {"auto", "manual", "excluded"}
    # additive garanti: eski alanlar durur
    assert "total_trades" in out and "by_timeframe" in out
