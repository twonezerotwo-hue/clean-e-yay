"""Günlük "neden kaçırdım" incelemesi: hareket ölçüsü, maruziyet, aday saatleri, kapalı süre, metin."""
from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from packages.learning import daily_review as dr

DAY = date(2026, 11, 12)
D0 = datetime(2026, 11, 12, tzinfo=UTC).timestamp()
D1 = D0 + 86400


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, UTC).isoformat()


def _bars(day_ret: float, n_before: int = 200, n_in: int = 24) -> list[tuple[float, float]]:
    """Önce ±%0,3 dalgalanma, sonra gün içinde düzgün dağılmış toplam `day_ret`."""
    out, c = [], 100.0
    for i in range(n_before):
        c *= math.exp(0.003 * (1 if i % 2 else -1))
        out.append((D0 - (n_before - i) * 3600, c))
    step = math.log(1 + day_ret) / n_in
    for i in range(n_in):
        c *= math.exp(step)
        out.append((D0 + i * 3600, c))
    return out


def test_day_move_scales_by_own_volatility() -> None:
    import statistics

    series = _bars(-0.05)
    before = [c for t, c in series if t < D0][-169:]
    sigma = statistics.stdev(math.log(before[k + 1] / before[k]) for k in range(168))
    pct, z = dr.day_move(series, D0, D1)
    assert pct == pytest.approx(-5.0, abs=0.01)
    assert z == pytest.approx(math.log(0.95) / (sigma * math.sqrt(24)), rel=1e-9)
    assert dr.day_move(_bars(-0.05, n_before=30), D0, D1) is None  # σ için yetersiz geçmiş
    assert dr.day_move(_bars(-0.05)[:200], D0, D1) is None  # gün içinde bar yok


def test_exposure_classifies_caught_reverse_and_missed() -> None:
    def tr(sym, side, opened, closed, pnl):
        return {"symbol": sym, "side": side, "opened_at": _iso(opened), "closed_at": _iso(closed), "pnl": pnl}

    audit = [
        tr("BTCUSD", "short", D0 + 3600, D0 + 7200, 4.5),
        tr("BTCUSD", "short", D1 - 60, D1 + 60, 99.0),           # ertesi gün kapandı → pnl o günün
        tr("ETHUSD", "long", D0 + 3600, D0 + 4000, -1.0),
        tr("XAGUSD", "short", D0 - 10 * 86400, D1 + 5400, 6.5),  # 10 gün önce açık, ertesi gün kapandı
        tr("COPPER", "short", D0 - 7200, D0 - 60, 1.0),          # gün başlamadan kapandı
    ]
    assert dr.exposure("BTCUSD", False, audit, [], D0, D1) == ("YAKALANDI", 4.5)  # ertesi günün kapanışı pnl'e girmez
    assert dr.exposure("ETHUSD", False, audit, [], D0, D1)[0] == "TERS"
    assert dr.exposure("XAGUSD", False, audit, [], D0, D1) == ("YAKALANDI", 0.0)
    assert dr.exposure("COPPER", False, audit, [], D0, D1)[0] == "KAÇIRILDI"
    assert dr.exposure("XAUUSD", False, audit, [], D0, D1)[0] == "KAÇIRILDI"
    held = [{"symbol": "XAUUSD", "side": "short", "opened_at": _iso(D0 - 86400)}]
    assert dr.exposure("XAUUSD", False, audit, held, D0, D1)[0] == "YAKALANDI"
    later = [{"symbol": "XAUUSD", "side": "short", "opened_at": _iso(D1 + 600)}]
    assert dr.exposure("XAUUSD", False, audit, later, D0, D1)[0] == "KAÇIRILDI"


def _cell(sym: str, tf: str, cand: str, action: str = "hold", blocked: list[str] | None = None) -> dict:
    return {"symbol": sym, "timeframe": tf, "candidate": cand, "action": action, "blocked_by": blocked or []}


