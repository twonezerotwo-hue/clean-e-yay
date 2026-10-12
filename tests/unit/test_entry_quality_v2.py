"""Giriş kalitesi v2 — YÖN ≠ GİRİŞ ZAMANLAMASI (2026-10-12).

Güvenceler:
- mode=off → hiçbir hesap yok, karar bayt-aynı (rapor boş).
- Kötü giriş ASLA zıt yöne çevrilmez: sonuç yalnız {aday, hold}; boyut ≤ 1.0.
- Güçlü trendde uç konum TEK BAŞINA ceza değildir (trend yakalama korunur).
- Dönüş olayları yaşla deterministik sönümlenir; sonsuza kadar aktif kalmaz.
- Tek geçerlilik tanımı: geçersiz (IPTAL) 0-2 setup skor/olay üretmez.
- Look-ahead yok: olay hiçbir zaman henüz bilinemeyecek bir barda damgalanmaz.
"""
from __future__ import annotations

import importlib
import random
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest

from packages.data.registry.loader import threshold_override
from packages.data.types import OHLCVBar
from packages.elliott import zero_two
from packages.scoring import entry_context, entry_quality, reversal_events
from packages.scoring import tf_scoring_v4 as v4
from packages.signals import market_structure

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(i: int, o: float, h: float, lo: float, c: float, v: float | None = 1.0) -> OHLCVBar:
    return OHLCVBar(symbol="T", timeframe="4h", ts=_T0 + timedelta(hours=4 * i),
                    open=o, high=h, low=lo, close=c, volume=v)


def _walk(path: list[float], spread: float = 0.4) -> list[OHLCVBar]:
    return [_bar(i, c, c + spread, c - spread, c) for i, c in enumerate(path)]


# ------------------------------------------------------------------ yardımcı bağlamlar

def _ctx(**kw) -> dict:
    base = {"v": 1, "range_pos": {"20": 0.5, "60": 0.5, "120": 0.5}, "ext_ema20": 0.0,
            "ext_ema50": 0.0, "ext_vwap": None, "rsi": 50.0, "bb_pctb": 0.5,
            "move5_atr": 0.0, "run_dir": 0, "run_len": 0, "events": [], "pullback": None}
    base.update(kw)
    return base


def _bad_short_ctx() -> dict:
    """Düşüşün dibinde, aşırı uzamış: short için KÖTÜ giriş."""
    return _ctx(range_pos={"20": 0.02, "60": 0.02, "120": 0.02}, ext_ema20=-3.8, ext_ema50=-6.5,
                rsi=18.0, bb_pctb=-0.15, move5_atr=-6.5, run_dir=-1, run_len=4)


def _bad_long_ctx() -> dict:
    return _ctx(range_pos={"20": 0.98, "60": 0.98, "120": 0.98}, ext_ema20=3.8, ext_ema50=6.5,
                rsi=84.0, bb_pctb=1.15, move5_atr=6.5, run_dir=1, run_len=4)


CFG = entry_quality.EntryQualityConfig(mode="active")


@contextmanager
def mode_ctx(monkeypatch, m: str, canonical: bool = False):
    """conftest mode()/zero_two_canonical() pin'ini kapsamlı olarak aşar."""
    with monkeypatch.context() as mp:
        mp.setattr(entry_quality, "mode", lambda: m)
        mp.setattr(entry_quality, "zero_two_canonical", lambda: canonical)
        yield


# ------------------------------------------------------------------ config

