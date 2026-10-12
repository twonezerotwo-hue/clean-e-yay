"""Giriş motoru terfisi — NEW (entry_quality_v2) = PRIMARY, LEGACY = SHADOW + TEKNİK FALLBACK.

Güvenceler (kullanıcı senaryoları A–J + ek):
- Geçerli LONG / SHORT / WAIT yeni motorun kararıdır; WAIT teknik hata DEĞİLDİR ve legacy'nin
  LONG/SHORT'uyla ezilmez.
- Yeni motor TEKNİK olarak başarısızsa (istisna, NaN/inf, bozuk karar/rapor, eksik bağlam,
  geçersiz eylem, gecikme aşımı) legacy karar uygulanır — RiskGate'i atlamadan.
- RiskGate her motor ve her yolda İLK sırada kalır; gölge (legacy) sonuç icraata sızmaz.
- Karşılaştırma telemetrisi (agreement, applied_engine, fallback_reason, sayaçlar) doğrudur.
- off / shadow / active deterministik davranır.
"""
from __future__ import annotations

import importlib
import logging
from types import SimpleNamespace

import pytest

from packages.decision import entry_engine
from packages.scoring import entry_quality

# ------------------------------------------------------------------ yardımcılar


def _ctx(**kw) -> dict:
    base = {"v": 1, "range_pos": {"20": 0.5, "60": 0.5, "120": 0.5}, "ext_ema20": 0.0,
            "ext_ema50": 0.0, "ext_vwap": None, "rsi": 50.0, "bb_pctb": 0.5,
            "move5_atr": 0.0, "run_dir": 0, "run_len": 0, "events": [], "pullback": None}
    base.update(kw)
    return base


def _bad_short_ctx() -> dict:
    """Düşüşün dibinde, aşırı uzamış → short için KÖTÜ giriş (geçerli WAIT)."""
    return _ctx(range_pos={"20": 0.02, "60": 0.02, "120": 0.02}, ext_ema20=-3.8, ext_ema50=-6.5,
                rsi=18.0, bb_pctb=-0.15, move5_atr=-6.5, run_dir=-1, run_len=4)


def _bad_long_ctx() -> dict:
    return _ctx(range_pos={"20": 0.98, "60": 0.98, "120": 0.98}, ext_ema20=3.8, ext_ema50=6.5,
                rsi=84.0, bb_pctb=1.15, move5_atr=6.5, run_dir=1, run_len=4)


def _good_short_ctx() -> dict:
    return _ctx(ext_ema20=-0.4, rsi=44.0)


def _good_long_ctx() -> dict:
    return _ctx(ext_ema20=0.4, rsi=56.0)


@pytest.fixture(autouse=True)
def _clean_stats():
    entry_engine.reset_stats()
    yield
    entry_engine.reset_stats()


@pytest.fixture
def fresh_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("CALIBRATION_STORE_PATH", str(tmp_path / "platt.json"))
    monkeypatch.setenv("GUARD_OVERRIDES_PATH", str(tmp_path / "guard_overrides.json"))
    from packages.paper import state as ps
    importlib.reload(ps)
    return ps


def _set_mode(monkeypatch, m: str) -> None:
    monkeypatch.setattr(entry_quality, "mode", lambda: m)
    monkeypatch.setattr(entry_quality, "zero_two_canonical", lambda: False)


def _force(monkeypatch, *, score: float, direction: str, ctx: dict | None):
    from packages.consensus.engine import ConsensusResult, ModuleScore
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision import engine as dec
    from packages.regime.classifier import classify
    snap = build_snapshot(["BTCUSD"])
    snap.entry_contexts = {"BTCUSD": {"1d": ctx}} if ctx else {}
    regime = classify(snap)
    fake = ConsensusResult(
        symbol="BTCUSD", score=score, direction=direction, confluence_aligned=True,
        dominant_module="touche",
        modules=[ModuleScore(name="touche", score=score, weight=1.0, contribution=score)],
    )
    monkeypatch.setattr(dec, "build_consensus", lambda *a, **kw: fake)
    return dec, snap, regime


def _risk(action: str = "HOLD"):
    from packages.risk.engine import RiskDecision
    return RiskDecision(action=action, reason="t", evidence=[])


def _decide(dec, snap, regime, risk_action: str = "HOLD"):
    return dec.decide_for_symbol("BTCUSD", snap, regime, _risk(risk_action),
                                 equity_usd=100_000, timeframe="1d")