def test_hourly_view_rebuilds_state_from_checkpoints_and_deltas() -> None:
    seed = [_cell("BTCUSD", "1h", "open_short", blocked=["risk_gate:NO_POSITION_INCREASE"])]
    rows = [
        {"ts": _iso(D0 + 600), "kind": "delta", "cells": []},                                   # 00: seed geçerli
        {"ts": _iso(D0 + 3600 + 60), "kind": "delta",
         "cells": [_cell("BTCUSD", "1h", "open_short", blocked=["entry_quality_v2:reduce", "confidence_floor"])]},
        {"ts": _iso(D0 + 2 * 3600 + 60), "kind": "checkpoint",                                  # 02: hepsi yeniden
         "cells": [_cell("BTCUSD", "15m", "open_short", action="open_short"), _cell("ETHUSD", "1h", "open_long")]},
        {"ts": _iso(D0 + 5 * 3600), "kind": "delta", "cells": [_cell("BTCUSD", "15m", "hold")]},  # 03–04 kapalı
        {"ts": _iso(D1 + 60), "kind": "delta", "cells": []},                                      # ertesi gün yok sayılır
    ]
    view = dr.hourly_view(seed, rows, D0, D1)
    assert sorted(view) == ["2026-11-12T00", "2026-11-12T01", "2026-11-12T02", "2026-11-12T05"]
    assert view["2026-11-12T00"][("BTCUSD", "short")] == "risk_gate"
    assert view["2026-11-12T01"][("BTCUSD", "short")] == "confidence_floor"   # küçültme etiketi atlanır
    assert view["2026-11-12T02"] == {("BTCUSD", "short"): "açıldı", ("ETHUSD", "long"): "diğer"}
    assert ("BTCUSD", "short") not in view["2026-11-12T05"]


def test_hourly_view_prefers_1h_over_other_timeframes() -> None:
    rows = [{"ts": _iso(D0 + 60), "kind": "checkpoint",
             "cells": [_cell("BTCUSD", "15m", "open_short", blocked=["ev_gate"]),
                       _cell("BTCUSD", "1h", "open_short", blocked=["confidence_floor"]),
                       _cell("BTCUSD", "1w", "open_short", blocked=["x"])]}]
    assert dr.hourly_view([], rows, D0, D1)["2026-11-12T00"][("BTCUSD", "short")] == "confidence_floor"


def test_downtime_counts_long_gaps_including_day_edges() -> None:
    ts = [D0 + 4 * 3600, D0 + 4 * 3600 + 20 * 60, D0 + 12 * 3600, D0 + 23 * 3600 + 50 * 60]
    # 00:00→04:00 (4 sa) + 04:20→12:00 (7,67 sa) + 12:00→23:50 (11,83 sa); 23:50→24:00 (10 dk) sayılmaz
    assert dr.downtime_hours(ts, D0, D1) == pytest.approx(4 + 7 + 40 / 60 + 11 + 50 / 60)
    assert dr.downtime_hours([], D0, D1) == 24


def test_news_stats_counts_direction_and_median_lag() -> None:
    heads = [
        {"ts": _iso(D0 + 100), "recorded_at": _iso(D0 + 100 + 600), "symbols": {"BTCUSD": -1.0}},
        {"ts": _iso(D0 + 200), "recorded_at": _iso(D0 + 200 + 1800), "symbols": {"BTCUSD": 1.0, "ETHUSD": 1.0}},
        {"ts": _iso(D0 + 300), "recorded_at": _iso(D0 + 300 + 3600), "symbols": {"BTCUSD": -1.0}},
        {"ts": _iso(D1 + 300), "recorded_at": _iso(D1 + 400), "symbols": {"BTCUSD": -1.0}},
    ]
    assert dr.news_stats("BTCUSD", False, heads, D0, D1) == (3, 2, 30.0)


def test_review_and_message_explain_what_was_missed_and_why() -> None:
    bars = {"BTCUSD": _bars(-0.06), "XAUUSD": _bars(-0.03), "COPPER": _bars(0.0005)}
    trades = [{"symbol": "XAUUSD", "side": "short", "opened_at": _iso(D0 - 9 * 86400), "closed_at": _iso(D0 + 3600),
               "pnl": 22.9}]
    # 00:00–06:00 arası 20 dakikada bir kayıt (kesintisiz), sonra sistem kapanıyor.
    changes = {0: [_cell("BTCUSD", "1h", "open_short", blocked=["confidence_floor"])],
               120: [_cell("BTCUSD", "1h", "open_short", blocked=["ev_gate"])],
               180: [_cell("BTCUSD", "1h", "hold")]}
    rows = [{"ts": _iso(D0 + m * 60), "kind": "delta", "cells": changes.get(m, [])} for m in range(0, 361, 20)]
    rep = dr.review(DAY, bars=bars, trades=trades, open_positions=[], seed_cells=[], record_rows=rows, headlines=[])
    assert [m["symbol"] for m in rep["movers"]] == ["BTCUSD", "XAUUSD"]  # COPPER sakin
    btc = rep["movers"][0]
    assert btc["status"] == "KAÇIRILDI" and btc["candidate_hours"] == 3
    assert btc["blockers"] == [["confidence_floor", 2], ["ev_gate", 1]] or btc["blockers"] == [("confidence_floor", 2), ("ev_gate", 1)]
    assert rep["downtime_hours"] == pytest.approx(18.0, abs=0.1)
    n = dr.notification(rep, datetime(2026, 11, 13, 0, 20, tzinfo=UTC))
    assert n.type == "review_recommendation"
    assert n.title == "Günlük inceleme 12.11: 2 büyük hareket, 1 kaçırıldı/ters"
    assert "1) BTCUSD −%6,0" in n.body_long
    assert "KAÇIRILDI — 3 saat short adayı vardı; durduran: güven tabanı (2 sa), beklenen değer kapısı (1 sa)" in n.body_long
    assert "2) XAUUSD −%3,0" in n.body_long and "YAKALANDI; günün kapanan sonucu +22,90 $" in n.body_long
    assert n.body_short == "BTCUSD −%6,0 kaçırıldı · XAUUSD −%3,0 yakalandı"
    assert "Sistem günün 18,0 saatinde kapalıydı" in n.body_long
    assert "yalnız gözlemdir" in n.body_long