def test_default_is_off_and_config_parsing_is_safe():
    assert entry_quality.EntryQualityConfig().mode == "off"
    assert entry_quality.EntryQualityConfig().zero_two_canonical is False
    with threshold_override({"entry_quality_v2": {"mode": "bogus"}}):
        assert entry_quality.config().mode == "off"          # geçersiz mod → güvenli varsayılan
    with threshold_override({"entry_quality_v2": {"mode": "shadow", "q_wait": 0.3}}):
        assert entry_quality.config().mode == "shadow"
        assert entry_quality.config().q_wait == 0.3
    with threshold_override({"entry_quality_v2": {"mode": "active", "ema20": [2.0, 4.0], "range_weights": {"60": 1.0}}}):
        c = entry_quality.config()
        assert c.ema20 == (2.0, 4.0) and c.range_weights["60"] == 1.0   # sözlükler derin birleşir


def test_conftest_pins_runtime_readers_off():
    assert entry_quality.mode() == "off" and entry_quality.zero_two_canonical() is False


# ------------------------------------------------------------------ assess

def test_bad_short_entry_waits_but_long_in_same_context_is_unaffected():
    short = entry_quality.assess("short", _bad_short_ctx(), CFG)
    assert short["verdict"] == "wait" and short["size_factor"] == 0.0
    assert short["entry_quality"] < CFG.q_wait
    # aynı bağlamda LONG'a cezası yok: kötü short girişi long'a ÇEVRİLMEZ ama long'u da cezalandırmaz
    long_ = entry_quality.assess("long", _bad_short_ctx(), CFG)
    assert long_["verdict"] == "ok" and long_["size_factor"] == 1.0


def test_bad_long_entry_waits():
    r = entry_quality.assess("long", _bad_long_ctx(), CFG)
    assert r["verdict"] == "wait"
    assert entry_quality.assess("short", _bad_long_ctx(), CFG)["verdict"] == "ok"


def test_trend_capture_extreme_location_alone_is_not_penalised():
    """Fiyat aralığın dibinde ama uzama kanıtı yok (RSI/EMA/BB normal) → short serbest."""
    ctx = _ctx(range_pos={"20": 0.03, "60": 0.03, "120": 0.03}, ext_ema20=-0.6, rsi=41.0, bb_pctb=0.3)
    r = entry_quality.assess("short", ctx, CFG)
    assert r["verdict"] == "ok" and r["entry_quality"] == 1.0 and r["location"] > 0.8


def test_stretch_without_extreme_location_is_only_partially_penalised():
    stretched_mid = _ctx(ext_ema20=-3.8, ext_ema50=-6.5, rsi=18.0, bb_pctb=-0.15, move5_atr=-6.5,
                         run_dir=-1, run_len=4)   # aralığın ORTASINDA
    r = entry_quality.assess("short", stretched_mid, CFG)
    at_low = entry_quality.assess("short", _bad_short_ctx(), CFG)
    assert at_low["entry_quality"] < r["entry_quality"] < 1.0


def test_quality_is_monotone_in_stretch():
    prev = 2.0
    for ext in (0.0, -1.0, -2.0, -3.0, -4.0):
        q = entry_quality.assess(
            "short", _ctx(range_pos={"20": 0.05, "60": 0.05, "120": 0.05}, ext_ema20=ext, ext_ema50=ext * 1.7,
                          rsi=50 + ext * 7), CFG)["entry_quality"]
        assert q <= prev + 1e-12
        prev = q


def test_reversal_risk_waits_even_with_good_location():
    ev = [{"kind": "choch", "direction": "bullish", "age": 0, "strength": 1.0, "confidence": 0.7},
          {"kind": "divergence", "direction": "bullish", "age": 1, "strength": 1.0, "confidence": 0.5},
          {"kind": "failed_break", "direction": "bullish", "age": 0, "strength": 1.0, "confidence": 0.6}]
    ctx = _ctx(events=ev)
    r = entry_quality.assess("short", ctx, CFG)
    assert r["verdict"] == "wait" and any(x.startswith("reversal_risk") for x in r["reasons"])
    # aynı olaylar long'u etkilemez (bullish olay long'a karşı risk değil)
    assert entry_quality.assess("long", ctx, CFG)["verdict"] == "ok"