SHORT = dict(score=15.0, direction="bearish")
LONG = dict(score=85.0, direction="bullish")


# ------------------------------------------------------------------ A / B: geçerli LONG / SHORT

def test_A_valid_long_is_applied_by_new_engine(fresh_env, monkeypatch):
    dec, snap, regime = _force(monkeypatch, ctx=_good_long_ctx(), **LONG)
    _set_mode(monkeypatch, "active")
    d = _decide(dec, snap, regime)
    rep = d.entry_quality_report
    assert d.action == "open_long" and d.size_multiplier > 0
    assert rep["applied_engine"] == "new" and rep["applied"] is True
    assert rep["fallback_reason"] is None and rep["verdict"] == "ok"
    assert rep["legacy_action"] == rep["new_action"] == "open_long" and rep["agreement"] is True
    assert entry_engine.stats()["fallback_total"] == 0


def test_B_valid_short_is_applied_by_new_engine(fresh_env, monkeypatch):
    dec, snap, regime = _force(monkeypatch, ctx=_good_short_ctx(), **SHORT)
    _set_mode(monkeypatch, "active")
    d = _decide(dec, snap, regime)
    rep = d.entry_quality_report
    assert d.action == "open_short" and d.size_multiplier > 0
    assert rep["applied_engine"] == "new" and rep["fallback_reason"] is None
    assert rep["legacy_action"] == rep["new_action"] == "open_short" and rep["agreement"] is True


# ------------------------------------------------------------------ C: geçerli WAIT = karar, fallback DEĞİL

@pytest.mark.parametrize("side,ctx_fn,cand", [
    (SHORT, _bad_short_ctx, "open_short"),
    (LONG, _bad_long_ctx, "open_long"),
])
def test_C_valid_wait_is_applied_and_legacy_never_overrides_it(fresh_env, monkeypatch, side, ctx_fn, cand):
    dec, snap, regime = _force(monkeypatch, ctx=ctx_fn(), **side)
    _set_mode(monkeypatch, "active")
    d = _decide(dec, snap, regime)
    rep = d.entry_quality_report
    assert d.action == "hold" and d.size_multiplier == 0.0 and d.actionable is False
    assert d.candidate_action == cand                          # yön korunur, zıt yön YOK
    assert rep["applied_engine"] == "new" and rep["fallback_reason"] is None
    assert rep["legacy_action"] == cand                        # legacy açacaktı…
    assert rep["new_action"] == "hold" and rep["agreement"] is False   # …yeni WAIT dedi, WAIT kazandı
    assert d.blocked_by == ["entry_quality_v2:entry_quality"]
    assert entry_engine.stats()["fallback_total"] == 0         # WAIT sayaçta fallback görünmez


# ------------------------------------------------------------------ D: istisna → legacy fallback

def test_D_exception_in_scoring_falls_back_to_legacy(fresh_env, monkeypatch):
    dec, snap, regime = _force(monkeypatch, ctx=_bad_short_ctx(), **SHORT)
    _set_mode(monkeypatch, "active")

    def boom(*a, **kw):
        raise RuntimeError("synthetic scoring crash")

    monkeypatch.setattr(entry_quality, "assess", boom)
    d = _decide(dec, snap, regime)
    rep = d.entry_quality_report
    assert d.action == "open_short"                            # legacy kararı uygulandı
    assert rep["applied_engine"] == "legacy_fallback" and rep["applied"] is False
    assert rep["fallback_reason"] == "exception:RuntimeError"
    assert rep["new_action"] is None and rep["agreement"] is None
    assert entry_engine.stats()["fallback_total"] == 1
    assert entry_engine.stats()["fallback_reasons"] == {"exception": 1}


def test_D2_failure_anywhere_in_new_decision_object_falls_back_to_legacy(fresh_env, monkeypatch):
    """Kapı dışında (karar nesnesi üretilirken) çıkan istisna da legacy'ye düşer."""
    dec, snap, regime = _force(monkeypatch, ctx=_bad_short_ctx(), **SHORT)
    _set_mode(monkeypatch, "active")

    def boom(*a, **kw):
        raise ValueError("synthetic")

    monkeypatch.setattr(entry_engine, "wait_tags", boom)      # yalnız yeni motorun WAIT yolunda çağrılır
    d = _decide(dec, snap, regime)
    assert d.action == "open_short"
    assert d.entry_quality_report["applied_engine"] == "legacy_fallback"
    assert d.entry_quality_report["fallback_reason"] == "exception:ValueError"
    assert entry_engine.stats()["fallback_total"] == 1