def test_quiet_day_message() -> None:
    rep = dr.review(DAY, bars={"COPPER": _bars(0.0005)}, trades=[], open_positions=[], seed_cells=[],
                    record_rows=[{"ts": _iso(D0 + h * 1800), "kind": "delta", "cells": []} for h in range(48)],
                    headlines=[])
    n = dr.notification(rep, datetime(2026, 11, 13, 0, 20, tzinfo=UTC))
    assert "büyük hareket yok" in n.title and "kapalıydı" not in n.body_long


def test_run_if_due_writes_once_after_quarter_past_midnight(tmp_path, monkeypatch) -> None:
    cache_dir = tmp_path / "ohlcv"
    cache_dir.mkdir()
    rec = tmp_path / "runtime" / "decision_record"
    rec.mkdir(parents=True)
    monkeypatch.setenv("OHLCV_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("DECISION_RECORD_DIR", str(rec))
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "ps.json"))
    monkeypatch.setenv("NEWS_EVENT_LEDGER_PATH", str(tmp_path / "news.jsonl"))
    monkeypatch.setenv("NOTIFICATIONS_PATH", str(tmp_path / "notifs.jsonl"))
    monkeypatch.setattr("packages.notifications.NOTIFICATIONS_PATH", tmp_path / "notifs.jsonl")
    monkeypatch.setattr(dr, "_closed_trades", lambda: [])
    monkeypatch.setattr("packages.data.registry.assets.trade_symbols", lambda: ["BTCUSD"])
    monkeypatch.setattr("packages.data.registry.assets.get", lambda s: SimpleNamespace(asset_class="crypto"))
    bars = [{"symbol": "BTCUSD", "timeframe": "1h", "ts": _iso(t), "open": c, "high": c, "low": c, "close": c,
             "source": "test", "verified": True} for t, c in _bars(-0.06)]
    (cache_dir / "BTCUSD_1h.json").write_text(json.dumps({"symbol": "BTCUSD", "timeframe": "1h",
                                                         "fetched_at": _iso(D1), "bars": bars}), encoding="utf-8")
    (rec / "2026-11-11.jsonl").write_text(json.dumps({"ts": _iso(D0 - 600), "kind": "checkpoint",
                                                      "cells": [_cell("BTCUSD", "1h", "open_short", blocked=["ev_gate"])]}) + "\n",
                                          encoding="utf-8")
    (rec / "2026-11-12.jsonl").write_text(json.dumps({"ts": _iso(D0 + 120), "kind": "delta", "cells": []}) + "\n",
                                          encoding="utf-8")

    assert dr.run_if_due(datetime(2026, 11, 13, 0, 10, tzinfo=UTC)) is None  # 00:15'ten önce değil
    rep = dr.run_if_due(datetime(2026, 11, 13, 0, 20, tzinfo=UTC))
    assert rep is not None and rep["day"] == "2026-11-12"
    assert rep["movers"][0]["candidate_hours"] == 1 and rep["movers"][0]["blockers"][0][0] == "ev_gate"  # önceki günden tohum
    assert (tmp_path / "runtime" / "daily_review" / "2026-11-12.json").exists()
    notifs = (tmp_path / "notifs.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(notifs) == 1 and json.loads(notifs[0])["type"] == "review_recommendation"
    assert dr.run_if_due(datetime(2026, 11, 13, 0, 25, tzinfo=UTC)) is None  # bir kez
    assert len((tmp_path / "notifs.jsonl").read_text(encoding="utf-8").splitlines()) == 1