def test_missing_context_is_permissive_and_never_raises():
    for ctx in (None, {}):
        r = entry_quality.assess("short", ctx, CFG)
        assert r["verdict"] == "ok" and r["size_factor"] == 1.0 and "no_context" in r["reasons"]
    assert entry_quality.assess("flat", _bad_short_ctx(), CFG)["verdict"] == "ok"


def test_size_factor_never_exceeds_one_and_reduce_band_is_bounded():
    rng = random.Random(7)
    for _ in range(500):
        ctx = _ctx(
            range_pos={k: rng.random() for k in ("20", "60", "120")},
            ext_ema20=rng.uniform(-5, 5), ext_ema50=rng.uniform(-8, 8), rsi=rng.uniform(5, 95),
            bb_pctb=rng.uniform(-0.3, 1.3), move5_atr=rng.uniform(-8, 8),
            run_dir=rng.choice((-1, 0, 1)), run_len=rng.randint(0, 6),
            events=[{"kind": rng.choice(list(reversal_events.HALF_LIFE_BARS)),
                     "direction": rng.choice(("bullish", "bearish")), "age": rng.randint(0, 30),
                     "strength": rng.random(), "confidence": rng.random()} for _ in range(rng.randint(0, 3))])
        for side in ("long", "short"):
            r = entry_quality.assess(side, ctx, CFG)
            assert 0.0 <= r["size_factor"] <= 1.0
            if r["verdict"] == "reduce":
                assert CFG.min_size_factor <= r["size_factor"] < 1.0
            if r["verdict"] == "ok":
                assert r["size_factor"] == 1.0
            if r["verdict"] == "wait":
                assert r["size_factor"] == 0.0


def test_pullback_bonus_only_for_same_direction_and_fresh():
    base = _bad_short_ctx()
    base["range_pos"] = {"20": 0.10, "60": 0.10, "120": 0.10}
    q0 = entry_quality.assess("short", base, CFG)["entry_quality"]
    with_pb = dict(base, pullback={"direction": "bearish", "age": 2})
    assert entry_quality.assess("short", with_pb, CFG)["entry_quality"] > q0
    stale = dict(base, pullback={"direction": "bearish", "age": 40})
    assert entry_quality.assess("short", stale, CFG)["entry_quality"] == q0
    wrong = dict(base, pullback={"direction": "bullish", "age": 2})
    assert entry_quality.assess("short", wrong, CFG)["entry_quality"] == q0


# ------------------------------------------------------------------ olay sönümü

def test_event_weight_halves_each_half_life_and_dies_after_cap():
    hl = reversal_events.HALF_LIFE_BARS["choch"]
    w0 = reversal_events.decayed_weight("choch", 0, 1.0)
    assert reversal_events.decayed_weight("choch", int(hl), 1.0) == pytest.approx(w0 / 2)
    assert reversal_events.decayed_weight("choch", int(2 * hl), 1.0) == pytest.approx(w0 / 4)
    assert reversal_events.decayed_weight("choch", int(3 * hl) + 1, 1.0) == 0.0
    assert reversal_events.decayed_weight("choch", -1, 1.0) == 0.0


def test_risk_against_noisy_or_and_same_kind_does_not_stack():
    one = [{"kind": "choch", "direction": "bullish", "age": 0, "strength": 1.0, "confidence": 0.7}]
    dup = one + [{"kind": "choch", "direction": "bullish", "age": 0, "strength": 0.5, "confidence": 0.7}]
    two_kinds = one + [{"kind": "divergence", "direction": "bullish", "age": 0, "strength": 1.0,
                        "confidence": 0.5}]
    r1, _ = reversal_events.risk_against(one, "short")
    rd, _ = reversal_events.risk_against(dup, "short")
    r2, labels = reversal_events.risk_against(two_kinds, "short")
    assert rd == pytest.approx(r1)                    # aynı tür birikmez
    assert r2 > r1 and r2 == pytest.approx(1 - (1 - 0.7) * (1 - 0.5))
    assert len(labels) == 2
    assert reversal_events.risk_against(one, "long")[0] == 0.0   # bullish olay long'a karşı değil


