"""O1 — system health ViewModel (pure read; network-free).

Worker heartbeat + snapshot store + halt store + paper audit'ten 7/24
operasyonel sağlık özeti üretir. STALE tespiti heartbeat yaşına göre (eşikler
config/env'den, güvenli default). Üretilen "warnings" owner uyarısıdır —
execution alert DEĞİL: trade açmaz, RiskGate/DQS/KillSwitch/halt bypass etmez.

PAPER_SAFE / NO_EXECUTION. Frontend hesap yapmaz — bu ViewModel'i gösterir.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime

from packages.data import snapshot_store
from packages.data.registry.loader import load_source_registry, load_thresholds
from packages.ops import heartbeat
from packages.paper import audit as paper_audit
from packages.risk import halt as halt_store

TICK_WORKER = "tick_worker"
LEARNING_WORKER = "learning_worker"

DEFAULT_TICK_STALE_SEC = 120       # ~4× 30sn tick interval
DEFAULT_LEARNING_STALE_SEC = 3600  # 1 saat

_METRIC_DEFAULTS = (
    ("cycle_count", 0),
    ("snapshots_written", 0),
    ("decisions_generated", 0),
    ("paper_actions", 0),
    ("learning_outcomes_seen", 0),
    ("proposals_generated", 0),
)


def _stale_threshold(env: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(env, default)))
    except (ValueError, TypeError):
        return default


def _age_seconds(ts: str | None, now: datetime) -> float | None:
    if not ts:
        return None
    try:
        return round((now - datetime.fromisoformat(ts)).total_seconds(), 1)
    except (ValueError, TypeError):
        return None


def _unknown_worker(name: str) -> dict:
    view = {
        "worker_name": name,
        "status": "UNKNOWN",
        "stale": True,
        "run_id": None,
        "started_at": None,
        "completed_at": None,
        "last_success_at": None,
        "last_error": None,
        "age_seconds": None,
        "duration_ms": None,
        # F2-1 — MTM salt-gözlem alanları (tick_worker yazar; gate girdisi değil).
        "unrealized_pnl_usd": None,
        "mtm_equity_usd": None,
    }
    for k, dv in _METRIC_DEFAULTS:
        view[k] = dv
    return view


def _worker_view(name: str, threshold_sec: int, now: datetime) -> dict:
    hb = heartbeat.load(name)
    if hb is None:
        return _unknown_worker(name)  # hiç çalışmadı
    last_contact = hb.get("completed_at") or hb.get("started_at")
    age = _age_seconds(last_contact, now)
    stored = str(hb.get("status", "UNKNOWN"))
    stale = age is None or age > threshold_sec
    if stored == "FAILED":
        status = "FAILED"          # hata stale olsa bile görünür kalsın
    elif stale:
        status = "STALE"           # uzun süredir cycle yok / takıldı
    else:
        status = stored
    view = dict(hb)
    view["worker_name"] = name
    view["status"] = status
    view["stale"] = stale
    view["age_seconds"] = age
    for k, dv in _METRIC_DEFAULTS:
        view.setdefault(k, dv)
    view.setdefault("duration_ms", None)
    view.setdefault("last_error", None)
    view.setdefault("last_success_at", None)
    # F2-1 — legacy heartbeat dosyaları MTM alanlarını taşımaz → None'a düşer.
    view.setdefault("unrealized_pnl_usd", None)
    view.setdefault("mtm_equity_usd", None)
    return view


def _provider_summary(
    provider_status: dict, *, decision_fallback_used: bool | None = None
) -> dict:
    # "disabled" = config eksik (opsiyonel entegrasyon kapalı) — degraded değil.
    counts = {"ok": 0, "degraded": 0, "down": 0, "unknown": 0, "disabled": 0}
    degraded_sources: list[str] = []
    observational_degraded_sources: list[str] = []
    # These providers are useful for discovery/coverage, but are not the
    # decision-critical quote path when the canonical snapshot says no
    # fallback was consumed.  Keep their stale state visible without making a
    # healthy decision snapshot look globally degraded.
    secondary_observation = {
        "coingecko", "ohlcv_coingecko", "alphavantage", "twelvedata", "finnhub",
    }
    # BLS is additive evidence only while causal decision application is off;
    # its public endpoint status must not inherit a quote fallback's severity.
    always_observation = {"macro_bls"}
    for name, info in (provider_status or {}).items():
        raw = info.get("status") if isinstance(info, dict) else info
        st = str(raw or "unknown").lower()
        # Older snapshots predate `last_fallback_at` and can say OK even when
        # they recorded thousands of stale-cache fallbacks.  Keep health honest
        # until a fresh worker snapshot replaces them.
        if isinstance(info, dict) and st == "ok":
            fallback = int(info.get("fallbacks") or 0)
            age = info.get("last_cache_age_seconds")
            if info.get("last_error_type") in {"stale_cache", "stale_cache_expired"}:
                st = "degraded"
            elif fallback > 0 and isinstance(age, (int, float)) and float(age) > 2400:
                st = "degraded"
        if st in {"degraded", "down"}:
            if str(name).lower() in always_observation or (
                decision_fallback_used is False
                and str(name).lower() in secondary_observation
            ):
                observational_degraded_sources.append(str(name))
                # Do not count an optional observation source as a failed
                # decision provider; its state is returned separately below.
                counts["ok"] += 1
                continue
            degraded_sources.append(str(name))
        counts[st] = counts.get(st, 0) + 1
    return {
        "providers": counts,
        "degraded_count": counts.get("degraded", 0) + counts.get("down", 0),
        "total": sum(counts.values()),
        "degraded_sources": sorted(degraded_sources),
        "observational_degraded_sources": sorted(observational_degraded_sources),
        "observation_degraded_count": len(observational_degraded_sources),
    }


def _registry_runtime_summary(provider_status: dict | None) -> dict:
    """Compare the policy registry with the providers present in the snapshot.

    This is deliberately a read-only diagnostic.  A provider missing from a
    cold-start snapshot is reported as ``unknown``; it is never silently
    treated as healthy and it never changes a decision or opens a position.
    """
    # Provider registries pre-create optional adapters (for example Finnhub,
    # TwelveData and the test mock).  A pre-created ``unknown`` row with zero
    # calls is not runtime usage and must not lower the registry score.  Rows
    # without status metadata are kept for deterministic unit/replay inputs.
    def _active(info: object) -> bool:
        if not isinstance(info, dict) or not info:
            return True
        if str(info.get("status", "")).lower() != "unknown":
            return True
        try:
            return int(info.get("calls") or 0) > 0
        except (TypeError, ValueError):
            return False

    observed = {str(name).lower() for name in (provider_status or {})}
    runtime = {
        str(name).lower()
        for name, info in (provider_status or {}).items()
        if _active(info)
    }
    # Registry names describe source adapters, while the snapshot exposes
    # orchestrator names (for example ``ohlcv_coingecko`` and
    # ``macro_bls``).  Comparing raw strings made a healthy runtime look
    # incomplete.  Keep the raw inventory for auditability, but normalize the
    # comparison to the actual runtime surface.
    fetcher_aliases: dict[str, set[str]] = {
        "coingecko": {"coingecko", "ohlcv_coingecko"},
        "yfinance": {"yfinance", "ohlcv_yfinance", "rotation"},
        "kraken": {"kraken", "ohlcv_kraken"},
        "binance_spot": {"binance_spot", "ohlcv_binance"},
        "binance": {"binance", "derivatives_binance"},
        "deribit": {"deribit", "options_deribit"},
        "fred": {"fred", "macro_fred"},
        "bls_public_api": {"bls_public_api", "macro_bls"},
        "eia_api": {"eia_api", "macro_eia"},
        "rss": {"rss", "news", "geo_news"},
        "investing_web_calendar": {"investing_web_calendar", "calendar", "calendar_web"},
        "investing_web_calendar_plus_news": {
            "investing_web_calendar_plus_news", "calendar", "calendar_web", "news", "geo_news",
        },
    }
    policy_only = {"packages.macro.evidence", "packages.macro.correlation"}
    try:
        registry_rows = list(load_source_registry().get("sources") or [])
    except Exception:
        registry_rows = []
    expected = {str(row.get("fetcher") or "").lower() for row in registry_rows if isinstance(row, dict)}
    expected.discard("")
    missing = sorted(
        fetcher for fetcher in expected
        if fetcher not in policy_only and not (fetcher_aliases.get(fetcher, {fetcher}) & observed)
    )
    mapped_runtime = set().union(*(fetcher_aliases.get(fetcher, {fetcher}) for fetcher in expected))
    return {
        "registry_sources": len(registry_rows),
        "registry_fetchers": sorted(expected),
        "runtime_providers": sorted(runtime),
        "unknown_fetchers": missing,
        "policy_only_fetchers": sorted(expected & policy_only),
        "unregistered_runtime_providers": sorted(runtime - mapped_runtime),
        "status": "OK" if not missing else "INCOMPLETE",
    }


def _effective_flags() -> dict:
    """Return the *effective* flags, including code-level safety overrides.

    Historical shadow settings are reported separately from the effective
    runtime route.  The runtime writer is intentionally disabled; old files
    remain readable for audit but cannot enter the decision or learning path.
    """
    thresholds = load_thresholds() or {}
    shadow_cfg = thresholds.get("shadow") or {}
    causal_cfg = thresholds.get("causal_world") or {}
    try:
        from packages.decision import shadow as decision_shadow

        shadow = decision_shadow.load_config()
        shadow_effective = bool(decision_shadow.affects_paper(shadow))
        shadow_code = {
            "enabled": bool(shadow.enabled),
            "affect_decision": bool(shadow.affect_decision),
            "manual_ready_only": bool(shadow.manual_ready_only),
        }
    except Exception:
        shadow_effective = False
        shadow_code = {"enabled": False, "affect_decision": False, "manual_ready_only": True}
    try:
        from packages.discovery import scan_enabled

        discovery_scan_enabled = bool(scan_enabled())
    except Exception:
        discovery_scan_enabled = False
    try:
        from packages.paper import news_setup

        confluence_gate = bool(news_setup.require_confluence_for_auto_open())
    except Exception:
        confluence_gate = True
    return {
        "paper_safe": True,
        "no_execution": True,
        "news_confluence_gate": confluence_gate,
        "shadow_requested": {
            "enabled": bool(shadow_cfg.get("enabled", False)),
            "affect_decision": bool(shadow_cfg.get("affect_decision", False)),
            "manual_ready_only": bool(shadow_cfg.get("manual_ready_only", True)),
        },
        "shadow_effective": {
            **shadow_code,
            "affects_paper": shadow_effective,
            "runtime_writes": False,
            "historical_read_only": True,
            "routed_to_paper": False,
            "manual_ready_route": False,
            "paper_mutation": False,
        },
        "causal_world_decision_apply": bool(causal_cfg.get("decision_apply", False)),
        "discovery_scan_enabled": discovery_scan_enabled,
    }


def build_system_health() -> dict:
    now = datetime.now(UTC)
    tick = _worker_view(
        TICK_WORKER, _stale_threshold("TICK_STALE_SEC", DEFAULT_TICK_STALE_SEC), now
    )
    learning = _worker_view(
        LEARNING_WORKER,
        _stale_threshold("LEARNING_STALE_SEC", DEFAULT_LEARNING_STALE_SEC),
        now,
    )

    latest = snapshot_store.latest()
    store_status = snapshot_store.status()
    snap_count = int(store_status.get("snapshot_count", 0) or 0)
    dqs_status = ((latest or {}).get("dqs") or {}).get("status")
    dqs = (latest or {}).get("dqs") or {}
    provider_summary = _provider_summary(
        (latest or {}).get("provider_status") or {},
        decision_fallback_used=(bool(dqs.get("fallback_used")) if latest else None),
    )
    registry_runtime = _registry_runtime_summary((latest or {}).get("provider_status") or {})
    effective_flags = _effective_flags()
    try:
        from packages.discovery import news_discovery

        discovery_health = news_discovery.viewmodel(limit_events=0).get("stats", {})
    except Exception:
        discovery_health = {"scheduler": {"status": "UNAVAILABLE"}}
    try:
        from packages.learning.summary import build_summary

        learning_readiness = (build_summary() or {}).get("performance_readiness") or {
            "status": "UNAVAILABLE",
            "score": None,
        }
    except Exception:
        learning_readiness = {"status": "UNAVAILABLE", "score": None}
    try:
        from packages.notifications import list_recent
        from packages.paper import reconciliation, ticket
        from packages.paper import state as paper_state

        paper_state_view = paper_state.load()
        identity_reconciliation = reconciliation.reconcile(
            tickets=ticket.load_last(),
            positions=[p.__dict__ for p in paper_state_view.open_positions],
            notifications=[n.to_dict() for n in list_recent(limit=200)],
        )
    except Exception:
        identity_reconciliation = {"status": "UNAVAILABLE", "score": None, "paper_safe": True, "no_execution": True}

    active = halt_store.active_halts()
    risk_halt_status = {
        "active": bool(active),
        "count": len(active),
        "types": [h.type for h in active],
    }

    audit_errors = int((paper_audit.summary().get("counts") or {}).get("ERROR", 0))

    # last_successful_tick: heartbeat last_success_at (fallback: snapshot generated_at).
    last_successful_tick = tick.get("last_success_at") or (latest or {}).get("generated_at")
    last_learning_run = learning.get("last_success_at") or learning.get("completed_at")

    stale_workers = [w["worker_name"] for w in (tick, learning) if w["stale"]]

    # Owner warning'leri (sadece RAPOR — trade açmaz, RiskGate bypass etmez).
    warnings: list[str] = []
    if stale_workers:
        warnings.append("worker_stale")
    if tick["stale"]:
        warnings.append("stale_dashboard_state")
    if provider_summary["degraded_count"] > 0:
        warnings.append("provider_degraded")
    if provider_summary["observation_degraded_count"] > 0:
        warnings.append("provider_observe_degraded")
    if dqs_status == "BLOCKED":
        warnings.append("dqs_blocked")
    if snap_count == 0:
        warnings.append("snapshot_store_empty")
    if learning["status"] == "NO_DATA":
        warnings.append("learning_worker_no_data")
    if audit_errors > 0:
        warnings.append("paper_audit_errors")
    if risk_halt_status["active"]:
        warnings.append("active_halt")
    if registry_runtime["status"] != "OK":
        warnings.append("provider_registry_incomplete")
    if not effective_flags["discovery_scan_enabled"]:
        warnings.append("discovery_scan_disabled")

    # Cold-start / kullanıcı-eylemi gerektiren beklenen durumlar overall'u
    # degraded'a düşürmesin (warning yine raporlanır).
    INFO_ONLY = {
        "learning_worker_no_data", "snapshot_store_empty", "provider_observe_degraded",
        # These are surfaced explicitly for operations, but a fresh clone or
        # an intentionally disabled shadow worker must not make the API unusable.
        "provider_registry_incomplete", "discovery_scan_disabled",
    }
    severe = [w for w in warnings if w not in INFO_ONLY]

    return {
        "api_status": "degraded" if severe else "ok",
        "paper_safe": True,
        "no_execution": True,
        "workers": {"tick_worker": tick, "learning_worker": learning},
        "stale_workers": stale_workers,
        "last_successful_tick": last_successful_tick,
        "last_learning_run": last_learning_run,
        "provider_summary": provider_summary,
        "provider_registry": registry_runtime,
        "effective_flags": effective_flags,
        "news_discovery": discovery_health,
        "learning_readiness": learning_readiness,
        "identity_reconciliation": identity_reconciliation,
        "dqs_status": dqs_status,
        "snapshot_store_status": store_status,
        "risk_halt_status": risk_halt_status,
        "warnings": warnings,
    }


__all__ = ["build_system_health"]
