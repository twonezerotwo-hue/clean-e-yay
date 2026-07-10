"""G2 — auto-weight trainer + rebalance endpoints.

- Trainer yalnızca data_verified=True trade'leri kullanır.
- Yeterli veri yoksa INSUFFICIENT döner; weights yaml yazılmaz.
- Approve yeni weights_v1.x.yaml yazar + manifest günceller; consensus
  okuduğunda yeni versiyonu görür.
- Reject pending'i siler.
- Bekleyen proposal yokken approve/reject 404 döner.
"""
from __future__ import annotations

import importlib
import json

from fastapi.testclient import TestClient


def _fresh_env(tmp_path, monkeypatch):
    state = tmp_path / "paper_state.json"
    store = tmp_path / "rebalance.json"
    manifest = tmp_path / "weights_active.json"
    out_dir = tmp_path / "weights_out"
    monkeypatch.setenv("PAPER_STATE_PATH", str(state))
    # Trainer artık recent_trades + decision_log birleşiminden öğreniyor →
    # decision_log'u test-bazında izole et. conftest session-scope'ta da izole
    # eder ama o dosya session-paylaşımlı; per-test override başka testlerin
    # yazdığı kayıtlardan da ayırır (dataset_size assertion'ları deterministik).
    monkeypatch.setenv("DECISION_LOG_PATH", str(tmp_path / "decision_log.jsonl"))
    monkeypatch.setenv("REBALANCE_STORE_PATH", str(store))
    monkeypatch.setenv("WEIGHTS_MANIFEST_PATH", str(manifest))
    monkeypatch.setenv("WEIGHTS_OUTPUT_DIR", str(out_dir))

    from packages.paper import state as ps
    importlib.reload(ps)
    from packages.learning import rebalance_store as rs
    importlib.reload(rs)
    from packages.data.registry import loader as ld
    importlib.reload(ld)
    return ps, rs, ld


def _seed_trades(ps, *, n_verified: int, n_unverified: int = 0,
                 fingerprint: str = "BTCUSD|NEUTRAL|bullish|S65|C|touche",
                 win_pnl: float = 120.0,
                 loss_pnl: float = -50.0,
                 wins: int | None = None,
                 id_prefix: str = "v") -> None:
    state = ps.load()
    for i in range(n_verified):
        is_win = i < wins if wins is not None else i % 2 == 0
        state.recent_trades.append(
            ps.Trade(
                id=f"{id_prefix}{i}",
                symbol="BTCUSD",
                side="long",
                entry_price=100.0,
                exit_price=101.0,
                pnl_usd=win_pnl if is_win else loss_pnl,
                opened_at="2026-06-11T00:00:00+00:00",
                closed_at="2026-06-11T01:00:00+00:00",
                close_reason="TP_HIT",
                fingerprint=fingerprint,
                data_verified=True,
            )
        )
    for j in range(n_unverified):
        state.recent_trades.append(
            ps.Trade(
                id=f"u{j}",
                symbol="BTCUSD",
                side="long",
                entry_price=100.0,
                exit_price=99.0,
                pnl_usd=-30.0,
                opened_at="2026-06-11T00:00:00+00:00",
                closed_at="2026-06-11T01:00:00+00:00",
                close_reason="SL_HIT",
                fingerprint=fingerprint,
                data_verified=False,
            )
        )
    ps.save(state)


def _seed_diverse_trades(ps) -> None:
    _seed_trades(
        ps,
        n_verified=6,
        fingerprint="BTCUSD|NEUTRAL|bullish|S65|C|touche",
        wins=6,
        id_prefix="t",
    )
    _seed_trades(
        ps,
        n_verified=6,
        fingerprint="BTCUSD|NEUTRAL|bearish|S35|C|fundamental",
        wins=0,
        id_prefix="f",
    )


def test_trainer_insufficient_when_no_verified_trades(tmp_path, monkeypatch) -> None:
    ps, _, _ = _fresh_env(tmp_path, monkeypatch)
    _seed_trades(ps, n_verified=0, n_unverified=5)
    from packages.learning import auto_weight_trainer as t
    res = t.train(regime="NEUTRAL")
    assert isinstance(res, dict)
    assert res["status"] == "INSUFFICIENT"
    assert res["reason"] == "no_verified_trades"


def test_trainer_below_min_total(tmp_path, monkeypatch) -> None:
    ps, _, _ = _fresh_env(tmp_path, monkeypatch)
    _seed_trades(ps, n_verified=3)
    from packages.learning import auto_weight_trainer as t
    res = t.train(regime="NEUTRAL")
    assert isinstance(res, dict)
    assert res["reason"] == "below_min_total"