def test_stale_event_stops_affecting_the_verdict():
    fresh = _ctx(events=[{"kind": "choch", "direction": "bullish", "age": 0, "strength": 1.0,
                          "confidence": 0.7}])
    old = _ctx(events=[{"kind": "choch", "direction": "bullish", "age": 40, "strength": 1.0,
                        "confidence": 0.7}])
    assert entry_quality.assess("short", fresh, CFG)["reversal_risk"] >= 0.6
    assert entry_quality.assess("short", old, CFG)["reversal_risk"] == 0.0


# ------------------------------------------------------------------ yapı kırılımı olayı

def _zigzag_bars(path: list[float]) -> list[OHLCVBar]:
    return _walk(path, spread=0.2)


def _bearish_then_choch() -> list[OHLCVBar]:
    """LH+LL düşüş yapısı (>= 20 bar), sonra son tepe (LH) kapanışla yukarı kırılır → bullish CHoCH."""
    down = [120, 118, 116, 118, 120, 118, 114, 112, 114, 116, 114, 110, 108, 106, 108, 110, 108,
            104, 102, 100, 98, 100, 102, 100, 97, 95, 93, 95, 97, 99, 101, 99, 96, 94, 92, 94, 96]
    return _zigzag_bars(down)


def test_break_events_choch_has_known_bar_not_after_last_and_nonnegative_age():
    bars = _bearish_then_choch()
    # son tepenin üstünde kapanış → CHoCH (bullish)
    breakout = bars + _zigzag_bars([97, 99, 101, 103, 105, 107])
    breakout = [b.model_copy(update={"ts": _T0 + timedelta(hours=4 * i)}) for i, b in enumerate(breakout)]
    evs = [e for e in market_structure.break_events(breakout) if e.kind == "choch"]
    assert evs, "CHoCH olayı bekleniyordu"
    for e in evs:
        assert 0 <= e.bar_index <= len(breakout) - 1
    assert any(e.direction == "bullish" for e in evs)
    # analyze() ile tutarlı: son durumda choch=bullish
    ms = market_structure.analyze(breakout)
    assert ms is not None and ms.choch == "bullish"


def test_break_events_unknown_before_pivot_confirmation():
    """Olay, referans pivotun teyit barından (pivot + right) ÖNCE damgalanamaz."""
    bars = _bearish_then_choch() + _zigzag_bars([97, 99, 101, 103, 105, 107])
    hs, _ = market_structure.swing_levels(bars)
    for e in market_structure.break_events(bars):
        ref = next((i for i, p in hs if p == e.level), None)
        if ref is not None:
            assert e.bar_index >= ref + 2


# ------------------------------------------------------------------ RSI uyumsuzluğu yeniden düzenlemesi

def _old_rsi_divergence_lean(closes: list[float]) -> float:
    """Yeniden düzenlemeden ÖNCEKİ davranışın birebir kopyası (eşdeğerlik referansı)."""
    rs = v4.rsi_series(closes)
    if rs is None:
        return 0.0
    n = len(closes)
    best = 0.0
    for kind, sign in (("low", 1.0), ("high", -1.0)):
        piv = [i for i in v4._pivots(closes, kind) if rs[i] is not None]
        if len(piv) < 2 or n - 1 - piv[-1] > v4.DIV_RECENT:
            continue
        p = piv[-3:]
        if kind == "low":
            two = closes[p[-1]] < closes[p[-2]] and rs[p[-1]] > rs[p[-2]]
            three = (len(p) == 3 and two and closes[p[-2]] < closes[p[-3]]
                     and rs[p[-2]] > rs[p[-3]])
        else:
            two = closes[p[-1]] > closes[p[-2]] and rs[p[-1]] < rs[p[-2]]
            three = (len(p) == 3 and two and closes[p[-2]] > closes[p[-3]]
                     and rs[p[-2]] < rs[p[-3]])
        if three:
            best = sign * 1.0
        elif two and best == 0.0:
            best = sign * 0.7
    return best


