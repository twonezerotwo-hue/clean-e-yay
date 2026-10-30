from packages.paper.signal_identity import build_signal_id


def test_signal_identity_is_stable_and_evidence_bound():
    base = dict(symbol="XAUUSD", timeframe="1h", side="short", fingerprint="fp-1")
    assert build_signal_id(**base) == build_signal_id(**base)
    assert build_signal_id(**base, news_setup_id="setup-a") != build_signal_id(**base, news_setup_id="setup-b")
    assert build_signal_id(**base, decision_id="dec-a") != build_signal_id(**base, decision_id="dec-b")