# ------------------------------------------------------------------ E: NaN / bozuk çıktı → legacy

@pytest.mark.parametrize("bad_ctx,reason", [
    (lambda: _bad_short_ctx() | {"ext_ema20": float("nan")}, "non_finite_context"),
    (lambda: _bad_short_ctx() | {"rsi": float("inf")}, "non_finite_context"),
    (lambda: _bad_short_ctx() | {"events": [{"weight": float("nan")}]}, "non_finite_context"),
    (lambda: _bad_short_ctx() | {"events": "bozuk"}, "malformed_context"),
    (lambda: _ctx(range_pos={}), "missing_context"),
    (lambda: _ctx(range_pos={"20": None, "60": None}), "missing_context"),
])
def test_E_non_finite_or_missing_context_falls_back_not_waits(fresh_env, monkeypatch, bad_ctx, reason):
    """NaN bağlam sessizce 'azami uzama' sayılıp sahte WAIT üretmemeli (clamp01(NaN)=1.0 tuzağı)."""
    dec, snap, regime = _force(monkeypatch, ctx=bad_ctx(), **SHORT)
    _set_mode(monkeypatch, "active")
    d = _decide(dec, snap, regime)
    assert d.action == "open_short"                            # sahte WAIT değil: legacy
    assert d.entry_quality_report["applied_engine"] == "legacy_fallback"
    assert d.entry_quality_report["fallback_reason"] == reason


def test_E2_no_context_at_all_falls_back(fresh_env, monkeypatch):
    dec, snap, regime = _force(monkeypatch, ctx=None, **SHORT)
    _set_mode(monkeypatch, "active")
    d = _decide(dec, snap, regime)
    assert d.action == "open_short"
    assert d.entry_quality_report["fallback_reason"] == "missing_context"


@pytest.mark.parametrize("bad_report,reason", [
    ({"verdict": "bogus", "entry_quality": 0.5, "reversal_risk": 0.1, "size_factor": 1.0}, "invalid_verdict"),
    ({"verdict": "ok", "entry_quality": float("nan"), "reversal_risk": 0.1, "size_factor": 1.0}, "invalid_entry_quality"),
    ({"verdict": "ok", "entry_quality": 0.5, "reversal_risk": float("inf"), "size_factor": 1.0}, "invalid_reversal_risk"),
    ({"verdict": "ok", "entry_quality": 0.5, "reversal_risk": 0.1, "size_factor": 1.7}, "invalid_size_factor"),
    ({"verdict": "reduce", "entry_quality": 0.5, "reversal_risk": 0.1, "size_factor": 0.0}, "invalid_size_factor"),
    ({"verdict": "ok", "entry_quality": None, "reversal_risk": 0.1, "size_factor": 1.0}, "invalid_entry_quality"),
])
def test_E3_malformed_assessment_falls_back(fresh_env, monkeypatch, bad_report, reason):
    dec, snap, regime = _force(monkeypatch, ctx=_good_short_ctx(), **SHORT)
    _set_mode(monkeypatch, "active")
    monkeypatch.setattr(entry_quality, "assess", lambda *a, **kw: dict(bad_report))
    d = _decide(dec, snap, regime)
    assert d.action == "open_short"
    assert d.entry_quality_report["applied_engine"] == "legacy_fallback"
    assert d.entry_quality_report["fallback_reason"] == reason


def test_E4_malformed_decision_object_falls_back(fresh_env, monkeypatch):
    dec, snap, regime = _force(monkeypatch, ctx=_good_short_ctx(), **SHORT)
    _set_mode(monkeypatch, "active")
    orig = dec._decide_core

    def corrupt(*a, eq_mode="off", **kw):
        d = orig(*a, eq_mode=eq_mode, **kw)
        if eq_mode == "active":
            d.size_multiplier = float("nan")
        return d

    monkeypatch.setattr(dec, "_decide_core", corrupt)
    d = _decide(dec, snap, regime)
    assert d.size_multiplier == d.size_multiplier and d.action == "open_short"   # NaN değil
    assert d.entry_quality_report["applied_engine"] == "legacy_fallback"
    assert d.entry_quality_report["fallback_reason"] == "non_finite_decision"