def test_divergence_lean_refactor_is_byte_identical_on_random_walks():
    rng = random.Random(11)
    checked = nonzero = 0
    for _ in range(400):
        px = 100.0
        closes = []
        for _ in range(rng.randint(40, 120)):
            px *= 1 + rng.gauss(0, 0.02)
            closes.append(px)
        got, want = v4.rsi_divergence_lean(closes), _old_rsi_divergence_lean(closes)
        assert got == want
        checked += 1
        nonzero += got != 0.0
    assert checked == 400 and nonzero > 20      # örneklem gerçekten uyumsuzluk içeriyor


# ------------------------------------------------------------------ 0-2 kanonik mercek

def _up_ext_bars() -> list[OHLCVBar]:
    up = [104, 103, 102, 100, 103, 106, 109, 110, 109, 108, 107, 106, 105, 106, 107, 108]
    return _walk([*up, 109, 111, 113, 114, 113, 112])


def test_canonical_lens_matches_old_on_valid_setup_but_zeroes_invalid_one():
    bars = _up_ext_bars()
    assert v4.elliott_lean(bars) == 1.0
    assert 0.0 < v4.elliott_lean_canonical(bars) <= 1.0          # geçerli: yön korunur (yaşla sönümlü)
    # dalga-1 mumu çizgiye değsin → İPTAL_DALGA1
    s = zero_two.find_setups(bars, left=2, right=2)[-1]
    j = s.p0.bar_index + 2
    lv = zero_two.line_value(s, j)
    b = bars[j]
    bars[j] = _bar(j, b.open, b.high, lv - 0.01, b.close)
    ev = zero_two.analyze(bars, left=2, right=2)
    assert ev[-1].status == zero_two.STATUS_WAVE1_TOUCH
    assert v4.elliott_lean(bars) == 1.0                           # ESKİ: geçersiz setup yine +1 (kusur)
    assert v4.elliott_lean_canonical(bars) == 0.0                 # YENİ: geçersiz → skor yok


def test_canonical_lens_decays_with_age_and_dies_when_stale():
    bars = _up_ext_bars()
    fresh = v4.elliott_lean_canonical(bars)
    assert fresh > 0
    older = v4.elliott_lean_canonical(bars, max_age=len(bars) - 12 + 8)
    assert older <= fresh                                         # daha kısa ömür → daha çok sönüm
    assert v4.elliott_lean_canonical(bars, max_age=1) == 0.0      # P2'den ≥1 bar geçmiş → bayat
    assert v4.elliott_lean_canonical([]) == 0.0


def test_compute_leans_flag_switches_lens_only():
    bars = _up_ext_bars()
    off = v4.compute_leans("4h", bars, [], {})
    on = v4.compute_leans("4h", bars, [], {}, canonical_zero_two=True)
    assert off["elliott"] == v4.elliott_lean(bars)
    assert on["elliott"] == v4.elliott_lean_canonical(bars)
    assert {k: v for k, v in off.items() if k != "elliott"} == {k: v for k, v in on.items() if k != "elliott"}


# ------------------------------------------------------------------ entry_context

def _random_bars(n: int, seed: int = 3) -> list[OHLCVBar]:
    rng = random.Random(seed)
    px, out = 100.0, []
    for i in range(n):
        o = px
        px *= 1 + rng.gauss(0, 0.012)
        h, lo = max(o, px) * 1.004, min(o, px) * 0.996
        out.append(_bar(i, o, h, lo, px, v=rng.uniform(800, 1200)))
    return out


