"""World-state narrative synthesis for the existing cockpit flow.

This module is deliberately downstream of the canonical snapshot, world-state,
causal shadow and risk gate.  It does not fetch news, calculate a signal, size
an order, or write any decision state.  The LLM may rewrite the bounded
evidence into Turkish prose; structured asset/scenario/forecast fields always
come from backend data and a deterministic fallback is used on every failure.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from packages.agent.llm import budget, cache
from packages.agent.llm import client as llm_client
from packages.agent.llm.guard import SYSTEM_RULES

_MARKERS = (
    ("TITLE:", "title"),
    ("SUMMARY:", "summary"),
    ("WHY_IT_MATTERS:", "why_it_matters"),
    ("WHAT_TO_WATCH:", "what_to_watch"),
    ("INVALIDATORS:", "invalidators"),
)
_MAX_HEADLINES = 5
_MAX_EVENTS = 5
_MAX_ASSETS = 12
_MAX_FORECASTS = 16

# Dünya olay-tipi kodları → kullanıcıya dönük Türkçe etiket. Ham kod (ör.
# GEOPOLITICAL_ESCALATION / MILITARY_ESCALATION) panelde GÖSTERİLMEZ; bilinmeyen
# kod için insan-okur bir yedeğe düşülür (kod hiçbir zaman olduğu gibi basılmaz).
_EVENT_TYPE_LABELS: dict[str, str] = {
    "NUCLEAR_ESCALATION": "Nükleer tırmanma",
    "CEASEFIRE": "Ateşkes",
    "PEACE_TALKS": "Barış görüşmeleri",
    "SANCTIONS": "Yaptırım",
    "SANCTIONS_RELIEF": "Yaptırım hafiflemesi",
    "CHOKEPOINT_THREAT": "Boğaz tehdidi",
    "CHOKEPOINT_DISRUPTION": "Boğaz kesintisi",
    "SHIPPING_ATTACK": "Gemi saldırısı",
    "PORT_DISRUPTION": "Liman kesintisi",
    "PIPELINE_DISRUPTION": "Boru hattı kesintisi",
    "AIRSTRIKE": "Hava saldırısı",
    "MISSILE_ATTACK": "Füze saldırısı",
    "ENERGY_INFRASTRUCTURE_ATTACK": "Enerji altyapısı saldırısı",
    "DRONE_ATTACK": "İHA saldırısı",
    "GROUND_OFFENSIVE": "Kara harekâtı",
    "TRADE_RESTRICTION": "Ticaret kısıtlaması",
    "MILITARY_DEESCALATION": "Askeri gerilim azalması",
    "MILITARY_ESCALATION": "Askeri tırmanma",
    "GEOPOLITICAL_ESCALATION": "Jeopolitik tırmanma",
    "rumor_unverified": "Söylenti (doğrulanmamış)",
    "WORLD_STATE": "Dünya durumu",
    "UNKNOWN": "Bilinmeyen olay",
}


def _event_type_label(code: Any) -> str:
    """Olay-tipi kodunu kullanıcıya dönük Türkçe etikete çevir; bilinmeyeni
    olduğu gibi basma, boşluklu başlık biçimine indir."""
    key = str(code or "").strip()
    if key in _EVENT_TYPE_LABELS:
        return _EVENT_TYPE_LABELS[key]
    return key.replace("_", " ").strip().title() or "Bilinmeyen olay"


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if hasattr(value, "model_dump"):
        try:
            return _jsonable(value.model_dump(mode="json"))
        except (TypeError, ValueError):
            pass
    if hasattr(value, "to_dict"):
        try:
            return _jsonable(value.to_dict())
        except (TypeError, ValueError):
            pass
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _row(value: Any) -> dict[str, Any]:
    normalized = _jsonable(value)
    return dict(normalized) if isinstance(normalized, Mapping) else {}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _list_text(value: Any, limit: int = 6) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    return [str(item) for item in (value or ()) if item][:limit]


def _headline_rows(headlines: Iterable[Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in headlines or ():
        row = _row(item)
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        rows.append({
            "title": title[:240],
            "source": str(row.get("source") or "unknown")[:80],
            "verified": bool(row.get("verified", False)),
            "event_type": str(row.get("event_type") or "UNKNOWN"),
        })
    return rows[:_MAX_HEADLINES]


def _world_rows(world_state: Any) -> dict[str, Any]:
    world = _row(world_state)
    graph = _row(world.get("graph_context"))
    physical = _row(world.get("physical_commodity"))
    scenario = _row(world.get("scenario_report"))
    discovery = _row(world.get("asset_discovery"))
    events = [_row(item) for item in (world.get("geopolitical_events") or ())]
    events = [
        {
            "event_id": str(item.get("event_id") or ""),
            "event_type": str(item.get("event_type") or "UNKNOWN"),
            "region": item.get("region"),
            "status": item.get("status"),
            "severity": item.get("severity"),
            "source_confidence": item.get("source_confidence"),
            "confirmed_action": bool(item.get("confirmed_action", False)),
            "evidence": _list_text(item.get("evidence"), 4),
        }
        for item in events
    ][: _MAX_EVENTS]
    return {
        "data_quality": str(world.get("data_quality") or "UNAVAILABLE"),
        "confidence": world.get("confidence"),
        "missing_inputs": _list_text(world.get("missing_inputs"), 8),
        "events": events,
        "graph": {
            "version": graph.get("graph_version"),
            "entities": _list_text(graph.get("entity_ids"), 12),
            "affected_assets": _list_text(graph.get("affected_assets"), _MAX_ASSETS),
            "factor_channels": _list_text(graph.get("factor_channels"), 10),
            "warnings": _list_text(graph.get("warnings"), 6),
        },
        "physical": {
            "status": physical.get("status"),
            "warnings": _list_text(physical.get("warnings"), 6),
            "assessments": physical.get("assessments") or {},
        },
        "scenario": {
            "status": scenario.get("status"),
            "events": scenario.get("events") or [],
            "warnings": _list_text(scenario.get("warnings"), 6),
        },
        "discovery": {
            "status": discovery.get("status"),
            "candidate_count": discovery.get("candidate_count", 0),
            "candidates": (discovery.get("candidates") or [])[:_MAX_ASSETS],
            "warnings": _list_text(discovery.get("warnings"), 6),
        },
    }


def _forecast_rows(causal_shadow: Any) -> list[dict[str, Any]]:
    shadow = _row(causal_shadow)
    rows: list[dict[str, Any]] = []
    for item in shadow.get("forecasts") or ():
        row = _row(item)
        if not row.get("symbol") or row.get("horizon") not in {"1d", "1w"}:
            continue
        rows.append({
            "symbol": str(row["symbol"]),
            "horizon": str(row["horizon"]),
            "available": bool(row.get("available", False)),
            "directional_bias": str(row.get("directional_bias") or "UNKNOWN"),
            "confidence": row.get("confidence"),
            "current_price": row.get("current_price"),
            "point_estimate": row.get("point_estimate"),
            "p10": row.get("p10"),
            "p50": row.get("p50"),
            "p90": row.get("p90"),
            "missing_inputs": _list_text(row.get("missing_inputs"), 5),
        })
    return rows[:_MAX_FORECASTS]


def _evidence(
    *,
    headlines: Iterable[Any] | None,
    world_state: Any,
    causal_shadow: Any,
    portfolio_risk: Any,
    risk_gate: Mapping[str, Any] | None,
    dqs: Mapping[str, Any] | None,
) -> dict[str, Any]:
    world = _world_rows(world_state)
    graph_assets = set(world["graph"]["affected_assets"])
    scenario_assets: set[str] = set()
    for event in world["scenario"]["events"]:
        for scenario in (_row(event).get("scenarios") or ()):
            scenario_assets.update(str(symbol).upper() for symbol in (_row(scenario).get("affected_assets") or {}))
    assets = sorted(graph_assets | scenario_assets)[:_MAX_ASSETS]
    forecast_rows = [
        row for row in _forecast_rows(causal_shadow)
        if str(row["symbol"]).upper() in set(assets)
    ]
    portfolio = _row(portfolio_risk)
    gate = _row(risk_gate)
    quality = _row(dqs)
    payload = {
        "headlines": _headline_rows(headlines),
        "world": world,
        "forecast_bands": forecast_rows,
        "portfolio": {
            "status": portfolio.get("status"),
            "gross_exposure_pct": portfolio.get("gross_exposure_pct"),
            "net_exposure_pct": portfolio.get("net_exposure_pct"),
            "concentration_hhi": portfolio.get("concentration_hhi"),
            "thesis_conflicts": (portfolio.get("thesis_conflicts") or [])[:4],
        },
        "risk_gate": {"action": gate.get("action"), "reason": gate.get("reason")},
        "dqs": {"status": quality.get("status"), "score": quality.get("score")},
        "affected_assets": assets,
    }
    return payload


def _stable_digest(payload: Mapping[str, Any]) -> str:
    # Generated timestamps are intentionally absent from the payload.  A new
    # LLM call is caused by changed evidence, not by a dashboard poll.
    raw = json.dumps(_jsonable(payload), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _event_title(payload: Mapping[str, Any]) -> str:
    events = payload.get("world", {}).get("events") or []
    if events:
        first = _row(events[0])
        return _event_type_label(first.get("event_type"))
    headlines = payload.get("headlines") or []
    return "Yeni haber akışı" if headlines else "Yeni doğrulanmış dünya olayı yok"


def _missing_data(payload: Mapping[str, Any]) -> list[str]:
    world = _row(payload.get("world"))
    missing = list(world.get("missing_inputs") or [])
    graph = _row(world.get("graph"))
    missing.extend(str(item) for item in graph.get("warnings") or ())
    physical = _row(world.get("physical"))
    for assessment in (physical.get("assessments") or {}).values():
        missing.extend(str(item) for item in (_row(assessment).get("missing_inputs") or ()))
    for row in payload.get("forecast_bands") or ():
        if not row.get("available"):
            missing.extend(str(item) for item in row.get("missing_inputs") or ())
    dqs = _row(payload.get("dqs"))
    if dqs.get("status") in {"BLOCKED", "DEGRADED"}:
        missing.append(f"dqs:{dqs['status']}")
    return list(dict.fromkeys(item for item in missing if item))[:12]


def _evidence_used(payload: Mapping[str, Any]) -> list[str]:
    used: list[str] = []
    for headline in payload.get("headlines") or ():
        used.append(f"headline:{str(_row(headline).get('title') or '')[:80]}")
    for event in _row(payload.get("world")).get("events") or ():
        row = _row(event)
        used.append(f"event:{row.get('event_id') or _event_type_label(row.get('event_type'))}")
    graph = _row(_row(payload.get("world")).get("graph"))
    if graph.get("version"):
        used.append(f"world_graph:{graph['version']}")
    scenario = _row(_row(payload.get("world")).get("scenario"))
    if scenario.get("status"):
        used.append(f"scenario:{scenario['status']}")
    for row in payload.get("forecast_bands") or ():
        if row.get("available"):
            used.append(f"forecast:{row['symbol']}/{row['horizon']}")
    return list(dict.fromkeys(used))[:16]


def _actionability(payload: Mapping[str, Any]) -> str:
    gate = _row(payload.get("risk_gate"))
    dqs = _row(payload.get("dqs"))
    if dqs.get("status") == "BLOCKED":
        return "NO_ACTION_DATA_BLOCKED"
    if gate.get("action") and gate.get("action") != "HOLD":
        return f"NO_ACTION_RISK_GATE_{gate['action']}"
    if payload.get("affected_assets"):
        return "OBSERVE_ONLY"
    return "NO_ACTION_NO_VERIFIED_IMPACT"


def _fallback(payload: Mapping[str, Any], *, reason: str) -> dict[str, Any]:
    world = _row(payload.get("world"))
    events = world.get("events") or []
    headlines = payload.get("headlines") or []
    assets = list(payload.get("affected_assets") or [])
    graph = _row(world.get("graph"))
    channels = list(graph.get("factor_channels") or [])
    if events:
        first = _row(events[0])
        summary = (
            f"{_event_type_label(first.get('event_type'))} için doğrulanmış kanıt bulundu. "
            f"Kaynak güveni {first.get('source_confidence') if first.get('source_confidence') is not None else 'belirsiz'}; "
            f"etkilenen adaylar: {', '.join(assets) if assets else 'henüz eşleşmedi'}."
        )
    elif headlines:
        summary = f"Yeni haber akışında {len(headlines)} başlık var; yapılandırılmış jeopolitik eşleşme henüz kesinleşmedi."
    else:
        summary = "Yeni doğrulanmış dünya olayı veya haber başlığı bulunamadı."
    why = (
        f"İzlenen kanallar: {', '.join(channels)}."
        if channels else "Etki kanalı için yeterli yapılandırılmış bağlantı yok."
    )
    watch = _missing_data(payload) or ["Yeni bağımsız kaynak doğrulaması", "emtia fiyat/volatilite verisi"]
    invalidators: list[str] = []
    for event in world.get("scenario", {}).get("events") or []:
        for scenario in _row(event).get("scenarios") or ():
            invalidators.extend(_row(scenario).get("invalidators") or ())
    return {
        "status": "OK" if events or headlines else "NO_EVENT",
        "trigger": "WORLD_EVENT" if events else "NEWS_SCAN" if headlines else "NO_EVENT",
        "source": "fallback",
        "model": None,
        "title": _event_title(payload),
        "summary": summary,
        "why_it_matters": why,
        "what_to_watch": list(dict.fromkeys(str(item) for item in watch))[:8],
        "invalidators": list(dict.fromkeys(str(item) for item in invalidators))[:8],
        "affected_assets": assets,
        "scenario_report": world.get("scenario"),
        "forecast_bands": payload.get("forecast_bands") or [],
        "actionability": _actionability(payload),
        "execution": "NO_EXECUTION",
        "evidence_used": _evidence_used(payload),
        "missing_data": _missing_data(payload),
        "warnings": [reason] if reason else [],
        "llm": {"mode": llm_client.get_mode(), "source": "fallback", "cached": False, "tokens_used": 0},
    }


def _parse(text: str) -> dict[str, Any] | None:
    out: dict[str, Any] = {}
    current: str | None = None
    for line in text.splitlines():
        value = line.strip()
        matched = False
        for marker, key in _MARKERS:
            if value.upper().startswith(marker):
                current = key
                out[key] = value[len(marker):].strip()
                matched = True
                break
        if not matched and current and value:
            out[current] = f"{out.get(current, '')}\n{value}".strip()
    if not str(out.get("summary") or "").strip():
        return None
    for key in ("what_to_watch", "invalidators"):
        out[key] = [line.strip().lstrip("-•").strip() for line in str(out.get(key) or "").splitlines() if line.strip()]
    return out


def _prompt(payload: Mapping[str, Any]) -> tuple[str, str]:
    system = SYSTEM_RULES + (
        " Ek kural: Bu dünya raporu sayısal işlem hedefi veya emir üretmez. "
        "Yalnızca verilen kanıtı Türkçe özetle; verilen JSON'da bulunmayan bir "
        "olay, ülke, fiyat, hedef veya kesinlik uydurma."
    )
    user = (
        "Aşağıdaki yapılandırılmış backend kanıtını yönetici özeti olarak açıkla. "
        "Yalnızca şu biçimi kullan; başka satır yazma:\n"
        "TITLE: <kısa başlık>\nSUMMARY: <2-3 cümle>\n"
        "WHY_IT_MATTERS: <etki zinciri; kesinlik iddiası yok>\n"
        "WHAT_TO_WATCH:\n- <izlenecek veri veya teyit>\n"
        "INVALIDATORS:\n- <senaryoyu geçersiz kılacak kanıt; yoksa yok>\n\n"
        f"BACKEND_EVIDENCE:\n{json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)}"
    )
    return system, user


def build_world_brief(
    *,
    headlines: Iterable[Any] | None = None,
    world_state: Any = None,
    causal_shadow: Any = None,
    portfolio_risk: Any = None,
    risk_gate: Mapping[str, Any] | None = None,
    dqs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one cached narrative view over verified world evidence.

    This function is safe to call from polling endpoints: unchanged evidence
    hits the existing file cache and does not spend tokens or call a provider.
    """
    payload = _evidence(
        headlines=headlines,
        world_state=world_state,
        causal_shadow=causal_shadow,
        portfolio_risk=portfolio_risk,
        risk_gate=risk_gate,
        dqs=dqs,
    )
    digest = _stable_digest(payload)
    cache_key = f"world-brief|{digest}"
    cached = cache.get(cache_key)
    if cached is not None:
        cached = dict(cached)
        meta = dict(cached.get("llm") or {})
        meta["cached"] = True
        cached["llm"] = meta
        return cached

    fallback = _fallback(payload, reason="llm_off")
    if not payload["headlines"] and not _row(payload["world"]).get("events"):
        cache.put(cache_key, fallback)
        return fallback

    enabled = os.environ.get("WORLD_BRIEF_LLM_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
    mode = llm_client.get_mode()
    client = llm_client.get_client() if enabled else None
    if client is None:
        fallback["llm"]["fallback_reason"] = "llm_disabled" if not enabled else ("llm_off" if mode == "off" else "no_api_key")
        cache.put(cache_key, fallback)
        return fallback

    system, user = _prompt(payload)
    max_tokens = min(budget.max_tokens_per_request(), 500)
    estimated = (len(system) + len(user)) // 4 + max_tokens
    client = budget.gate(client, estimated)  # dolu bütçede yalnız yerel sağlayıcı kalır
    if client is None:
        fallback["llm"]["fallback_reason"] = "budget_exceeded"
        cache.put(cache_key, fallback)
        return fallback
    try:
        completion = client.complete(system, user, max_tokens)
    except Exception:
        completion = None
    if completion is None:
        fallback["llm"]["fallback_reason"] = "llm_error"
        cache.put(cache_key, fallback)
        return fallback
    used = completion.input_tokens + completion.output_tokens
    budget.record(used, completion.source)
    parsed = _parse(completion.text)
    if parsed is None:
        fallback["llm"]["fallback_reason"] = "invalid_format"
        fallback["llm"]["tokens_used"] = used
        cache.put(cache_key, fallback)
        return fallback
    result = dict(fallback)
    for key in ("title", "summary", "why_it_matters"):
        if parsed.get(key):
            result[key] = str(parsed[key])[:1200]
    for key in ("what_to_watch", "invalidators"):
        if parsed.get(key):
            result[key] = [str(item)[:240] for item in parsed[key]][:8]
    result["source"] = "llm"
    result["model"] = completion.model
    result["llm"] = {
        "mode": mode,
        "source": "llm",
        "model": completion.model,
        "cached": False,
        "tokens_used": used,
        "fallback_reason": None,
    }
    # Structured evidence is always backend-owned; the model cannot replace it.
    result["affected_assets"] = payload["affected_assets"]
    result["scenario_report"] = _row(payload["world"]).get("scenario")
    result["forecast_bands"] = payload["forecast_bands"]
    result["evidence_used"] = _evidence_used(payload)
    result["missing_data"] = _missing_data(payload)
    result["actionability"] = _actionability(payload)
    result["execution"] = "NO_EXECUTION"
    cache.put(cache_key, result)
    return result


__all__ = ["build_world_brief"]