def test_trainer_emits_proposal(tmp_path, monkeypatch) -> None:
    ps, _, _ = _fresh_env(tmp_path, monkeypatch)
    # Proposal icin en az iki karsilastirilabilir modul gerekir.
    _seed_diverse_trades(ps)
    from packages.learning import auto_weight_trainer as t
    res = t.train(regime="NEUTRAL")
    assert hasattr(res, "deltas")
    assert res.from_version == "1.0.0"
    assert res.to_version == "1.1.0"
    # Sadece verified hesaba katıldı:
    assert res.dataset_size == 12
    # YAML proposal bir 'regimes.NEUTRAL' tablosu içermeli + normalize ≈1
    weights = res.proposed_yaml["regimes"]["NEUTRAL"]
    assert abs(sum(weights.values()) - 1.0) < 1e-3


def test_unverified_records_are_excluded(tmp_path, monkeypatch) -> None:
    ps, _, _ = _fresh_env(tmp_path, monkeypatch)
    _seed_diverse_trades(ps)
    _seed_trades(ps, n_verified=0, n_unverified=5, id_prefix="u")
    from packages.learning import auto_weight_trainer as t
    res = t.train(regime="NEUTRAL")
    assert res.dataset_size == 12
    assert res.rejected_records == 5


def test_trainer_skips_single_module_no_diversity(tmp_path, monkeypatch) -> None:
    ps, _, _ = _fresh_env(tmp_path, monkeypatch)
    _seed_trades(ps, n_verified=10)
    from packages.learning import auto_weight_trainer as t
    res = t.train(regime="NEUTRAL")
    assert isinstance(res, dict)
    assert res["status"] == "INSUFFICIENT"
    assert res["reason"] == "no_module_diversity"


def test_endpoints_propose_approve_flow(tmp_path, monkeypatch) -> None:
    ps, _rs, ld = _fresh_env(tmp_path, monkeypatch)
    _seed_diverse_trades(ps)

    # Yeni modül + manifest path environment kullandığımız için apps.api
    # modüllerini de yeniden yükle ki taze loader / store cache'i kullansın.
    from apps.api import main as api_main
    importlib.reload(api_main)
    client = TestClient(api_main.app)

    # 1) Propose
    r = client.post("/api/v1/learning/rebalance/propose", json={"regime": "NEUTRAL"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PENDING"
    new_version = body["proposal"]["to_version"]

    # 2) GET shows pending
    r = client.get("/api/v1/learning/rebalance/proposal")
    assert r.status_code == 200
    cur = r.json()["current"]
    assert cur and cur["status"] == "PENDING"
    assert cur["to_version"] == new_version

    # 3) Approve
    r = client.post("/api/v1/learning/rebalance/approve", json={"approved_by": "tester"})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["status"] == "APPROVED"

    # Manifest dosyası yazıldı ve active version artık new_version olmalı.
    assert ld.active_weights_version() == new_version

    # 4) Tekrar approve → 404 (pending kalmadı)
    r = client.post("/api/v1/learning/rebalance/approve")
    assert r.status_code == 404


def test_endpoints_reject_clears_pending(tmp_path, monkeypatch) -> None:
    ps, _rs, ld = _fresh_env(tmp_path, monkeypatch)
    _seed_diverse_trades(ps)

    from apps.api import main as api_main
    importlib.reload(api_main)
    client = TestClient(api_main.app)

    r = client.post("/api/v1/learning/rebalance/propose", json={"regime": "NEUTRAL"})
    assert r.status_code == 200
    r = client.post("/api/v1/learning/rebalance/reject", json={"reason": "looks_noisy"})
    assert r.status_code == 200
    assert r.json()["status"] == "REJECTED"

    # Pending kalmadı:
    cur = client.get("/api/v1/learning/rebalance/proposal").json()["current"]
    assert cur is None

    # Active version baseline'da kalır:
    assert ld.active_weights_version() == "1.0.0"

    # 404 on subsequent approve
    r = client.post("/api/v1/learning/rebalance/approve")
    assert r.status_code == 404


def test_active_weights_falls_back_to_baseline_without_manifest(
    tmp_path, monkeypatch
) -> None:
    _, _, ld = _fresh_env(tmp_path, monkeypatch)
    # Manifest dosyası yok → baseline (v1.0.0)
    assert ld.active_weights_version() == "1.0.0"
    w = ld.load_active_weights()
    assert "regimes" in w


def test_consensus_uses_active_weights(tmp_path, monkeypatch) -> None:
    ps, _rs, ld = _fresh_env(tmp_path, monkeypatch)
    _seed_diverse_trades(ps)

    from apps.api import main as api_main
    importlib.reload(api_main)
    client = TestClient(api_main.app)
    r = client.post("/api/v1/learning/rebalance/propose", json={"regime": "NEUTRAL"})
    assert r.status_code == 200
    r = client.post("/api/v1/learning/rebalance/approve")
    assert r.status_code == 200
    new_version = r.json()["proposal"]["active_yaml"]
    # active_yaml relative path; dosya açılabilmeli
    p = ld.REPO_ROOT / new_version
    assert p.exists()
    data = json.loads(
        ld.weights_manifest_path().read_text(encoding="utf-8")
    )
    assert data["version"] == ld.active_weights_version()