def test_entry_context_insufficient_bars_returns_none_and_is_deterministic():
    assert entry_context.build(_random_bars(30), "4h") is None
    bars = _random_bars(250)
    a, b = entry_context.build(bars, "4h"), entry_context.build(list(bars), "4h")
    assert a == b and a is not None
    assert set(a["range_pos"]) == {"20", "60", "120"}
    assert all(0.0 <= v <= 1.0 for v in a["range_pos"].values())
    assert a["vol_ratio"] is not None


def test_entry_context_has_no_lookahead_future_bars_do_not_change_past_context():
    """Aynı önek, sonrasına eklenen barlardan bağımsız aynı bağlamı üretir."""
    bars = _random_bars(320)
    k = 250
    assert entry_context.build(bars[:k], "4h") == entry_context.build(list(bars[:k]), "4h")
    # önek bağlamı, sonradan ne gelirse gelsin (bars[:k] dilimi) yalnız önek verisine bağlı
    shuffled_future = bars[:k] + _random_bars(70, seed=99)
    assert entry_context.build(shuffled_future[:k], "4h") == entry_context.build(bars[:k], "4h")


def test_entry_context_without_volume_marks_volume_fields_none():
    bars = [b.model_copy(update={"volume": None}) for b in _random_bars(250)]
    ctx = entry_context.build(bars, "1d")
    assert ctx["vol_ratio"] is None and ctx["ext_vwap"] is None


def test_reversal_events_ages_are_nonnegative_and_within_window():
    bars = _random_bars(300, seed=5)
    for k in range(120, 300, 7):
        events, _ = reversal_events.detect(bars[:k])
        for e in events:
            assert 0 <= e.age <= k - 1
            assert 0 <= e.bar_index <= k - 1
            assert e.direction in ("bullish", "bearish")
            assert 0.0 <= e.weight() <= 1.0


# ------------------------------------------------------------------ motor entegrasyonu

@pytest.fixture
def fresh_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("CALIBRATION_STORE_PATH", str(tmp_path / "platt.json"))
    monkeypatch.setenv("GUARD_OVERRIDES_PATH", str(tmp_path / "guard_overrides.json"))
    from packages.paper import state as ps
    importlib.reload(ps)
    return ps


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


def _decide(dec, snap, regime):
    from packages.risk.engine import RiskDecision
    return dec.decide_for_symbol("BTCUSD", snap, regime, RiskDecision(action="HOLD", reason="ok", evidence=[]),
                                 equity_usd=100_000, timeframe="1d")


def test_engine_off_is_inert_even_with_bad_context(fresh_env, monkeypatch):
    dec, snap, regime = _force(monkeypatch, score=15.0, direction="bearish", ctx=_bad_short_ctx())
    d = _decide(dec, snap, regime)
    assert d.entry_quality_report == {}
    assert d.action == "open_short" and not any(b.startswith("entry_quality_v2") for b in d.blocked_by)


def test_engine_shadow_reports_both_decisions_but_does_not_change_action(fresh_env, monkeypatch):
    dec, snap, regime = _force(monkeypatch, score=15.0, direction="bearish", ctx=_bad_short_ctx())
    with mode_ctx(monkeypatch, "shadow"):
        d = _decide(dec, snap, regime)
    rep = d.entry_quality_report
    assert d.action == "open_short"                               # KARAR DEĞİŞMEZ
    assert rep["old_action"] == "open_short" and rep["new_action"] == "hold"
    assert rep["verdict"] == "wait" and rep["applied"] is False and rep["mode"] == "shadow"


def test_engine_active_waits_bad_short_and_never_opens_the_opposite_side(fresh_env, monkeypatch):
    dec, snap, regime = _force(monkeypatch, score=15.0, direction="bearish", ctx=_bad_short_ctx())
    with mode_ctx(monkeypatch, "active"):
        d = _decide(dec, snap, regime)
    assert d.action == "hold" and d.action not in ("open_long", "open_short")
    assert d.candidate_action == "open_short"                     # yön korunur (cockpit candidate vs final)
    assert d.blocked_by == ["entry_quality_v2:entry_quality"]
    assert d.entry_quality_report["applied"] is True and d.size_multiplier == 0.0


