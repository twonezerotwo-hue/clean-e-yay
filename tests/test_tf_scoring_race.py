"""tf_scoring DOĞRULAMA KARNESİ testleri (İZOLE, salt-gözlem).

Owner kararı (2026-07-12): v4 CANLI teknik oy; karne canlı sınavını tutar
(v4 vs backup vs taban). Kritik güvenceler:
1. Boş defter → dürüst COLLECTING (uydurma yok).
2. Defter yazımı (symbol, speaker_tf, bar_ts) bazında DEDUPE eder; OK-olmayan /
   damgasız / iki-yön-de-boş sembolleri atlar.
3. Çözümleme: v4 doğru yönü tutarsa isabet/getiri artar; backup ve baseline
   ayrı puanlanır; kararsız band-altı hareket elenir.
4. Verdict: yeterli örneklemde v4 yedeği+tabanı geçiyorsa V4_AHEAD, en az
   birinin gerisindeyse V4_BEHIND — rapor yazar, OTOMATİK aksiyon YOK
   (geri-alma owner'ın touche_v4=false tek-satırı).
5. Üretici flag OFF → run() tam no-op (DISABLED).
"""
from __future__ import annotations

import json

import pytest

from packages.learning import tf_scoring_race as race

_SPK = {"UP": "1d", "DOWN": "4h"}


@pytest.fixture(autouse=True)
def _fresh_ledger(tmp_path, monkeypatch):
    """Her teste TEMİZ defter/rapor (session-scoped ortak yol test-arası sızdırırdı)."""
    monkeypatch.setenv("TF_SCORING_RACE_LEDGER", str(tmp_path / "race.jsonl"))
    monkeypatch.setenv("TF_SCORING_RACE_REPORT", str(tmp_path / "race_report.json"))


def _artifact(per_symbol: dict) -> dict:
    return {"per_symbol": per_symbol}


def _sym(v4=None, backup=None, regime="UP", *, tf=None, ts="2026-07-01T00:00:00+00:00",
         close=100.0, status="OK"):
    speaker = tf or _SPK.get(regime or "")
    return {
        "status": status,
        "direction_v4": v4,
        "direction_backup": backup,
        "regime": {"regime": regime, "er": 0.4} if regime else None,
        "speaker_tf": speaker,
        "bar_marks": {speaker: {"ts": ts, "close": close}} if speaker else {},
    }


# ── boş defter ───────────────────────────────────────────────────────────────

def test_empty_ledger_is_collecting():
    rep = race.evaluate()
    assert rep["race_status"] == "COLLECTING"
    assert rep["ledger_rows"] == 0
    assert rep["resolved"] == 0
    assert rep["designs"]["v4"]["hit_rate"] is None
    assert rep["beats_backup"] is None
    assert rep["beats_baseline"] is None


# ── defter yazımı ────────────────────────────────────────────────────────────

def test_append_writes_row_and_dedupes():
    art = _artifact({"BTCUSD": _sym(v4=0.6, backup=0.5, regime="UP")})
    assert race.append_ledger(art) == 1
    # Aynı bar (aynı bar_ts) ikinci kez → DEDUPE (0 yeni satır).
    assert race.append_ledger(art) == 0
    rows = race.read_ledger()
    assert len(rows) == 1
    r = rows[0]
    assert r["symbol"] == "BTCUSD" and r["speaker_tf"] == "1d"
    assert r["v4_dir"] == 0.6 and r["backup_dir"] == 0.5 and r["price_at"] == 100.0


def test_append_new_bar_adds_row():
    race.append_ledger(_artifact({"BTCUSD": _sym(v4=0.6, ts="2026-07-01T00:00:00+00:00")}))
    n = race.append_ledger(_artifact({"BTCUSD": _sym(v4=0.5, ts="2026-07-02T00:00:00+00:00")}))
    assert n == 1
    assert len(race.read_ledger()) == 2


def test_append_speaker_switches_with_regime():
    """UP → 1d konuşur; DOWN → 4h konuşur (damga o TF'ten alınır)."""
    race.append_ledger(_artifact({"ETHUSD": _sym(v4=-0.4, regime="DOWN")}))
    rows = race.read_ledger()
    assert rows[0]["speaker_tf"] == "4h"


def test_append_writes_when_only_backup_present():
    """v4 çekimser olsa bile backup varsa satır yazılır (canlıda backup konuşmuştur)."""
    assert race.append_ledger(_artifact({"BTCUSD": _sym(v4=None, backup=0.3, regime="UP")})) == 1


def test_append_skips_non_ok_and_no_direction():
    art = _artifact({
        "A": _sym(v4=0.5, status="no_evidence"),      # OK değil
        "B": _sym(v4=None, backup=None, regime="UP"),  # iki yön de yok
        "C": _sym(v4=0.5, regime=None),                # rejim yok → konuşan TF yok
    })
    assert race.append_ledger(art) == 0
    assert race.read_ledger() == []


def test_append_skips_missing_bar_mark():
    art = _artifact({"A": {"status": "OK", "direction_v4": 0.5, "direction_backup": 0.4,
                          "regime": {"regime": "UP", "er": 0.4},
                          "speaker_tf": "1d", "bar_marks": {}}})
    assert race.append_ledger(art) == 0


# ── çözümleme + puanlama ─────────────────────────────────────────────────────

def _seed(rows: list[dict]) -> None:
    with race.ledger_path().open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _lrow(v4_dir, *, backup_dir=None, regime="UP", tf="1d", i=0):
    return {"ts": "2026-07-01T00:00:00+00:00", "symbol": f"S{i}", "speaker_tf": tf,
            "regime": regime, "bar_ts": f"2026-07-0{i % 9 + 1}T00:00:00+00:00",
            "price_at": 100.0, "v4_dir": v4_dir, "backup_dir": backup_dir}