def test_E5_invalid_action_and_side_flip_are_technical_failures():
    ok = SimpleNamespace(action="open_short", candidate_action="open_short", size_multiplier=0.5,
                         confidence=0.6, entry_quality_report={"size_factor": 0.8})
    assert entry_engine.decision_problem(ok) is None
    for wait in ("hold", "blocked"):                         # WAIT / blocked geçerli karardır
        assert entry_engine.decision_problem(
            SimpleNamespace(action=wait, candidate_action="open_short", size_multiplier=0.0,
                            confidence=0.0, entry_quality_report={})) is None
    cases = [
        (SimpleNamespace(**{**vars(ok), "action": "sell"}), "invalid_action"),
        (SimpleNamespace(**{**vars(ok), "action": None}), "invalid_action"),
        (SimpleNamespace(**{**vars(ok), "action": "open_long"}), "side_flip"),     # ZIT YÖN yasak
        (SimpleNamespace(**{**vars(ok), "size_multiplier": float("inf")}), "non_finite_decision"),
        (SimpleNamespace(**{**vars(ok), "confidence": float("nan")}), "non_finite_decision"),
        (SimpleNamespace(**{**vars(ok), "size_multiplier": -0.1}), "invalid_size"),
        (SimpleNamespace(**{**vars(ok), "entry_quality_report": {"size_factor": 1.4}}), "invalid_size_factor"),
    ]
    for obj, reason in cases:
        assert entry_engine.decision_problem(obj) == reason, reason


def test_E6_latency_budget_breach_is_a_technical_timeout(fresh_env, monkeypatch):
    dec, snap, regime = _force(monkeypatch, ctx=_bad_short_ctx(), **SHORT)
    _set_mode(monkeypatch, "active")
    clock = iter([0.0, 5.0, 5.0, 5.0, 5.0, 5.0])             # değerlendirme "5 sn" sürdü (bütçe 1 sn)
    monkeypatch.setattr(entry_engine, "perf_counter", lambda: next(clock))
    d = _decide(dec, snap, regime)
    assert d.action == "open_short"
    assert d.entry_quality_report["fallback_reason"] == "timeout"


# ------------------------------------------------------------------ F / G: RiskGate her yolda İLK

@pytest.mark.parametrize("risk_action,expected", [
    ("KILL_SWITCH", "blocked"), ("RISK_REDUCE", "hold"), ("NO_POSITION_INCREASE", "hold"),
])
def test_F_fallback_path_still_goes_through_riskgate(fresh_env, monkeypatch, risk_action, expected):
    dec, snap, regime = _force(monkeypatch, ctx=_good_short_ctx(), **SHORT)
    _set_mode(monkeypatch, "active")
    orig = dec._decide_core

    def active_always_crashes(*a, eq_mode="off", **kw):
        if eq_mode == "active":
            raise RuntimeError("synthetic new-engine crash")
        return orig(*a, eq_mode=eq_mode, **kw)

    monkeypatch.setattr(dec, "_decide_core", active_always_crashes)
    d = _decide(dec, snap, regime, risk_action)
    assert d.action == expected and d.size_multiplier == 0.0   # fallback RiskGate'i ATLAMAZ
    assert d.blocked_by == [f"risk_gate:{risk_action}"]
    assert d.entry_quality_report["applied_engine"] == "legacy_fallback"


@pytest.mark.parametrize("mode", ["off", "shadow", "active"])
@pytest.mark.parametrize("risk_action", ["KILL_SWITCH", "RISK_REDUCE", "NO_POSITION_INCREASE"])
@pytest.mark.parametrize("ctx_fn", [_good_short_ctx, _bad_short_ctx])
def test_G_riskgate_block_stops_every_engine_from_opening(fresh_env, monkeypatch, mode, risk_action, ctx_fn):
    dec, snap, regime = _force(monkeypatch, ctx=ctx_fn(), **SHORT)
    _set_mode(monkeypatch, mode)
    d = _decide(dec, snap, regime, risk_action)
    assert d.action in ("blocked", "hold")
    assert d.size_multiplier == 0.0 and d.actionable is False
    assert d.blocked_by == [f"risk_gate:{risk_action}"]


# ------------------------------------------------------------------ H: gölge (legacy) icraata sızmaz

