"""R5 — tf_scoring_v2 gölge YARIŞ defteri testleri (İZOLE, salt-gözlem).

Kritik güvenceler:
1. Boş defter → dürüst NOT_READY (uydurma yok).
2. Defter yazımı (symbol, speaker_tf, bar_ts) bazında DEDUPE eder; OK-olmayan /
   damgasız / kanıtsız sembolleri atlar.
3. Çözümleme: yeni beyin doğru yönü tutarsa isabet/getiri artar; taban (buy-hold)
   ayrı puanlanır; kararsız band-altı hareket elenir.
4. Terfi KIRMIZI ÇİZGİsi: kriter tutsa bile owner paketi ÖTESİNDE hiçbir şey
   otomatik terfi etmez (paket = governor önerisi).
5. Gölge flag OFF → run() tam no-op (DISABLED).
"""
from __future__ import annotations

import json

import pytest

from packages.learning import tf_scoring_race as race


@pytest.fixture(autouse=True)
def _fresh_ledger(tmp_path, monkeypatch):
    """Her teste TEMİZ defter/rapor (session-scoped ortak yol test-arası sızdırırdı)."""
    monkeypatch.setenv("TF_SCORING_RACE_LEDGER", str(tmp_path / "race.jsonl"))
    monkeypatch.setenv("TF_SCORING_RACE_REPORT", str(tmp_path / "race_report.json"))


def _artifact(per_symbol: dict) -> dict:
    return {"per_symbol": per_symbol}


def _sym(direction, regime, *, tf="1d", ts="2026-07-01T00:00:00+00:00",
         close=100.0, legacy=None, status="OK"):
    return {
        "status": status,
        "direction": direction,
        "regime": {"regime": regime, "er": 0.4} if regime else None,
        "direction_blend_legacy": legacy,
        "bar_marks": {tf: {"ts": ts, "close": close}},
    }


# ── boş defter ───────────────────────────────────────────────────────────────

def test_empty_ledger_not_ready():
    rep = race.evaluate()
    assert rep["race_status"] == "NOT_READY"
    assert rep["ledger_rows"] == 0
    assert rep["resolved"] == 0
    assert rep["designs"]["new_brain"]["hit_rate"] is None
    assert rep["beats_baseline"] is None


# ── defter yazımı ────────────────────────────────────────────────────────────

def test_append_writes_row_and_dedupes():
    art = _artifact({"BTCUSD": _sym(0.6, "UP", tf="1d")})
    assert race.append_ledger(art) == 1
    # Aynı bar (aynı bar_ts) ikinci kez → DEDUPE (0 yeni satır).
    assert race.append_ledger(art) == 0
    rows = race.read_ledger()
    assert len(rows) == 1
    r = rows[0]
    assert r["symbol"] == "BTCUSD" and r["speaker_tf"] == "1d"
    assert r["new_dir"] == 0.6 and r["price_at"] == 100.0


def test_append_new_bar_adds_row():
    race.append_ledger(_artifact({"BTCUSD": _sym(0.6, "UP", ts="2026-07-01T00:00:00+00:00")}))
    n = race.append_ledger(_artifact({"BTCUSD": _sym(0.5, "UP", ts="2026-07-02T00:00:00+00:00")}))
    assert n == 1
    assert len(race.read_ledger()) == 2


def test_append_speaker_switches_with_regime():
    """UP → 1d konuşur; DOWN → 4h konuşur (damga o TF'ten alınır)."""
    race.append_ledger(_artifact({"ETHUSD": _sym(-0.4, "DOWN", tf="4h")}))
    rows = race.read_ledger()
    assert rows[0]["speaker_tf"] == "4h"


def test_append_skips_non_ok_and_no_evidence():
    art = _artifact({
        "A": _sym(0.5, "UP", status="no_evidence"),   # OK değil
        "B": _sym(None, "UP"),                         # yön yok
        "C": _sym(0.5, None),                          # rejim yok → konuşan TF yok
    })
    assert race.append_ledger(art) == 0
    assert race.read_ledger() == []


def test_append_skips_missing_bar_mark():
    art = _artifact({"A": {"status": "OK", "direction": 0.5,
                          "regime": {"regime": "UP", "er": 0.4}, "bar_marks": {}}})
    assert race.append_ledger(art) == 0


# ── çözümleme + puanlama ─────────────────────────────────────────────────────

def _seed(rows: list[dict]) -> None:
    with race.ledger_path().open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _lrow(new_dir, *, legacy=None, regime="UP", tf="1d", i=0):
    return {"ts": "2026-07-01T00:00:00+00:00", "symbol": f"S{i}", "speaker_tf": tf,
            "regime": regime, "bar_ts": f"2026-07-0{i % 9 + 1}T00:00:00+00:00",
            "price_at": 100.0, "new_dir": new_dir, "legacy_dir": legacy}


def test_new_brain_correct_direction_scores_hit(monkeypatch):
    # Yeni beyin YUKARI dedi, piyasa +%2 → isabet + pozitif getiri.
    _seed([_lrow(0.6, i=1)])
    monkeypatch.setattr(race, "_forward_pct", lambda row: 2.0)
    rep = race.evaluate()
    nb = rep["designs"]["new_brain"]
    assert nb["decisive"] == 1 and nb["hits"] == 1
    assert nb["hit_rate"] == 1.0 and nb["avg_return_pct"] == 2.0


def test_new_brain_wrong_direction_scores_miss(monkeypatch):
    # Yeni beyin YUKARI dedi ama piyasa −%2 düştü → ıska + negatif getiri.
    _seed([_lrow(0.6, i=1)])
    monkeypatch.setattr(race, "_forward_pct", lambda row: -2.0)
    rep = race.evaluate()
    nb = rep["designs"]["new_brain"]
    assert nb["hits"] == 0 and nb["avg_return_pct"] == -2.0