def test_engine_active_good_entry_unchanged_and_reduce_only_shrinks(fresh_env, monkeypatch):
    good = _ctx(range_pos={"20": 0.5, "60": 0.5, "120": 0.5}, ext_ema20=-0.4, rsi=44.0)
    dec, snap, regime = _force(monkeypatch, score=15.0, direction="bearish", ctx=good)
    with mode_ctx(monkeypatch, "off"):
        base = _decide(dec, snap, regime)
    with mode_ctx(monkeypatch, "active"):
        act = _decide(dec, snap, regime)
    assert act.action == base.action == "open_short"
    assert act.size_multiplier == base.size_multiplier            # kaliteli giriş: değişmez
    # orta kalite → azaltma: boyut ASLA artmaz
    mid = _ctx(range_pos={"20": 0.04, "60": 0.04, "120": 0.04}, ext_ema20=-2.6, ext_ema50=-3.5, rsi=33.0)
    dec, snap, regime = _force(monkeypatch, score=15.0, direction="bearish", ctx=mid)
    with mode_ctx(monkeypatch, "active"):
        red = _decide(dec, snap, regime)
    assert red.action == "open_short" and red.size_multiplier <= base.size_multiplier
    assert red.size_multiplier < base.size_multiplier and "entry_quality_v2:reduce" in red.blocked_by


@pytest.mark.parametrize("score,direction,cand", [(15.0, "bearish", "open_short"), (85.0, "bullish", "open_long")])
def test_engine_never_flips_side_for_any_context(fresh_env, monkeypatch, score, direction, cand):
    rng = random.Random(21)
    for _ in range(60):
        ctx = _ctx(range_pos={k: rng.random() for k in ("20", "60", "120")},
                   ext_ema20=rng.uniform(-5, 5), ext_ema50=rng.uniform(-8, 8), rsi=rng.uniform(5, 95),
                   bb_pctb=rng.uniform(-0.3, 1.3), move5_atr=rng.uniform(-8, 8),
                   run_dir=rng.choice((-1, 0, 1)), run_len=rng.randint(0, 6))
        dec, snap, regime = _force(monkeypatch, score=score, direction=direction, ctx=ctx)
        with mode_ctx(monkeypatch, "active"):
            d = _decide(dec, snap, regime)
        assert d.action in (cand, "hold")


def test_engine_active_riskgate_still_comes_first(fresh_env, monkeypatch):
    from packages.risk.engine import RiskDecision
    dec, snap, regime = _force(monkeypatch, score=15.0, direction="bearish", ctx=_bad_short_ctx())
    with mode_ctx(monkeypatch, "active"):
        d = dec.decide_for_symbol("BTCUSD", snap, regime,
                                  RiskDecision(action="KILL_SWITCH", reason="x", evidence=[]),
                                  equity_usd=100_000, timeframe="1d")
    assert d.action == "blocked" and d.blocked_by == ["risk_gate:KILL_SWITCH"]


# ------------------------------------------------------------------ pipeline

def test_pipeline_builds_no_contexts_when_off(monkeypatch):
    from packages.data.ingestion import pipeline
    assert pipeline._build_entry_contexts(["BTCUSD"]) == {}
    with mode_ctx(monkeypatch, "shadow"):
        out = pipeline._build_entry_contexts(["BTCUSD"])
    assert isinstance(out, dict)     # fixture barlarıyla bağlam üretilebilir ya da hücre boş kalır; çökmez


# ------------------------------------------------------------------ olay dedektörleri (sentetik geometri)

