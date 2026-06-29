"""G3 — dar-bant otomatik ağırlık uygulaması + outcome-bazlı rollback.

Politika:
- Otonom yol (worker): proposal dar bantta (|delta| ≤ band) + auto-apply açık →
  OTOMATİK uygulanır (manifest yazılır, approved_by="auto"). Bant dışı / kapalı /
  izlemede → PENDING (owner). API propose/approve yolu bu testlerin KAPSAMI DIŞINDA
  ve değişmez.
- Aynı anda tek izlenen değişiklik: aktif auto-apply varken yeni proposal PENDING.
- Rollback: apply sonrası ≥ MIN yeni verified outcome birikince post-apply
  expectancy baseline'ın altına düşerse manifest önceki versiyona geri alınır;
  düşmezse CONFIRMED.
"""
from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture
def g3_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("DECISION_LOG_PATH", str(tmp_path / "decision_log.jsonl"))
    monkeypatch.setenv("REBALANCE_STORE_PATH", str(tmp_path / "rebalance.json"))
    monkeypatch.setenv("WEIGHTS_MANIFEST_PATH", str(tmp_path / "weights_active.json"))
    monkeypatch.setenv("WEIGHTS_OUTPUT_DIR", str(tmp_path / "weights_out"))
    monkeypatch.setenv("WEIGHT_AUTOAPPLY_PATH", str(tmp_path / "weight_autoapply.json"))
    # Default knob'lar: AÇIK / band 0.05 / min 15. Testler gerektikçe ezer.
    monkeypatch.delenv("REBALANCE_AUTO_APPLY", raising=False)
    monkeypatch.delenv("REBALANCE_AUTO_APPLY_BAND", raising=False)
    monkeypatch.delenv("REBALANCE_ROLLBACK_MIN_OUTCOMES", raising=False)
    from packages.paper import state as ps
    importlib.reload(ps)
    return {"tmp": tmp_path, "ps": ps}


def _proposal(deltas, *, version="1.1.0"):
    return {
        "from_version": "1.0.0",
        "to_version": version,
        "generated_at": "2026-06-11T00:00:00+00:00",
        "regime": "NEUTRAL",
        "deltas": deltas,
        "proposed_yaml": {"regimes": {"NEUTRAL": {"touche": 0.5, "fundamental": 0.5}}},
    }


def _seed_outcomes(ps, n, pnl, closed_at):
    st = ps.load()
    for i in range(n):
        st.recent_trades.append(ps.Trade(
            id=f"o{closed_at}{i}", symbol="BTCUSD", side="long", entry_price=100.0,
            exit_price=101.0, pnl_usd=pnl, opened_at="2026-12-31T00:00:00+00:00",
            closed_at=closed_at, close_reason="TP_HIT", data_verified=True, timeframe="1d",
        ))
    ps.save(st)


def _manifest(tmp):
    p = tmp / "weights_active.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# ── auto-apply gate ──────────────────────────────────────────────────────────

def test_within_band_auto_applies(g3_env):
    from packages.learning import rebalance_store as rs
    from packages.learning import weight_autoapply_store as aas
    res = rs.maybe_auto_apply(
        _proposal([
            {"module": "touche", "old": 0.50, "new": 0.53, "delta": 0.03},
            {"module": "fundamental", "old": 0.50, "new": 0.47, "delta": -0.03},
        ]),
        baseline_expectancy=0.0, baseline_n=5,
    )
    assert res["decision"] == "auto_applied"
    assert res["status"] == "AUTO_APPLIED"
    man = _manifest(g3_env["tmp"])
    assert man and man["version"] == "1.1.0" and man["approved_by"] == "auto"
    active = aas.get_active()
    assert active and active["applied_version"] == "1.1.0" and active["prev_version"] == "1.0.0"
    assert rs.get_pending() is None  # otomatik uygulandı, owner kuyruğunda yok


def test_out_of_band_stays_pending(g3_env):
    from packages.learning import rebalance_store as rs
    from packages.learning import weight_autoapply_store as aas
    res = rs.maybe_auto_apply(
        _proposal([{"module": "touche", "old": 0.50, "new": 0.60, "delta": 0.10}]),
        baseline_expectancy=0.0, baseline_n=5,
    )
    assert res["decision"] == "pending_out_of_band"
    assert _manifest(g3_env["tmp"]) is None  # manifest YAZILMADI
    assert aas.get_active() is None
    assert rs.get_pending() is not None


def test_disabled_stays_pending(g3_env, monkeypatch):
    monkeypatch.setenv("REBALANCE_AUTO_APPLY", "0")
    from packages.learning import rebalance_store as rs
    res = rs.maybe_auto_apply(
        _proposal([{"module": "touche", "old": 0.50, "new": 0.52, "delta": 0.02}]),
        baseline_expectancy=0.0, baseline_n=5,
    )
    assert res["decision"] == "pending_disabled"
    assert _manifest(g3_env["tmp"]) is None
    assert rs.get_pending() is not None


