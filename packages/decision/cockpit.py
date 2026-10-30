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
from types import SimpleNamespace
from typing import Any

from packages.decision import final_gate, tick_artifact
from packages.decision.engine import directional_strength_from_score
from packages.decision.final_gate import (  # noqa: F401 — eski içe aktarma yolu
    CONFIRMATION_GROUPS,
    technical_confirmation_ready,
    technical_data_ready,
)
from packages.paper import news_setup

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
    "technical_confirmation": "TechnicalConfirmation",
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
    "ACTIONABLE": "Teknik olarak giriş engeli yok; edge kanıtı ayrıca doğrulanmalıdır.",
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
    """En güçlü yön hücreleri — candidate→final ayrımı açık."""
    def _strength(cell: dict) -> float:
        value = cell.get("directional_strength")
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
        try:
            return float(directional_strength_from_score(float(cell.get("score", 50)), cell.get("direction")))
        except (TypeError, ValueError):
            return 50.0

    ranked = sorted(cells, key=lambda c: -_strength(c))
    out = []
    for c in ranked[:limit]:
        strength = _strength(c)
        out.append(
            {
                "symbol": c.get("symbol"),
                "timeframe": c.get("timeframe"),
                "direction": c.get("direction"),
                "score": c.get("score"),
                "consensus_score": c.get("consensus_score", c.get("score")),
                "score_semantics": c.get("score_semantics", "direction_axis_50_neutral"),
                "directional_strength": round(strength, 1),
                "confidence": c.get("confidence"),
                "confidence_source": c.get("confidence_source"),
                "decision_id": c.get("decision_id"),
                "candidate_action": c.get("candidate_action"),
                "final_action": c.get("action"),
                "actionable": bool(c.get("actionable")),
                "execution_ready": bool(c.get("execution_ready", c.get("actionable"))),
                "execution_state": c.get("execution_state"),
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


def _open_position_actions(open_positions: list[Any]) -> list[dict]:
    """Return only actions that are backed by an actually open paper position.

    ``_paper_actions`` is the decision-matrix projection and therefore contains
    *intended* actions.  Mixing that list into ``current_paper_actions`` made
    the cockpit claim that an order existed when the tick worker had held it at
    the final news-confluence gate.
    """
    return [
        {
            "symbol": getattr(position, "symbol", None),
            "timeframe": getattr(position, "timeframe", "1d"),
            "paper_action": f"open_{getattr(position, 'side', '')}",
            "position_id": getattr(position, "id", None),
        }
        for position in open_positions
        if getattr(position, "symbol", None)
    ]


def _auto_open_readiness(
    cells: list[dict],
    snap: Any,
    paper_state: Any,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Project the worker's final paper-open gate into the read model.

    The tick worker deliberately requires a live, same-symbol/timeframe/side
    ``ARMED`` news+technical setup.  The decision matrix is calculated before
    that gate, so exposing matrix ``READY`` as if it were an opened position is
    misleading.  This helper is read-only and calls the canonical matcher; it
    never creates a setup or mutates paper state.
    """
    candidates = [
        cell
        for cell in cells
        if cell.get("action") in {"open_long", "open_short"}
        and bool(cell.get("execution_ready", cell.get("actionable")))
    ]
    try:
        required = news_setup.require_confluence_for_auto_open()
    except Exception:
        # Observability must not take down the cockpit if a malformed optional
        # threshold is encountered.  The worker remains the decision authority.
        required = False

    setups = getattr(paper_state, "news_prepared_setups", None)
    quotes = {
        str(getattr(quote, "symbol", "")): quote
        for quote in (getattr(snap, "prices", None) or [])
    }
    ready: list[dict] = []
    blockers: list[dict] = []
    for cell in candidates:
        symbol = str(cell.get("symbol") or "")
        timeframe = str(cell.get("timeframe") or "")
        side = "long" if cell.get("action") == "open_long" else "short"
        if not technical_data_ready(snap, symbol, timeframe):
            blockers.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "side": side,
                "code": "technical_data",
                "reason": "Teknik veri taze ve doğrulanmış değil.",
            })
            continue
        technical_ok, _technical_reason = technical_confirmation_ready(snap, symbol, timeframe, side)
        if not technical_ok:
            blockers.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "side": side,
                "code": "technical_confirmation",
                "reason": "Aynı yönde yeterli teknik teyit yok.",
            })
            continue
        if not required:
            ready.append({"symbol": symbol, "timeframe": timeframe, "side": side})
            continue
        if setups is None:
            blockers.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "side": side,
                "code": "news_confluence",
                "reason": "Haber-teknik kurulum verisi henüz hazır değil.",
            })
            continue
        quote = quotes.get(symbol)
        match = news_setup.match_confluence(
            setups,
            symbol=symbol,
            timeframe=timeframe,
            side=side,
            price=getattr(quote, "price", None),
            data_verified=bool(getattr(quote, "verified", False)),
            decision_id=cell.get("decision_id"),
            now=now,
        )
        if match is not None:
            ready.append({"symbol": symbol, "timeframe": timeframe, "side": side})
            continue
        blockers.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "side": side,
                "code": "news_confluence",
                "reason": (
                    "Aynı varlık, zaman dilimi ve yönde canlı ARMED "
                    "haber-teknik kurulumu yok."
                ),
            }
        )

    return {
        "enabled": bool(required),
        "available": setups is not None,
        "candidate_count": len(candidates),
        "ready_count": len(ready),
        "blocked_count": len(blockers),
        "ready": ready,
        "blockers": blockers,
        "reason": (
            "Otomatik kâğıt açılışı için haber-teknik kurulumu bekleniyor."
            if blockers and not ready
            else None
        ),
    }


_FINAL_BLOCKER_REASONS = {
    "news_confluence": "Teknik aday var; aynı varlık, zaman dilimi ve yönde canlı ARMED haber-teknik kurulumu yok.",
    "news_conflict": "Ters yönlü canlı haber kurulumu otomatik açılışı engelledi.",
    "technical_data": "Teknik veri taze ve doğrulanmış değil; otomatik açılış bekletildi.",
    "technical_confirmation": "Teknik göstergeler aynı yönde yeterli teyit vermedi; otomatik açılış bekletildi.",
    "session_gate": "Seans ya da conflict gate otomatik açılışı engelledi.",
}


def _final_gate_context(view: dict, snap: Any, now: datetime) -> dict[str, Any]:
    """Tick yayını yokken son kapının ihtiyaç duyduğu bağlam (conflict gate ön
    hesabı olmadan; o kapı bu durumda fail-open kalır)."""
    from packages.decision import conflict_gate

    prices = {q.symbol: q.price for q in (getattr(snap, "prices", None) or []) if q.price is not None}
    verified = {q.symbol: bool(getattr(q, "verified", False)) for q in (getattr(snap, "prices", None) or [])}
    return {
        "prices": prices,
        "verified": verified,
        "regime": SimpleNamespace(label=str(view.get("regime") or "")),
        "gate_cfg": conflict_gate.load_config(),
    }


def finalize_matrix_view(
    view: dict,
    snap: Any,
    paper_state: Any,
    now: datetime | None = None,
) -> dict:
    """Apply the worker's final paper-open gate to a read-only matrix.

    ``matrix_view`` is intentionally pure and remains the technical/risk
    projection used by replay tests.  API, brief and LLM surfaces must use this
    projection before they call something an actionable paper entry.
    """
    now = now or datetime.now(UTC)
    cells = view.get("cells") or []
    from packages.paper.state_machine import derive_decision_state

    # Açık pozisyon (varlık, zaman dilimi) düzeyinde: 1h pozisyonu 4h hücresini "açık" göstermez.
    open_keys = {
        (str(getattr(p, "symbol", "")), str(getattr(p, "timeframe", "") or "1d"))
        for p in (getattr(paper_state, "open_positions", None) or [])
    }
    pending = view.get("pending_paper_actions") or _paper_actions(cells)
    # Haber-teknik kurulum görünümü (yalnız require modunda kapı; ekranda bilgi).
    readiness = _auto_open_readiness(cells, snap, paper_state, now)
    # Son kapı tek yerde (final_gate). Tick bu snapshot için sonucu yayınladıysa
    # ekran onu gösterir; yoksa aynı fonksiyon hücre verisiyle çalışır.
    published = tick_artifact.final_for(snap)
    fallback: dict[str, Any] | None = None
    for cell in cells:
        intent = cell.get("paper_action_intent", cell.get("paper_action"))
        cell["paper_action_intent"] = intent
        if intent not in final_gate.CANDIDATE_ACTIONS:
            cell["final_actionable"] = False
            cell["final_execution_ready"] = False
            state, state_reason = derive_decision_state(cell, open_keys=open_keys)
            cell["lifecycle_state"] = state
            cell["lifecycle_reason"] = state_reason
            continue

        symbol, timeframe = str(cell.get("symbol") or ""), str(cell.get("timeframe") or "")
        result = published.get((symbol, timeframe)) if published is not None else None
        if result is None:
            if fallback is None:
                fallback = _final_gate_context(view, snap, now)
            result = final_gate.evaluate(
                SimpleNamespace(
                    symbol=symbol,
                    timeframe=timeframe,
                    action=intent,
                    decision_id=cell.get("decision_id"),
                    risk=SimpleNamespace(action=(view.get("risk_gate") or {}).get("action", "HOLD")),
                ),
                snap=snap,
                setups=getattr(paper_state, "news_prepared_setups", None) or [],
                prices=fallback["prices"],
                verified_flags=fallback["verified"],
                now=now,
                regime=fallback["regime"],
                gate_cfg=fallback["gate_cfg"],
                conflict_by_symbol={},
                execution_ready=bool(cell.get("execution_ready", cell.get("actionable"))),
            )

        cell["final_execution_ready"] = result.route != "block"
        cell["final_actionable"] = result.route == "open"
        cell["paper_action"] = intent if result.route == "open" else "none"
        if result.route == "manual_ready":
            cell["reason"] = "Tüm kapılar geçti; seans/conflict gate açılışı owner onayına yönlendirdi" + (
                f" ({result.reason})." if result.reason else "."
            )
        elif result.route == "block":
            cell["execution_state"] = "BLOCKED"
            if result.blocker and result.blocker not in (cell.get("blocked_by") or []):
                cell.setdefault("blocked_by", []).append(result.blocker)
            if result.blocker in _FINAL_BLOCKER_REASONS:
                cell["reason"] = _FINAL_BLOCKER_REASONS[result.blocker]
        state, state_reason = derive_decision_state(
            cell,
            open_keys=open_keys,
            technical_confirmed=result.technical_confirmed,
            news_confirmed=result.news_matched,
        )
        cell["lifecycle_state"] = state
        cell["lifecycle_reason"] = state_reason

    view["auto_open"] = readiness
    view["pending_paper_actions"] = pending
    view["paper_actions"] = _paper_actions(cells)
    view["final_gate_applied"] = True
    view["final_gate_snapshot_id"] = getattr(snap, "snapshot_id", None)
    view["final_gate_paper_state_revision"] = getattr(paper_state, "revision", None)
    return view


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
    view = finalize_matrix_view(view, snap, paper_state, now)
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
    data_mode = compute_data_mode(provenance, dqs_status)

    open_positions = list(getattr(paper_state, "open_positions", []) or [])
    open_n = len(open_positions)
    expired = _expired_time_stops(open_positions, now)
    pending_paper_actions = view.get("pending_paper_actions") or []
    current_paper_actions = _open_position_actions(open_positions)
    auto_open = view.get("auto_open") or _auto_open_readiness(cells, snap, paper_state, now)
    matrix_can_act = any(c.get("final_execution_ready", False) for c in cells)
    # ``can_act`` must describe the same final gate as the tick worker, not
    # merely the pre-gate decision matrix.
    can_act = (not suspended) and matrix_can_act and not (
        auto_open["enabled"]
        and auto_open["available"]
        and auto_open["ready_count"] == 0
        and auto_open["candidate_count"] > 0
    )
    status = compute_status(blocker["code"], can_act)
    candidates = _top_candidates(cells)
    watch = next_watch_conditions(view, snap, open_positions, now)
    top_blockers = _blocked_by_reasons(cells)[:6]

    matrix_actionable_n = sum(
        1 for c in cells if c.get("execution_ready", c.get("actionable"))
    )
    actionable_n = (
        auto_open["ready_count"]
        if auto_open["enabled"] and auto_open["available"]
        else matrix_actionable_n
    )
    exploration_n = sum(1 for c in cells if c.get("execution_state") == "EXPLORATION")
    if auto_open["blocked_count"]:
        # The matrix blockers describe the pre-gate decision.  Add the final
        # worker gate so the user sees why a READY-looking signal did not open.
        top_blockers = ["news_confluence", *top_blockers]
        top_blockers = list(dict.fromkeys(top_blockers))[:6]
        watch.insert(
            0,
            {
                "key": "news_confluence",
                "label": "Aynı yönde canlı haber-teknik teyit oluşsun",
                "detail": (
                    f"{auto_open['blocked_count']} aday ARMED haber kurulumu olmadığı için bekliyor"
                ),
            },
        )
    if blocker["code"] == "NONE":
        if auto_open["blocked_count"] and actionable_n == 0:
            summary = (
                f"Agent {status}. {matrix_actionable_n} teknik sinyal var, ancak "
                "otomatik kâğıt açılışı haber-teknik kurulumu bekliyor; "
                f"{len(candidates)} aday izleniyor."
            )
        else:
            summary = (
                f"Agent {status}. Engel yok; {actionable_n} hücre hazır"
                + (f", {exploration_n} keşif" if exploration_n else "")
                + ", "
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
        "auto_open": auto_open,
        "next_watch_conditions": watch,
        "recommended_stance": _STANCE.get(status, ""),
        "paper_state_summary": {
            "open_positions": open_n,
            "expired_time_stops": expired,
            "new_entries_disabled": suspended,
            "frozen": blocker["code"] == "HALT",
            # current = ledger-backed positions; pending = decision-matrix
            # intents that still have to pass the worker's final gates.
            "current_paper_actions": current_paper_actions,
            "pending_paper_actions": pending_paper_actions,
            "auto_open": auto_open,
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
