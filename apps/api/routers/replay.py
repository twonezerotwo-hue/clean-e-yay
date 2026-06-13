"""Replay endpoint'leri — R1 gerçek snapshot replay temeli.

Replay = **kaydedilmiş gerçek state'in incelenmesi**. Sahte backtest YOK,
uydurma geçmiş performans YOK. Endpoint'ler yalnızca disk snapshot store'dan
(`packages/data/snapshot_store.py`) okur — live provider'a GİTMEZ, yeni karar
HESAPLAMAZ.

PAPER_SAFE / NO_EXECUTION: replay hiçbir emir üretmez, paper pozisyon açmaz,
RiskGate'i bypass etmez, LLM karar motoruna bağlanmaz.

- GET /replay/status                       → store durumu (active/empty)
- GET /replay/backtest                      → R2 deterministik rolling backtest
- GET /replay/backtest/{run_id}             → aynı run (store değiştiyse 404)
- GET /replay/{snapshot_id}                → kayıtlı snapshot (yoksa 404)
- GET /replay/{snapshot_id}/decision-trace → kayıtlı matristen karar izi (yoksa 404)

R2 backtest: stored snapshot serisi üzerinde outcome ölçer (hit_rate / false
positive/negative / avg_return / max_drawdown / blocked_decision_accuracy,
per-timeframe & per-symbol). Yalnızca GERÇEK gelecek snapshot'larla ölçer →
look-ahead yok; eksikse dürüstçe insufficient_future_data der.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from packages.data import backtest, snapshot_store

router = APIRouter(tags=["replay"])

_NO_EXEC = "no_live_execution"
_TOP_CELLS = 8

_REASON_ACTIVE = (
    "Aktif: kayıtlı gerçek snapshot'lar üzerinden replay (stored state "
    "inspection). Yeni karar hesaplanmaz, live provider çağrılmaz. Rolling "
    "backtest motoru AKTİF DEĞİL — sahte geçmiş performans üretilmez."
)
_REASON_EMPTY = (
    "insufficient_snapshots — henüz kayıtlı snapshot yok; tick_worker çalışınca "
    "store dolar. backtest not active; sahte geçmiş üretilmez."
)


@router.get("/replay/status")
def get_replay_status() -> dict:
    """Replay store durumu (read-only; live data refetch yok)."""
    st = snapshot_store.status()
    n = int(st["snapshot_count"])
    active = n > 0
    return {
        "status": "active" if active else "empty",
        "available": active,
        "mode": "active_snapshot_replay" if active else "insufficient_snapshots",
        "snapshot_count": n,
        "latest_snapshot_id": st["latest_snapshot_id"],
        "latest_generated_at": st["latest_generated_at"],
        "schema_version": int(st["schema_version"]),
        "reason": _REASON_ACTIVE if active else _REASON_EMPTY,
        "execution": _NO_EXEC,
    }


# NOT: bu iki route, `/replay/{snapshot_id}` catch-all'undan ÖNCE tanımlanır;
# aksi halde "backtest" snapshot_id sanılır (FastAPI kayıt sırasıyla eşler).
@router.get("/replay/backtest")
def get_replay_backtest() -> dict:
    """R2 — deterministik rolling backtest (stored snapshot serisi).

    Live provider refetch YOK, decide_matrix yeniden çalışmaz, paper açılmaz,
    RiskGate bypass yok. Boş store → insufficient_snapshots; ölçülebilir gelecek
    yoksa insufficient_future_data (her ikisi de 200, dürüst body).
    """
    return backtest.run_backtest()


@router.get("/replay/backtest/{run_id}")
def get_replay_backtest_run(run_id: str) -> dict:
    """Belirli bir run_id için backtest sonucu.

    Backtest store üzerinde deterministiktir; sahte geçmiş run saklanmaz. İstenen
    run_id mevcut store'un deterministik id'siyle eşleşmiyorsa (store değişmiş)
    404 — bayat/uydurma sonuç döndürmek yerine dürüstçe reddeder.
    """
    result = backtest.run_backtest()
    if result.get("run_id") != run_id:
        raise HTTPException(
            status_code=404,
            detail={
                "run_id": run_id,
                "status": "not_found",
                "available": False,
                "current_run_id": result.get("run_id"),
                "reason": "Bu run_id mevcut snapshot store ile eşleşmiyor. "
                "Backtest store üzerinde deterministiktir; geçmiş run "
                "saklanmaz. Güncel sonuç için current_run_id kullanın.",
            },
        )
    return result


@router.get("/replay/{snapshot_id}")
def get_replay_snapshot(snapshot_id: str) -> dict:
    """Kayıtlı snapshot'ı döndürür; store'da yoksa 404 (live refetch yapmaz)."""
    doc = snapshot_store.get(snapshot_id)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail={
                "snapshot_id": snapshot_id,
                "status": "not_found",
                "available": False,
                "reason": "Bu snapshot_id store'da yok. Replay live veri "
                "refetch etmez — yalnızca kaydedilmiş state okunur.",
            },
        )
    return {
        "snapshot_id": doc.get("snapshot_id"),
        "status": "active",
        "available": True,
        "execution": _NO_EXEC,
        "snapshot": doc,
    }


@router.get("/replay/{snapshot_id}/decision-trace")
def get_replay_decision_trace(snapshot_id: str) -> dict:
    """Kayıtlı decision_matrix'ten karar izi — yalnızca stored state'i açıklar.

    Yeni karar hesaplamaz, live provider çağırmaz. Catalyst/options/volatilite/
    türev özetleri kayıtlı matristen gelir.
    """
    doc = snapshot_store.get(snapshot_id)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail={
                "snapshot_id": snapshot_id,
                "status": "not_found",
                "available": False,
                "reason": "Bu snapshot_id store'da yok; decision-trace için "
                "kayıtlı state gerekir.",
            },
        )

    dm = doc.get("decision_matrix") or {}
    cells = dm.get("cells") or []
    top = sorted(cells, key=lambda c: -abs(float(c.get("score", 50)) - 50))[:_TOP_CELLS]
    blocked = sorted({b for c in cells for b in (c.get("blocked_by") or [])})
    paper_actions = [
        {"symbol": c.get("symbol"), "timeframe": c.get("timeframe"),
         "paper_action": c.get("paper_action")}
        for c in cells
        if c.get("paper_action") not in (None, "none")
    ]
    provider_issues = {
        name: meta
        for name, meta in (doc.get("provider_status") or {}).items()
        if (meta or {}).get("status") not in (None, "ok", "OK")
    }

    return {
        "snapshot_id": doc.get("snapshot_id"),
        "generated_at": doc.get("generated_at"),
        "schema_version": int(doc.get("schema_version", snapshot_store.SCHEMA_VERSION)),
        "available": True,
        "execution": _NO_EXEC,
        "note": "replay = stored state inspection — yeni karar hesaplanmaz, "
        "live provider çağrılmaz.",
        "mode": doc.get("mode"),
        "dqs": doc.get("dqs"),
        "regime": dm.get("regime"),
        "suspended": bool(dm.get("suspended")),
        "risk_gate": dm.get("risk_gate") or doc.get("risk_state"),
        "top_candidates": [
            {
                "symbol": c.get("symbol"),
                "timeframe": c.get("timeframe"),
                "candidate_action": c.get("candidate_action"),
                "final_action": c.get("action"),
                "score": c.get("score"),
                "direction": c.get("direction"),
                "blocked_by": list(c.get("blocked_by") or []),
            }
            for c in top
        ],
        "final_decisions": [
            {
                "symbol": c.get("symbol"),
                "timeframe": c.get("timeframe"),
                "action": c.get("action"),
                "paper_action": c.get("paper_action"),
                "blocked_by": list(c.get("blocked_by") or []),
            }
            for c in cells
        ],
        "blocked_by_reasons": blocked,
        "paper_actions": paper_actions,
        "paper_state_summary": doc.get("paper_state_summary"),
        "provider_issues": provider_issues,
        "deep_data": {
            "options": dm.get("options") or [],
            "volatility": dm.get("volatility") or [],
            "derivatives": dm.get("derivatives") or [],
            "catalysts": dm.get("catalysts") or [],
            "event_risk": dm.get("event_risk") or {},
        },
    }