def test_v4_correct_direction_scores_hit(monkeypatch):
    # v4 YUKARI dedi, piyasa +%2 → isabet + pozitif getiri.
    _seed([_lrow(0.6, i=1)])
    monkeypatch.setattr(race, "_forward_pct", lambda row: 2.0)
    rep = race.evaluate()
    v4 = rep["designs"]["v4"]
    assert v4["decisive"] == 1 and v4["hits"] == 1
    assert v4["hit_rate"] == 1.0 and v4["avg_return_pct"] == 2.0


def test_v4_wrong_direction_scores_miss(monkeypatch):
    # v4 YUKARI dedi ama piyasa −%2 düştü → ıska + negatif getiri.
    _seed([_lrow(0.6, i=1)])
    monkeypatch.setattr(race, "_forward_pct", lambda row: -2.0)
    rep = race.evaluate()
    v4 = rep["designs"]["v4"]
    assert v4["hits"] == 0 and v4["avg_return_pct"] == -2.0


def test_neutral_band_drops_flat_move(monkeypatch):
    # |getiri| band (0.5%) altında → kararsız; hiçbir tasarım notlanmaz.
    _seed([_lrow(0.6, i=1)])
    monkeypatch.setattr(race, "_forward_pct", lambda row: 0.2)
    rep = race.evaluate()
    assert rep["resolved"] == 1
    assert rep["designs"]["v4"]["decisive"] == 0


def test_unresolved_rows_not_counted(monkeypatch):
    # Arşivde ileri bar yoksa (_forward_pct None) satır çözülmedi sayılır.
    _seed([_lrow(0.6, i=1)])
    monkeypatch.setattr(race, "_forward_pct", lambda row: None)
    rep = race.evaluate()
    assert rep["resolved"] == 0 and rep["designs"]["v4"]["decisive"] == 0


def test_baseline_is_buy_hold(monkeypatch):
    # Piyasa düşüşünde: taban (hep yukarı) ıskalar, v4 (aşağı) isabet eder.
    _seed([_lrow(-0.6, i=1)])
    monkeypatch.setattr(race, "_forward_pct", lambda row: -2.0)
    rep = race.evaluate()
    assert rep["designs"]["v4"]["hits"] == 1          # aşağı dedi, düştü
    assert rep["designs"]["baseline"]["hits"] == 0    # yukarı der, düştü
    assert rep["beats_baseline"] is True


def test_backup_none_skips_only_backup(monkeypatch):
    # backup None → o motor bu satırı atlar; v4 + taban puanlanır.
    _seed([_lrow(0.6, backup_dir=None, i=1)])
    monkeypatch.setattr(race, "_forward_pct", lambda row: 2.0)
    rep = race.evaluate()
    assert rep["designs"]["v4"]["decisive"] == 1
    assert rep["designs"]["backup"]["decisive"] == 0


# ── verdict (rapor yazar, karar owner'ın) ────────────────────────────────────

def test_below_min_resolved_is_collecting(monkeypatch):
    _seed([_lrow(0.6, i=1)])  # tek satır → eşik altı
    monkeypatch.setattr(race, "_forward_pct", lambda row: 2.0)
    assert race.evaluate()["race_status"] == "COLLECTING"


def test_v4_behind_when_loses_to_baseline(monkeypatch):
    # 40 satır, v4 hep doğru ama taban da aynı yönde (+2) → tabanı GEÇMEZ → BEHIND.
    _seed([_lrow(0.6, backup_dir=0.6, i=i) for i in range(40)])
    monkeypatch.setattr(race, "_forward_pct", lambda row: 2.0)
    rep = race.evaluate()
    assert rep["beats_baseline"] is False
    assert rep["race_status"] == "V4_BEHIND"


def test_v4_ahead_when_beats_backup_and_baseline(monkeypatch):
    # UP yarısı (v4 +, backup −) + DOWN yarısı (v4 −, backup +):
    # v4 hep isabet (avg +2); backup hep ıska (avg −2); taban avg 0 → AHEAD.
    up = [_lrow(0.6, backup_dir=-0.6, i=i) for i in range(20)]
    down = [_lrow(-0.6, backup_dir=0.6, regime="DOWN", tf="4h", i=i) for i in range(20, 40)]
    _seed(up + down)
    monkeypatch.setattr(
        race, "_forward_pct",
        lambda row: 2.0 if row["regime"] == "UP" else -2.0,
    )
    rep = race.evaluate()
    assert rep["designs"]["v4"]["avg_return_pct"] == 2.0
    assert rep["designs"]["backup"]["avg_return_pct"] == -2.0
    assert rep["designs"]["baseline"]["avg_return_pct"] == 0.0
    assert rep["beats_backup"] is True and rep["beats_baseline"] is True
    assert rep["race_status"] == "V4_AHEAD"


def test_run_disabled_is_noop(monkeypatch):
    monkeypatch.delenv("TF_SCORING_V2_SHADOW", raising=False)
    assert race.run() == {"status": "DISABLED"}


def test_run_reports_without_side_effects(monkeypatch):
    """run() rapor yazar; governor'a paket SUNMAZ (v4 zaten canlı — otomatik
    aksiyon yok, geri-alma owner'ın tek-satır flag'i)."""
    monkeypatch.setenv("TF_SCORING_V2_SHADOW", "1")
    _seed([_lrow(0.6, i=1)])
    monkeypatch.setattr(race, "_forward_pct", lambda row: 2.0)
    monkeypatch.setattr(race, "append_ledger", lambda artifact=None: 0)
    out = race.run()
    assert out["status"] == "OK" and out["race_status"] == "COLLECTING"
    assert race.report_path().exists()