def test_custom_band_env_widens_gate(g3_env, monkeypatch):
    monkeypatch.setenv("REBALANCE_AUTO_APPLY_BAND", "0.15")
    from packages.learning import rebalance_store as rs
    res = rs.maybe_auto_apply(
        _proposal([{"module": "touche", "old": 0.50, "new": 0.60, "delta": 0.10}]),
        baseline_expectancy=0.0, baseline_n=5,
    )
    assert res["decision"] == "auto_applied"  # 0.10 ≤ 0.15


def test_active_monitoring_routes_next_to_pending(g3_env):
    from packages.learning import rebalance_store as rs
    rs.maybe_auto_apply(
        _proposal([{"module": "touche", "old": 0.50, "new": 0.52, "delta": 0.02}]),
        baseline_expectancy=0.0, baseline_n=5,
    )
    res2 = rs.maybe_auto_apply(
        _proposal([{"module": "touche", "old": 0.52, "new": 0.54, "delta": 0.02}],
                  version="1.2.0"),
        baseline_expectancy=0.0, baseline_n=5,
    )
    assert res2["decision"] == "pending_monitoring"  # tek-değişiklik-tek-doğrulama
    assert rs.get_pending() is not None


# ── rollback / confirm ───────────────────────────────────────────────────────

def _apply_one(rs, *, baseline):
    rs.maybe_auto_apply(
        _proposal([{"module": "touche", "old": 0.50, "new": 0.52, "delta": 0.02}]),
        baseline_expectancy=baseline, baseline_n=10,
    )


def test_monitoring_until_min_outcomes(g3_env):
    from packages.learning import rebalance_store as rs
    from packages.learning import weight_rollback as wr
    _apply_one(rs, baseline=0.0)
    _seed_outcomes(g3_env["ps"], 5, 10.0, "2027-01-01T00:00:00+00:00")  # < 15
    res = wr.check_rollback()
    assert res["status"] == "monitoring" and res["post_n"] == 5


def test_rollback_when_expectancy_drops(g3_env):
    from packages.learning import rebalance_store as rs
    from packages.learning import weight_autoapply_store as aas
    from packages.learning import weight_rollback as wr
    _apply_one(rs, baseline=100.0)  # yüksek baseline
    assert _manifest(g3_env["tmp"])["version"] == "1.1.0"
    _seed_outcomes(g3_env["ps"], 15, 10.0, "2027-01-01T00:00:00+00:00")  # ort 10 < 100
    res = wr.check_rollback()
    assert res["status"] == "ROLLED_BACK"
    assert res["reverted_to"] == "1.0.0"
    # prev manifest yoktu → geri alış manifest'i siler (baseline v1.0.0)
    assert _manifest(g3_env["tmp"]) is None
    assert aas.get_active() is None
    assert any(h.get("event") == "ROLLED_BACK" for h in aas.history())


def test_confirm_when_expectancy_holds(g3_env):
    from packages.learning import rebalance_store as rs
    from packages.learning import weight_autoapply_store as aas
    from packages.learning import weight_rollback as wr
    _apply_one(rs, baseline=0.0)  # düşük baseline
    _seed_outcomes(g3_env["ps"], 15, 50.0, "2027-01-01T00:00:00+00:00")  # ort 50 ≥ 0
    res = wr.check_rollback()
    assert res["status"] == "CONFIRMED"
    assert _manifest(g3_env["tmp"])["version"] == "1.1.0"  # KORUNUR
    assert aas.get_active() is None


def test_rollback_restores_previous_manifest(g3_env):
    """Önceden bir manifest varsa (v1.0.0), rollback onu geri yazar (silmez)."""
    from packages.learning import rebalance_store as rs
    from packages.learning import weight_rollback as wr
    # Önceden var olan owner-onaylı manifest.
    (g3_env["tmp"] / "weights_active.json").write_text(
        json.dumps({"version": "1.0.0", "yaml_path": "config/weights_v1.0.yaml",
                    "approved_by": "owner"}), encoding="utf-8")
    _apply_one(rs, baseline=100.0)
    assert _manifest(g3_env["tmp"])["version"] == "1.1.0"  # auto-apply üstüne yazdı
    _seed_outcomes(g3_env["ps"], 15, -5.0, "2027-01-01T00:00:00+00:00")
    res = wr.check_rollback()
    assert res["status"] == "ROLLED_BACK"
    man = _manifest(g3_env["tmp"])
    assert man and man["version"] == "1.0.0" and man["approved_by"] == "owner"  # geri yazıldı


def test_no_active_is_safe(g3_env):
    from packages.learning import weight_rollback as wr
    assert wr.check_rollback() == {"status": "no_active"}


def test_proposal_endpoint_surfaces_auto_apply(g3_env):
    """G3 cockpit yüzeyi: GET .../rebalance/proposal auto_apply bloğunu döndürür."""
    from fastapi.testclient import TestClient

    from packages.learning import rebalance_store as rs
    _apply_one(rs, baseline=0.0)

    from apps.api import main as api_main
    importlib.reload(api_main)
    client = TestClient(api_main.app)
    r = client.get("/api/v1/learning/rebalance/proposal")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "auto_apply" in body
    assert body["auto_apply"]["active"]["applied_version"] == "1.1.0"
    assert any(e.get("event") == "AUTO_APPLIED" for e in body["auto_apply"]["ledger"])
