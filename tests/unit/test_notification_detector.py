"""packages/notifications/detector.py — bildirim metni testleri.

Kurumsal seviye kontrolü: hiçbir body_short/body_long ham enum değeri
(KILL_SWITCH, RISK_REDUCE, ...) veya İngilizce jargon ("entry") sızdırmamalı;
her zaman Türkçe, kullanıcıya doğrudan okunabilir etiket kullanmalı.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.notifications import detector


def _ticket(**overrides):
    base = {
        "id": "tk_1",
        "status": "active",
        "symbol": "BTCUSD",
        "timeframe": "1h",
        "side": "long",
        "expires_at": None,
        "summary": {
            "entry_price": 60000.0,
            "stop_loss": 59500.0,
            "take_profit": 61000.0,
            "rr_ratio": 2.0,
            "confidence_calibrated": 0.62,
        },
    }
    base.update(overrides)
    return base


# ---------- detect_new_tickets ----------

def test_new_ticket_uses_turkish_giris_not_english_entry():
    out = detector.detect_new_tickets(set(), [_ticket()])
    assert len(out) == 1
    n = out[0]
    assert "entry" not in n.body_short.lower()
    assert "giriş" in n.body_short.lower()
    assert "Zarar Durdur" in n.body_long
    assert "Kâr Al" in n.body_long
    assert "Giriş:" in n.body_long
    assert n.title == "Yeni BTCUSD AL sinyali"


def test_new_ticket_skips_already_seen_and_inactive():
    seen = {"tk_1"}
    out = detector.detect_new_tickets(seen, [_ticket(), _ticket(id="tk_2", status="closed")])
    assert out == []


def test_new_ticket_short_side_label():
    out = detector.detect_new_tickets(set(), [_ticket(side="short")])
    assert "SAT" in out[0].title
    assert "SAT" in out[0].body_short


# ---------- detect_expiring_tickets ----------

def test_expiring_ticket_within_window():
    soon = (datetime.now(UTC) + timedelta(minutes=3)).isoformat()
    out = detector.detect_expiring_tickets([_ticket(expires_at=soon)], warn_minutes=5)
    assert len(out) == 1
    assert out[0].title == "Ticket süresi bitiyor"


def test_expiring_ticket_outside_window_is_skipped():
    far = (datetime.now(UTC) + timedelta(minutes=30)).isoformat()
    out = detector.detect_expiring_tickets([_ticket(expires_at=far)], warn_minutes=5)
    assert out == []


# ---------- detect_recheck_changes ----------

def _recheck(**overrides):
    base = {"position_id": "pos_1", "symbol": "BTCUSD", "timeframe": "1h", "side": "long",
            "verdict": "EXIT_RECOMMEND", "reason": "sinyal zayıfladı"}
    base.update(overrides)
    return base


def test_recheck_exit_recommend_has_no_shouting_or_raw_verdict():
    out = detector.detect_recheck_changes({}, [_recheck()])
    assert len(out) == 1
    n = out[0]
    assert "TERS" not in n.body_short
    assert "EXIT_RECOMMEND" not in n.body_long
    assert "tersine döndü" in n.body_short


def test_recheck_reduce_has_no_raw_jargon():
    out = detector.detect_recheck_changes({}, [_recheck(verdict="REDUCE")])
    assert len(out) == 1
    n = out[0]
    assert "sıkıştı" not in n.body_short
    assert "kısıtlama uyguluyor" in n.body_short


def test_recheck_unchanged_verdict_is_skipped():
    out = detector.detect_recheck_changes({"pos_1": "EXIT_RECOMMEND"}, [_recheck()])
    assert out == []


# ---------- detect_risk_gate_change ----------

def test_risk_gate_escalation_has_no_raw_enum_leak():
    out = detector.detect_risk_gate_change("ALLOW_NORMAL", "KILL_SWITCH", "günlük zarar limiti aşıldı")
    assert len(out) == 1
    n = out[0]
    assert "KILL_SWITCH" not in n.body_short
    assert "KILL_SWITCH" not in n.body_long
    assert "ALLOW_NORMAL" not in n.body_long
    assert n.priority == "critical"
    assert "Tüm girişler durduruldu" in n.body_short


def test_risk_gate_deescalation_is_silent():
    out = detector.detect_risk_gate_change("KILL_SWITCH", "RISK_REDUCE", "iyileşti")
    assert out == []  # gevşeme bildirim üretmez


def test_risk_gate_unknown_action_falls_back_gracefully():
    out = detector.detect_risk_gate_change("ALLOW_NORMAL", "RISK_REDUCE", "drawdown")
    assert len(out) == 1
    assert "RISK_REDUCE" not in out[0].body_short
    assert "Boyut azaltma gerekiyor" in out[0].body_short


# ---------- detect_catalyst_imminent ----------

def test_catalyst_imminent_within_window():
    out = detector.detect_catalyst_imminent(set(), [
        {"id": "cat_1", "title": "FOMC kararı", "importance": "HIGH", "minutes_to_event": 10},
    ])
    assert len(out) == 1
    assert "FOMC kararı" in out[0].title


def test_catalyst_low_importance_is_skipped():
    out = detector.detect_catalyst_imminent(set(), [
        {"id": "cat_1", "title": "Küçük olay", "importance": "LOW", "minutes_to_event": 10},
    ])
    assert out == []


# ---------- detect_dqs_drop ----------

def test_dqs_drop_below_threshold():
    out = detector.detect_dqs_drop(80.0, 60.0, threshold=70)
    assert len(out) == 1
    assert out[0].title == "Veri kalitesi düştü"


def test_dqs_drop_already_below_threshold_is_silent():
    out = detector.detect_dqs_drop(65.0, 60.0, threshold=70)
    assert out == []
