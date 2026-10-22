"""LLM güvenlik ağı: canlı web bulgusu varken LLM 'veri yok' derse deterministik
özeti kullan (modelden bağımsız — zayıf yerel model gerçek veriyi çöpe atmasın)."""
from __future__ import annotations

from packages.agent.llm import chat


def test_denial_with_live_evidence_is_dropped():
    grounded = "Canli web ozeti: Kisa sonuc: Supreme Court rejects Trump's push; heat alerts..."
    llm = "Veri yok.\n\nKaynak: ..."
    assert chat._llm_dropped_findings(llm, grounded, live_evidence=True) is True


def test_no_live_evidence_never_triggers():
    # Web bulgusu yoksa guard çalışmaz (meşru 'yok' cevaplarını vurmaz).
    grounded = "açık pozisyonun yok; kasada $100,000."
    llm = "Şu an açık pozisyonun yok."
    assert chat._llm_dropped_findings(llm, grounded, live_evidence=False) is False


def test_denial_but_grounded_also_denies_not_triggered():
    # Deterministik yanıt da 'veri yok' diyorsa LLM doğru → guard çalışmamalı.
    grounded = "Canli web aramasi bu soru icin sonuc dondurmedi ve elimde haber yok."
    llm = "Haber yok."
    assert chat._llm_dropped_findings(llm, grounded, live_evidence=True) is False


def test_faithful_summary_not_dropped():
    # LLM bulguyu düzgün aktardıysa (denial yok) → guard çalışmaz, LLM cevabı kalır.
    grounded = "Canli web ozeti: SCOTUS kararı, sıcak hava uyarıları..."
    llm = "Öne çıkan haberler: Yüksek Mahkeme kararı ve sıcak hava uyarıları var."
    assert chat._llm_dropped_findings(llm, grounded, live_evidence=True) is False


def _blocker_context() -> dict:
    return {
        "snapshot_id": "snap-test",
        "dqs": {"status": "OK", "score": 80, "notes": []},
        "halt": {"active": False, "events": []},
        "matrix": {
            "suspended": False,
            "risk_gate": {"action": "HOLD", "reason": None},
            "blocked_by_reasons": [
                "concentration_guard",
                "confidence_floor",
                "entry_quality_v2:entry_quality",
            ],
            "paper_actions": [
                {"symbol": "XAUUSD", "timeframe": "1h", "paper_action": "open_short"}
            ],
        },
    }


def test_main_blocker_answer_is_natural_and_keeps_raw_codes_out_of_text():
    text, evidence = chat._grounded_answer("Şu an işlem açmaya en büyük engel ne?", _blocker_context())

    assert "pozisyon yoğunluğu sınırı" in text
    assert "sinyal güveni alt sınırı" in text
    assert "concentration_guard" not in text
    assert "confidence_floor" not in text
    assert "blocked_by:concentration_guard" in evidence
    assert "intent:overview" not in evidence


def test_waiting_answer_translates_blocker_codes():
    text, _ = chat._waiting_answer(_blocker_context())

    assert "pozisyon yoğunluğu sınırı" in text
    assert "concentration_guard" not in text