def test_H_legacy_shadow_result_never_reaches_execution(fresh_env, monkeypatch):
    dec, snap, regime = _force(monkeypatch, ctx=_bad_short_ctx(), **SHORT)
    _set_mode(monkeypatch, "active")
    d = _decide(dec, snap, regime)
    cell = dec.matrix_view(regime, _risk(), [d], snap, ["BTCUSD"])["cells"][0]
    assert cell["entry_quality"]["legacy_action"] == "open_short"   # yalnız telemetri…
    assert cell["action"] == "hold" and cell["paper_action"] == "none"   # …icraat YOK
    assert cell["actionable"] is False and cell["status"] == "NOT_ACTIONABLE"
    # tick worker yalnız hold/blocked dışındaki eylemleri attempt_open'a taşır
    assert d.action in {"blocked", "hold"} and d.size_multiplier == 0.0
    # karar nesnesi legacy KARAR nesnesi taşımaz (yalnız yön/eylem/skor özeti)
    assert not any(hasattr(d, a) for a in ("legacy_decision", "legacy"))


# ------------------------------------------------------------------ I: karşılaştırma telemetrisi

def test_I_disagreement_and_fallback_telemetry_is_exact(fresh_env, monkeypatch):
    dec, snap, regime = _force(monkeypatch, ctx=_good_short_ctx(), **SHORT)
    _set_mode(monkeypatch, "active")
    agree = _decide(dec, snap, regime)                                  # SHORT, SHORT
    snap.entry_contexts = {"BTCUSD": {"1d": _bad_short_ctx()}}
    veto = _decide(dec, snap, regime)                                   # legacy SHORT, yeni WAIT
    snap.entry_contexts = {"BTCUSD": {"1d": _bad_short_ctx() | {"rsi": float("nan")}}}
    fb = _decide(dec, snap, regime)                                     # teknik fallback
    view = dec.matrix_view(regime, _risk(), [agree, veto, fb], snap, ["BTCUSD"])
    eng = view["engine"]
    assert eng["mode"] == "active" and eng["primary"] == "new" and eng["shadow"] == "legacy"
    assert eng["cells"] == 3 and eng["evaluated"] == 2                  # fallback hücresi karşılaştırılmaz
    assert eng["disagreements"] == 1 and eng["disagreement_pct"] == 50.0
    assert eng["new"] == {"long": 0, "short": 1, "wait": 1} and eng["new_unavailable"] == 1
    assert eng["legacy"] == {"long": 0, "short": 3, "wait": 0}
    assert eng["entry_quality_veto"] == 1 and eng["reversal_risk_veto"] == 0
    assert eng["fallback"]["count"] == 1 and eng["fallback"]["reasons"] == {"non_finite_context": 1}
    assert eng["fallback"]["fallback_total"] == 1
    assert eng["gate_ms"]["max"] >= eng["gate_ms"]["avg"] >= 0.0
    cells = {(c["blocked_by"][0] if c["blocked_by"] else c["action"]): c for c in view["cells"]}
    assert cells["entry_quality_v2:entry_quality"]["entry_quality"]["agreement"] is False
    assert [c["entry_quality"]["agreement"] for c in view["cells"]] == [True, False, None]
    assert all(c["entry_quality"]["legacy_direction"] == "bearish" for c in view["cells"])
    assert all(c["entry_quality"]["legacy_score"] == 15.0 == c["entry_quality"].get("new_score", 15.0)
               for c in view["cells"][:2])


def test_I2_reversal_risk_veto_is_counted_separately(fresh_env, monkeypatch):
    ev = {"kind": "choch", "direction": "bullish", "bar": 99, "ts": "2026-01-01T00:00:00+00:00",
          "strength": 1.0, "confidence": 1.0, "age": 0, "half_life": 8.0}
    dec, snap, regime = _force(monkeypatch, ctx=_ctx(events=[ev]), **SHORT)
    _set_mode(monkeypatch, "active")
    d = _decide(dec, snap, regime)
    if d.action != "hold":
        pytest.skip("sentetik olay bu yapılandırmada reversal_wait eşiğini geçmedi")
    eng = dec.matrix_view(regime, _risk(), [d], snap, ["BTCUSD"])["engine"]
    assert eng["reversal_risk_veto"] + eng["entry_quality_veto"] >= 1


def test_I3_fallback_logging_is_rate_limited(caplog):
    caplog.set_level(logging.WARNING, logger="packages.decision.entry_engine")
    for _ in range(200):
        entry_engine.count_fallback("exception:ValueError", "BTCUSD", "1d")
    warnings = [r for r in caplog.records if "teknik fallback" in r.getMessage()]
    assert len(warnings) == 1                                  # log spam yok
    assert entry_engine.stats() == {"fallback_total": 200, "fallback_reasons": {"exception": 200}}