def test_neutral_band_drops_flat_move(monkeypatch):
    # |getiri| band (0.5%) altında → kararsız; hiçbir tasarım notlanmaz.
    _seed([_lrow(0.6, i=1)])
    monkeypatch.setattr(race, "_forward_pct", lambda row: 0.2)
    rep = race.evaluate()
    assert rep["resolved"] == 1
    assert rep["designs"]["new_brain"]["decisive"] == 0


def test_unresolved_rows_not_counted(monkeypatch):
    # Arşivde ileri bar yoksa (_forward_pct None) satır çözülmedi sayılır.
    _seed([_lrow(0.6, i=1)])
    monkeypatch.setattr(race, "_forward_pct", lambda row: None)
    rep = race.evaluate()
    assert rep["resolved"] == 0 and rep["designs"]["new_brain"]["decisive"] == 0


def test_baseline_is_buy_hold(monkeypatch):
    # Piyasa düşüşünde: taban (hep yukarı) ıskalar, yeni beyin (aşağı) isabet eder.
    _seed([_lrow(-0.6, i=1)])
    monkeypatch.setattr(race, "_forward_pct", lambda row: -2.0)
    rep = race.evaluate()
    assert rep["designs"]["new_brain"]["hits"] == 1   # aşağı dedi, düştü
    assert rep["designs"]["baseline"]["hits"] == 0    # yukarı der, düştü
    assert rep["beats_baseline"] is True


def test_legacy_none_skips_only_legacy(monkeypatch):
    # Eski harman None → o tasarım bu satırı atlar; yeni beyin + taban puanlanır.
    _seed([_lrow(0.6, legacy=None, i=1)])
    monkeypatch.setattr(race, "_forward_pct", lambda row: 2.0)
    rep = race.evaluate()
    assert rep["designs"]["new_brain"]["decisive"] == 1
    assert rep["designs"]["legacy"]["decisive"] == 0


# ── terfi kriteri (KIRMIZI ÇİZGİ) ────────────────────────────────────────────

def test_ready_requires_all_gates(monkeypatch):
    # 40 satır, yeni beyin her seferinde doğru + tabanı geçer → READY.
    _seed([_lrow(0.6, legacy=0.6, i=i) for i in range(40)])
    monkeypatch.setattr(race, "_forward_pct", lambda row: 2.0)
    rep = race.evaluate()
    assert rep["checks"]["resolved_decisive"]["pass"] is True
    assert rep["checks"]["ci_disjoint"]["pass"] is True
    # Yeni beyin ve taban aynı yönde (ikisi de +2) → tabanı GEÇMEZ → NOT_READY.
    assert rep["checks"]["beats_baseline"]["pass"] is False
    assert rep["race_status"] == "NOT_READY"


def test_ready_when_beats_baseline(monkeypatch):
    # Yarısı yükseliş (yeni+taban isabet), yarısı düşüş (yalnız yeni isabet):
    # yeni beynin ortalama getirisi tabanı geçer → tüm kapılar → READY.
    up = [_lrow(0.6, i=i) for i in range(20)]
    down = [_lrow(-0.6, regime="DOWN", tf="4h", i=i) for i in range(20, 40)]
    _seed(up + down)
    monkeypatch.setattr(
        race, "_forward_pct",
        lambda row: 2.0 if row["regime"] == "UP" else -2.0,
    )
    rep = race.evaluate()
    assert rep["designs"]["new_brain"]["avg_return_pct"] == 2.0
    assert rep["designs"]["baseline"]["avg_return_pct"] == 0.0
    assert rep["beats_baseline"] is True
    assert rep["race_status"] == "READY"


def test_run_disabled_is_noop(monkeypatch):
    monkeypatch.delenv("TF_SCORING_V2_SHADOW", raising=False)
    assert race.run() == {"status": "DISABLED"}


def test_run_ready_submits_owner_package(monkeypatch):
    monkeypatch.setenv("TF_SCORING_V2_SHADOW", "1")
    _seed([_lrow(0.6, i=i) if i < 20 else _lrow(-0.6, regime="DOWN", tf="4h", i=i)
           for i in range(40)])
    monkeypatch.setattr(race, "_forward_pct",
                        lambda row: 2.0 if row["regime"] == "UP" else -2.0)
    # append_ledger'ı nötrle (gerçek gölge artifact'ı okumasın); READY yolunu ölç.
    monkeypatch.setattr(race, "append_ledger", lambda artifact=None: 0)
    captured = {}
    monkeypatch.setattr(race.rail, "submit_enable",
                        lambda **kw: captured.update(kw) or {"proposal_id": "p1"})
    out = race.run()
    assert out["status"] == "OK" and out["race_status"] == "READY"
    # KIRMIZI ÇİZGİ: yalnız governor önerisi (STRATEGY_ENABLE zarfı); canlı yön yok.
    assert captured["requested_change"] == {"promote_tf_scoring_v2_direction": True}
    assert captured["source"] == "tf_scoring_race"


def test_run_not_ready_no_submit(monkeypatch):
    monkeypatch.setenv("TF_SCORING_V2_SHADOW", "1")
    _seed([_lrow(0.6, i=1)])  # tek satır → eşik altı
    monkeypatch.setattr(race, "_forward_pct", lambda row: 2.0)
    monkeypatch.setattr(race, "append_ledger", lambda artifact=None: 0)
    called = {"n": 0}
    monkeypatch.setattr(race.rail, "submit_enable",
                        lambda **kw: called.update(n=called["n"] + 1))
    out = race.run()
    assert out["race_status"] == "NOT_READY"
    assert called["n"] == 0  # NOT_READY → paket YOK
