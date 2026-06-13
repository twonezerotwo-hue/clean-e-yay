"""UX1 — Agent Operating Cockpit ViewModel.

Mevcut decision / risk / paper state'inden türetilen **özet** görünüm. Yeni
trading feature / data provider / intelligence module YOK; RiskGate / DQS /
KillSwitch / halt davranışına DOKUNULMAZ — yalnızca okunur ve sadeleştirilir.

Frontend hesap yapmaz (DASHBOARD_RULES): agent_status, **tek** main_blocker
("veya" yok), data_mode, watch/trigger koşulları, candidate→final karar izi
hepsi burada deterministik üretilir.

PAPER_SAFE / NO_EXECUTION — bu modül emir/karar üretmez, yalnızca matrix_view
(packages.decision.engine) + snapshot + paper state'i özetler.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# Enum literal'leri openapi (CockpitBrief) ile birebir senkron tutulur.
AGENT_STATUSES = ("ACTIONABLE", "NO_ACTION", "WATCHING", "FROZEN", "BLOCKED")
MAIN_BLOCKER_CODES = ("DQS_BLOCKED", "HALT", "PROVIDER_DOWN", "RISK_GATE", "NONE")
DATA_MODES = (
    "LIVE_VERIFIED",
    "LIVE_DEGRADED",
    "PARTIAL_FALLBACK",
    "SIMULATION",
    "BLOCKED",
)

# Sharpe / win-rate gibi metriklerin istatistiksel anlam kazandığı eşik —
# altındaysa frontend bunları büyük göstermez (LearningPanel uyarısı).
_RESTRICTIVE_RISK = ("RISK_REDUCE", "NO_POSITION_INCREASE")

# blocked_by tag prefix → okunur kapı kategorisi (restrictive_gates için).
_GATE_LABELS: dict[str, str] = {
    "risk_gate": "RiskGate",
    "mistake_memory": "MistakeMemory",
    "derivatives_risk": "Derivatives",
    "volatility_risk": "Volatility",
    "catalyst_risk": "Catalyst",
    "options_risk": "Options",
    "correlation": "Correlation",
    "timeframe_policy": "TimeframePolicy",
    "1w_bias": "1wBias",
    "event_risk": "EventRisk",
}


def compute_main_blocker(
    *,
    dqs_status: str | None,
    risk_action: str | None,
    risk_reason: str | None,
    halt_active: bool,
    provider_down: bool,
) -> dict[str, str]:
    """Tek ana engel — asla "veya" kullanmaz.

    Öncelik: DQS BLOCKED (veri yoksa hiçbir şey değerlendirilemez) >
    HALT/kill-switch (owner reset gerekli sticky freeze) > RiskGate kısıtı.
    DQS BLOCKED nedeni sağlayıcı düşüşüyse PROVIDER_DOWN olarak işaretlenir.
    """
    if dqs_status == "BLOCKED":
        if provider_down:
            return {
                "code": "PROVIDER_DOWN",
                "label": "PROVIDER_DOWN",
                "detail": "Sağlayıcı verisi yok — DQS BLOCKED, karar üretilmiyor.",
            }
        return {
            "code": "DQS_BLOCKED",
            "label": "DQS BLOCKED",
            "detail": risk_reason or "Veri kalitesi karar için yetersiz.",
        }
    if halt_active or risk_action == "KILL_SWITCH":
        return {
            "code": "HALT",
            "label": "HALT",
            "detail": risk_reason or "Kill-switch / halt aktif — owner reset gerekli.",
        }
    if risk_action in _RESTRICTIVE_RISK:
        return {
            "code": "RISK_GATE",
            "label": f"RiskGate {risk_action}",
            "detail": risk_reason or "",
        }
    return {"code": "NONE", "label": "NONE", "detail": "Risk kapısı açık."}


def compute_data_mode(provenance: dict | None, dqs_status: str | None) -> str:
    """Provenance label + DQS → 5 sade data_mode etiketinden biri."""
    label = (provenance or {}).get("label")
    if label == "INSUFFICIENT_DATA" or dqs_status == "BLOCKED":
        return "BLOCKED"
    if label == "MOCK_MODE":
        return "SIMULATION"
    if label == "SIMULATION":
        return "PARTIAL_FALLBACK" if dqs_status == "DEGRADED" else "SIMULATION"
    # label == "LIVE" (provenance LIVE → DQS OK); savunmacı: DEGRADED → LIVE_DEGRADED
    return "LIVE_DEGRADED" if dqs_status == "DEGRADED" else "LIVE_VERIFIED"


def compute_status(main_blocker_code: str, can_act: bool) -> str:
    """5 agent durumundan biri — main_blocker ve aksiyon edilebilirlikten."""
    if main_blocker_code in ("DQS_BLOCKED", "PROVIDER_DOWN"):
        return "BLOCKED"
    if main_blocker_code == "HALT":
        return "FROZEN"
    if main_blocker_code == "RISK_GATE":
        return "WATCHING"
    return "ACTIONABLE" if can_act else "NO_ACTION"


_STANCE: dict[str, str] = {
    "ACTIONABLE": "RiskGate limitleri dahilinde yeni giriş açılabilir.",
    "WATCHING": "Yeni giriş yok — mevcut pozisyonları izle.",
    "FROZEN": "Donduruldu — owner reset gerekli, yalnızca mevcut riski yönet.",
    "BLOCKED": "Bloklu — veri yetersiz, yeni karar üretilmiyor.",
    "NO_ACTION": "Geçerli kurulum yok — sinyal bekle.",
}


def _expired_time_stops(open_positions: list[Any], now: datetime) -> int:
    n = 0
    for p in open_positions:
        vu = getattr(p, "valid_until", None)
        if not vu:
            continue
        try:
            if datetime.fromisoformat(vu) <= now:
                n += 1
        except (ValueError, TypeError):
            continue
    return n


def _top_candidates(cells: list[dict], limit: int = 6) -> list[dict]:
    """En güçlü kanaatli hücreler (|score-50| sıralı) — candidate→final açık."""
    ranked = sorted(cells, key=lambda c: -abs(float(c.get("score", 50)) - 50))
    out = []
    for c in ranked[:limit]:
        out.append(
            {
                "symbol": c.get("symbol"),
                "timeframe": c.get("timeframe"),
                "direction": c.get("direction"),
                "score": c.get("score"),
                "candidate_action": c.get("candidate_action"),
                "final_action": c.get("action"),
                "actionable": bool(c.get("actionable")),
                "status": c.get("status"),
            }
        )
    return out


def _restrictive_gates(cells: list[dict]) -> list[str]:
    """Hücreleri kısan kapı kategorileri (distinct, okunur)."""
    cats: list[str] = []
    seen: set[str] = set()
    for c in cells:
        for b in c.get("blocked_by") or []:
            for prefix, label in _GATE_LABELS.items():
                if b.startswith(prefix) and label not in seen:
                    seen.add(label)
                    cats.append(label)
                    break
    return cats


def _blocked_by_reasons(cells: list[dict]) -> list[str]:
    return sorted({b for c in cells for b in (c.get("blocked_by") or [])})


def _paper_actions(cells: list[dict]) -> list[dict]:
    return [
        {
            "symbol": c.get("symbol"),
            "timeframe": c.get("timeframe"),
            "paper_action": c.get("paper_action"),
        }
        for c in cells
        if c.get("paper_action") not in (None, "none")
    ]


def next_watch_conditions(
    view: dict,
    snap: Any,
    open_positions: list[Any],
    now: datetime | None = None,
) -> list[dict]:
    """Agent'ın bir sonraki izlediği tetik koşulları (deterministik).

    Yalnızca mevcut state'ten türetilir — gelecek tahmini yok. Her madde
    {key, label, detail}: kullanıcı "agent ne bekliyor?" sorusunu okuyabilsin.
    """
    now = now or datetime.now(UTC)
    out: list[dict] = []
    risk_gate = view.get("risk_gate") or {}
    risk_action = risk_gate.get("action")
    dqs_status = view.get("dqs_status")
    cells = view.get("cells") or []

    # 1) açık pozisyon limiti (NO_POSITION_INCREASE tetikleyicisi)
    open_n = len(open_positions)
    if open_n >= 6:
        out.append(
            {
                "key": "position_count",
                "label": "Açık pozisyon sayısı limitin altına insin",
                "detail": f"şu an {open_n} açık pozisyon",
            }
        )

    # 2) korelasyon cluster exposure (hücre blocked_by'dan)
    if any("correlation" in b for c in cells for b in (c.get("blocked_by") or [])):
        out.append(
            {
                "key": "cluster_exposure",
                "label": "Korelasyon cluster exposure cap altına insin",
                "detail": "aynı yönlü cluster kısıtı aktif",
            }
        )

    # 3) süresi dolmuş time-stop'lar çözülsün
    expired = _expired_time_stops(open_positions, now)
    if expired:
        out.append(
            {
                "key": "time_stop_resolved",
                "label": "Süresi dolmuş time-stop'lar kapansın",
                "detail": f"{expired} pozisyon TIME_STOP_EXPIRED (fiyatla kapanır)",
            }
        )

    # 4) eksik sağlayıcı geri gelsin
    for name, meta in (getattr(snap, "provider_status", None) or {}).items():
        status = (meta or {}).get("status")
        if status not in (None, "ok", "OK"):
            out.append(
                {
                    "key": "provider_restored",
                    "label": f"Eksik sağlayıcı geri gelsin: {name}",
                    "detail": f"status={status}",
                }
            )

    # 5) catalyst yarı-ömrü dolsun
    for c in view.get("catalysts") or []:
        vu = c.get("valid_until")
        out.append(
            {
                "key": "catalyst_halflife",
                "label": f"Catalyst etkisi sönsün: {c.get('event_type')}",
                "detail": f"valid_until {vu}" if vu else "yarı-ömür aktif",
            }
        )

    # 6) DQS tam doğrulansın
    if dqs_status and dqs_status != "OK":
        out.append(
            {
                "key": "dqs_verified",
                "label": "DQS tam doğrulansın",
                "detail": f"şu an {dqs_status}",
            }
        )

    # 7) risk gate açılsın
    if risk_action in _RESTRICTIVE_RISK or risk_action == "KILL_SWITCH":
        out.append(
            {
                "key": "risk_gate_clear",
                "label": "Risk kapısı açılsın",
                "detail": f"şu an {risk_action}",
            }
        )

    return out[:8]


def agent_brief_view(
    view: dict,
    snap: Any,
    paper_state: Any,
    provenance: dict,
    *,
    halt_active: bool,
) -> dict:
    """AgentBriefView — ilk ekranın tek ana kartı (özet beyin)."""
    now = datetime.now(UTC)
    cells = view.get("cells") or []
    risk_gate = view.get("risk_gate") or {}
    risk_action = risk_gate.get("action")
    risk_reason = risk_gate.get("reason")
    dqs_status = view.get("dqs_status")
    suspended = bool(view.get("suspended"))

    provider_down = any(
        (meta or {}).get("status") not in (None, "ok", "OK")
        for meta in (getattr(snap, "provider_status", None) or {}).values()
    )
    blocker = compute_main_blocker(
        dqs_status=dqs_status,
        risk_action=risk_action,
        risk_reason=risk_reason,
        halt_active=halt_active,
        provider_down=provider_down,
    )
    can_act = (not suspended) and any(c.get("actionable") for c in cells)
    status = compute_status(blocker["code"], can_act)
    data_mode = compute_data_mode(provenance, dqs_status)

    open_positions = list(getattr(paper_state, "open_positions", []) or [])
    open_n = len(open_positions)
    expired = _expired_time_stops(open_positions, now)
    paper_actions = _paper_actions(cells)
    candidates = _top_candidates(cells)
    watch = next_watch_conditions(view, snap, open_positions, now)
    top_blockers = _blocked_by_reasons(cells)[:6]

    actionable_n = sum(1 for c in cells if c.get("actionable"))
    if blocker["code"] == "NONE":
        summary = (
            f"Agent {status}. Engel yok; {actionable_n} hücre actionable, "
            f"{len(candidates)} aday izleniyor."
        )
    else:
        summary = (
            f"Agent {status}. Ana engel: {blocker['label']}"
            + (f" ({blocker['detail']})" if blocker["detail"] else "")
            + f". {len(candidates)} aday izleniyor, "
            + ("yeni giriş yok." if not can_act else "giriş mümkün.")
        )

    return {
        "status": status,
        "can_act": can_act,
        "main_blocker": blocker,
        "summary": summary,
        "data_mode": data_mode,
        "regime": view.get("regime"),
        "dqs": {
            "status": dqs_status,
            "score": getattr(snap.quality, "score", None),
        },
        "risk": {"action": risk_action, "reason": risk_reason},
        "open_paper_positions": open_n,
        "top_blockers": top_blockers,
        "top_candidates": candidates,
        "next_watch_conditions": watch,
        "recommended_stance": _STANCE.get(status, ""),
        "paper_state_summary": {
            "open_positions": open_n,
            "expired_time_stops": expired,
            "new_entries_disabled": suspended,
            "frozen": blocker["code"] == "HALT",
            "current_paper_actions": paper_actions,
        },
        "generated_at": now.isoformat(),
    }


def decision_trace_view(view: dict, snap: Any) -> dict:
    """DecisionTraceView — candidate→final karar izi + kanıt referansları."""
    cells = view.get("cells") or []
    risk_gate = view.get("risk_gate") or {}
    candidate_decisions = [
        {
            "symbol": c.get("symbol"),
            "timeframe": c.get("timeframe"),
            "candidate_action": c.get("candidate_action"),
            "score": c.get("score"),
            "direction": c.get("direction"),
        }
        for c in cells
    ]
    final_decisions = [
        {
            "symbol": c.get("symbol"),
            "timeframe": c.get("timeframe"),
            "action": c.get("action"),
            "actionable": bool(c.get("actionable")),
            "status": c.get("status"),
            "blocked_by": list(c.get("blocked_by") or []),
            "reason": c.get("reason"),
        }
        for c in cells
    ]
    blocked_by = _blocked_by_reasons(cells)
    evidence_refs = [
        f"snapshot:{getattr(snap, 'snapshot_id', '?')}",
        f"dqs:{view.get('dqs_status')}",
        f"risk_gate:{risk_gate.get('action')}",
        *[f"blocked_by:{b}" for b in blocked_by[:4]],
    ]
    return {
        "candidate_decisions": candidate_decisions,
        "final_decisions": final_decisions,
        "blocked_by": blocked_by,
        "risk_gate": risk_gate,
        "restrictive_gates": _restrictive_gates(cells),
        "paper_action": _paper_actions(cells),
        "evidence_refs": evidence_refs,
    }