# ------------------------------------------------------------------ J: off / shadow / active deterministik

def _stable(d) -> dict:
    rep = {k: v for k, v in d.entry_quality_report.items() if k != "gate_ms"}   # gate_ms = zaman ölçümü
    return {"action": d.action, "size": d.size_multiplier, "blocked_by": list(d.blocked_by),
            "reason": d.reason, "report": rep}


@pytest.mark.parametrize("mode,action,has_report", [
    ("off", "open_short", False), ("shadow", "open_short", True), ("active", "hold", True),
])
def test_J_modes_are_deterministic_and_distinct(fresh_env, monkeypatch, mode, action, has_report):
    dec, snap, regime = _force(monkeypatch, ctx=_bad_short_ctx(), **SHORT)
    _set_mode(monkeypatch, mode)
    a, b = _decide(dec, snap, regime), _decide(dec, snap, regime)
    assert _stable(a) == _stable(b)                            # aynı girdi → aynı karar
    assert a.action == action and bool(a.entry_quality_report) is has_report
    view = dec.matrix_view(regime, _risk(), [a], snap, ["BTCUSD"])
    assert ("engine" in view) is has_report                    # off: matrix bayt-aynı (blok yok)


def test_J2_off_and_shadow_decisions_are_identical_except_telemetry(fresh_env, monkeypatch):
    dec, snap, regime = _force(monkeypatch, ctx=_bad_short_ctx(), **SHORT)
    _set_mode(monkeypatch, "off")
    off = _decide(dec, snap, regime)
    _set_mode(monkeypatch, "shadow")
    sh = _decide(dec, snap, regime)
    assert (off.action, off.size_multiplier, off.reason, off.blocked_by, off.confidence) == \
           (sh.action, sh.size_multiplier, sh.reason, sh.blocked_by, sh.confidence)


# ------------------------------------------------------------------ ek değişmezler

@pytest.mark.parametrize("side,ctx_fns", [
    (SHORT, (_good_short_ctx, _bad_short_ctx, _bad_long_ctx)),
    (LONG, (_good_long_ctx, _bad_long_ctx, _bad_short_ctx)),
])
def test_active_never_flips_side_even_on_fallback(fresh_env, monkeypatch, side, ctx_fns):
    cand = "open_short" if side is SHORT else "open_long"
    _set_mode(monkeypatch, "active")
    for fn in ctx_fns:
        for broken in (False, True):
            ctx = fn() | ({"ext_ema50": float("nan")} if broken else {})
            dec, snap, regime = _force(monkeypatch, ctx=ctx, **side)
            d = _decide(dec, snap, regime)
            assert d.action in (cand, "hold")                  # asla zıt yön
            assert d.size_multiplier <= 1.5


def test_zero_two_canonical_stays_off_in_live_config():
    """zero_two_canonical AYRI terfidir (canlı yön girdisini değiştirir): entry_quality_v2
    aktivasyonuyla birlikte AÇILMAZ. Bilinçli terfide bu test birlikte güncellenir."""
    assert entry_quality.config().zero_two_canonical is False


def test_gate_never_raises_and_reports_technical_failure_even_for_garbage_snapshot():
    rep = entry_engine.gate(object(), "BTCUSD", "1d", "open_short", "active")
    assert rep["fallback_reason"] == "missing_context" and rep["applied_engine"] == "legacy_fallback"
    rep2 = entry_engine.gate(None, "BTCUSD", "1d", "open_long", "shadow")
    assert rep2["fallback_reason"] == "missing_context" and rep2["applied_engine"] == "legacy"
    assert entry_engine.stats()["fallback_total"] == 1         # shadow'daki başarısızlık sayılmaz


# ------------------------------------------------------------------ yürütme kabiliyeti (karar → gates → paper)