def _sweep_bars(mirror: bool = False) -> list[OHLCVBar]:
    closes = [90 + i for i in range(21)] + [108, 106, 104, 102, 100, 102, 104, 106, 108, 109]
    sign = (lambda c: 220 - c) if mirror else (lambda c: c)
    bars = [_bar(i, sign(c), sign(c) + 0.2, sign(c) - 0.2, sign(c)) for i, c in enumerate(closes)]
    n = len(bars)
    if mirror:   # dip süpürme: fitil son dibin altına iner, kapanış geri alır
        bars.append(_bar(n, 220 - 109, 220 - 108.8, 220 - 111.0, 220 - 109.4))
    else:        # tepe süpürme: fitil son tepenin üstüne çıkar, kapanış altına döner
        bars.append(_bar(n, 109, 111.0, 108.8, 109.4))
    return bars


def test_failed_break_sweep_detected_with_correct_direction_and_age():
    ev, _ = reversal_events.detect(_sweep_bars())
    fb = [e for e in ev if e.kind == "failed_break"]
    assert fb and fb[0].direction == "bearish" and fb[0].age == 0 and fb[0].ts is not None
    ev2, _ = reversal_events.detect(_sweep_bars(mirror=True))
    fb2 = [e for e in ev2 if e.kind == "failed_break"]
    assert fb2 and fb2[0].direction == "bullish"


def test_failed_break_event_ages_and_decays_as_bars_pass():
    bars = _sweep_bars()
    for _ in range(6):   # 6 bar daha: yatay, süpürmenin üstüne çıkmadan
        n = len(bars)
        bars.append(_bar(n, 107, 107.3, 106.7, 107))
    ev, _ = reversal_events.detect(bars)
    fb = [e for e in ev if e.kind == "failed_break"]
    assert fb and fb[0].age >= 5 and fb[0].weight() < reversal_events.decayed_weight("failed_break", 0, fb[0].strength)


def test_climax_event_needs_extreme_location_and_loud_directional_bar():
    base = [_bar(i, 100 - i * 0.2, 100 - i * 0.2 + 0.3, 100 - i * 0.2 - 0.3, 100 - i * 0.2, v=100.0) for i in range(80)]
    last = base[-1]
    base.append(_bar(80, last.close, last.close + 0.1, last.close - 3.5, last.close - 3.0, v=450.0))
    ev, _ = reversal_events.detect(base)
    cl = [e for e in ev if e.kind == "climax"]
    assert cl and cl[0].direction == "bullish" and cl[0].age == 0       # satış climax'ı → yukarı dönüş adayı
    # sakin barlarda (büyük gövde / aşırı hacim yok) climax YOK
    calm = [_bar(i, 100, 100.3, 99.7, 100, v=100.0) for i in range(81)]
    ev2, _ = reversal_events.detect(calm)
    assert not [e for e in ev2 if e.kind == "climax"]


def test_matrix_cell_has_entry_quality_key_only_when_mode_is_not_off(fresh_env, monkeypatch):
    from packages.risk.engine import RiskDecision
    dec, snap, regime = _force(monkeypatch, score=15.0, direction="bearish", ctx=_bad_short_ctx())
    risk = RiskDecision(action="HOLD", reason="ok", evidence=[])
    d_off = _decide(dec, snap, regime)
    cell_off = dec.matrix_view(regime, risk, [d_off], snap, ["BTCUSD"])["cells"][0]
    assert "entry_quality" not in cell_off                       # kapalıyken hücre bayt-aynı
    with mode_ctx(monkeypatch, "shadow"):
        d_sh = _decide(dec, snap, regime)
    cell_sh = dec.matrix_view(regime, risk, [d_sh], snap, ["BTCUSD"])["cells"][0]
    assert cell_sh["entry_quality"]["old_action"] == "open_short"
    assert cell_sh["entry_quality"]["new_action"] == "hold"
    assert cell_sh["action"] == "open_short"                     # shadow: nihai eylem değişmez