@pytest.mark.usefixtures("seed_ohlcv_reference")   # BTCUSD@60000 referans fiyatı
@pytest.mark.parametrize("fallback", [False, True], ids=["new_engine", "technical_fallback"])
@pytest.mark.parametrize("side_kw,side,ctx_fn", [
    (LONG, "long", _good_long_ctx), (SHORT, "short", _good_short_ctx),
])
def test_execution_capability_long_and_short_still_reach_paper_open(
        fresh_env, monkeypatch, side_kw, side, ctx_fn, fallback):
    """Terfi sonrası emir hattı bozulmadı: izin verilen LONG ve SHORT (hem yeni motor hem teknik
    fallback yolu) gates.apply_gates'ten geçip attempt_open'da paper pozisyonu açabiliyor."""
    from datetime import UTC, datetime

    from packages.decision import conflict_gate, gates
    from packages.paper import lifecycle
    from packages.paper.state import PaperState

    dec, snap, regime = _force(monkeypatch, ctx=ctx_fn(), **side_kw)
    _set_mode(monkeypatch, "active")
    if fallback:
        monkeypatch.setattr(entry_quality, "assess",
                            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("synthetic")))
    d = _decide(dec, snap, regime)
    assert d.action == f"open_{side}" and d.size_multiplier > 0
    assert d.entry_quality_report["applied_engine"] == ("legacy_fallback" if fallback else "new")

    routed = gates.apply_gates(d, side=side, now=datetime.now(UTC), regime=regime,
                               gate_cfg=conflict_gate.ConflictGateConfig(), conflict_by_symbol={})
    assert routed.route in ("open", "manual_ready")             # yeni motor/fallback rotayı bloke etmedi

    state = PaperState(equity_usd=100_000.0, peak_equity_usd=100_000.0)
    pos, decision = lifecycle.attempt_open(
        state, symbol="BTCUSD", side=side, entry_price=60_000.0,
        size_multiplier=d.size_multiplier * max(routed.effective_multiplier, 0.01),
        timeframe="1d", open_reason=d.reason, snapshot_id="snap::t", fingerprint=d.fingerprint,
        data_verified=True, open_dqs=88.0, open_risk_action="HOLD",
        open_blocked_by=list(d.blocked_by), **routed.session_attribution,
    )
    assert pos is not None, decision                            # paper emri KABUL edildi
    assert pos.side == side and pos.symbol == "BTCUSD" and state.open_positions == [pos]


# ------------------------------------------------------------------ bias-only TF (1w): kapı çalışmaz

def _decide_tf(dec, snap, regime, tf: str):
    return dec.decide_for_symbol("BTCUSD", snap, regime, _risk(), equity_usd=100_000, timeframe=tf)


@pytest.mark.parametrize("ctx_kind", ["missing", "bad_short", "nan"])
def test_bias_only_timeframe_never_runs_the_gate_nor_counts_a_fallback(fresh_env, monkeypatch, ctx_kind):
    """1w paper_execution=false (hiç pozisyon açamaz): genç sembolün kısa haftalık geçmişi
    ('missing_context') kalıcı fallback sayacı/log üretmemeli; WAIT de uydurmamalı."""
    ctx = {"missing": None, "bad_short": _bad_short_ctx(),
           "nan": _bad_short_ctx() | {"rsi": float("nan")}}[ctx_kind]
    dec, snap, regime = _force(monkeypatch, ctx=None, **SHORT)
    snap.entry_contexts = {"BTCUSD": {"1w": ctx}} if ctx else {}
    _set_mode(monkeypatch, "active")
    d = _decide_tf(dec, snap, regime, "1w")
    assert d.entry_quality_report == {}                       # kapı hiç çalışmadı
    assert d.blocked_by == ["timeframe_policy:no_paper_execution"] or d.action == "hold"
    assert d.action == "hold" and d.size_multiplier == 0.0
    assert entry_engine.stats()["fallback_total"] == 0
    # legacy ile birebir aynı karar (off): bias hücresi motorlar arasında farklılaşmaz
    _set_mode(monkeypatch, "off")
    off = _decide_tf(dec, snap, regime, "1w")
    assert (d.action, d.reason, d.blocked_by, d.size_multiplier) == \
           (off.action, off.reason, off.blocked_by, off.size_multiplier)


def test_executable_timeframe_still_falls_back_on_missing_context(fresh_env, monkeypatch):
    """Düzeltme yalnız bias-only TF'yi kapsar: pozisyon açabilen TF'de eksik bağlam hâlâ fallback."""
    dec, snap, regime = _force(monkeypatch, ctx=None, **SHORT)
    _set_mode(monkeypatch, "active")
    d = _decide_tf(dec, snap, regime, "1d")
    assert d.action == "open_short"
    assert d.entry_quality_report["fallback_reason"] == "missing_context"
    assert entry_engine.stats()["fallback_total"] == 1
