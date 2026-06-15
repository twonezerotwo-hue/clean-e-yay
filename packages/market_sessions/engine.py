"""Market-session engine — deterministic phase rules, asset context, gate policy.

Pure decision-support: it reads config + calendar and produces context. It does
NOT import paper/risk/broker code, does NOT open/close trades, and does NOT
duplicate RiskGate. The gating policy is restrictive-only:
``block > manual_ready > caution > allow`` and ``size_multiplier`` is always ≤ 1.0
(market sessions can never increase size).
"""
from __future__ import annotations

from datetime import UTC, datetime

from .calendar_provider import ResolvedSession, resolve_session
from .config import MarketConfig, MarketSessionsConfig, SessionThresholds, load_config
from .models import (
    AssetSessionContext,
    LiquidityTone,
    MarketSessionDecision,
    MarketSessionDecisionInput,
    MarketSessionStatus,
    SessionPhase,
)


def _minutes(seconds: float) -> int:
    return int(seconds // 60)


def _norm_now(now_utc: datetime) -> datetime:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=UTC)
    return now_utc.astimezone(UTC)


def _dedup(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for it in items:
        seen.setdefault(it, None)
    return list(seen)


def _phase(
    market: MarketConfig,
    rs: ResolvedSession,
    now_utc: datetime,
    th: SessionThresholds,
) -> tuple[SessionPhase, LiquidityTone, bool, int | None, int | None]:
    """Return (phase, liquidity_tone, volatility_window, minutes_to_open, minutes_to_close)."""
    # 24/7 continuous market.
    if market.kind == "continuous":
        m_to_close = (
            max(0, _minutes((rs.close_utc - now_utc).total_seconds())) if rs.close_utc else None
        )
        return "mid_session", "high", False, None, m_to_close

    # No session info at all → unknown (calendar unavailable, never invented).
    if not rs.is_open and rs.open_utc is None and rs.close_utc is None and rs.next_open_utc is None:
        return "unknown", "unknown", False, None, None

    if rs.is_open and rs.open_utc is not None and rs.close_utc is not None:
        m_to_close = max(0, _minutes((rs.close_utc - now_utc).total_seconds()))
        m_since_open = _minutes((now_utc - rs.open_utc).total_seconds())
        if m_since_open <= th.opening_post_minutes:
            return "opening_window", "high", True, None, m_to_close
        if m_to_close <= th.closing_pre_minutes:
            return "closing_window", "high", True, None, m_to_close
        return "mid_session", "normal", False, None, m_to_close

    # Closed: classify by proximity to the next open / today's close.
    m_to_open = (
        max(0, _minutes((rs.next_open_utc - now_utc).total_seconds())) if rs.next_open_utc else None
    )
    if m_to_open is not None and m_to_open <= th.opening_pre_minutes:
        return "opening_window", "thin", True, m_to_open, None
    if m_to_open is not None and m_to_open <= th.pre_open_watch_minutes:
        return "pre_open", "thin", False, m_to_open, None
    if rs.close_utc is not None and now_utc >= rs.close_utc:
        return "after_close", "thin", False, m_to_open, None
    return "closed", "closed", False, m_to_open, None


def market_status(
    market: MarketConfig,
    now_utc: datetime,
    thresholds: SessionThresholds,
    resolved: ResolvedSession | None = None,
) -> MarketSessionStatus:
    now_utc = _norm_now(now_utc)
    rs = resolved or resolve_session(market, now_utc)
    phase, liquidity, vol, m_to_open, m_to_close = _phase(market, rs, now_utc, thresholds)
    return MarketSessionStatus(
        market_id=market.market_id,
        label=market.label,
        exchange=market.exchange,
        timezone=market.timezone,
        is_open=rs.is_open,
        is_holiday=rs.is_holiday,
        open_time_utc=rs.open_utc.isoformat() if rs.open_utc else None,
        close_time_utc=rs.close_utc.isoformat() if rs.close_utc else None,
        minutes_to_open=m_to_open,
        minutes_to_close=m_to_close,
        session_phase=phase,
        liquidity_tone=liquidity,
        volatility_window=vol,
        holiday_verified=rs.holiday_verified,
        diagnostics=list(rs.diagnostics),
    )


def all_market_statuses(
    now_utc: datetime, cfg: MarketSessionsConfig | None = None
) -> list[MarketSessionStatus]:
    cfg = cfg or load_config()
    now_utc = _norm_now(now_utc)
    return [market_status(m, now_utc, cfg.thresholds) for m in cfg.markets]


def asset_context(
    asset_code: str, now_utc: datetime, cfg: MarketSessionsConfig | None = None
) -> AssetSessionContext:
    cfg = cfg or load_config()
    now_utc = _norm_now(now_utc)
    markets = cfg.markets_for_asset(asset_code)

    if not markets:
        return AssetSessionContext(
            asset_code=asset_code.upper(),
            relevant_markets=[],
            any_relevant_market_open=False,
            primary_market_open=None,
            session_risk="unknown",
            reason="No market mapping for asset",
            diagnostics=["asset_unmapped"],
        )

    statuses = [market_status(m, now_utc, cfg.thresholds) for m in markets]
    any_open = any(s.is_open for s in statuses)
    is_crypto = any(m.kind == "continuous" for m in markets)

    primary = next(
        (s for s, m in zip(statuses, markets, strict=True) if m.kind == "exchange"),
        statuses[0],
    )

    diagnostics: list[str] = []
    for s in statuses:
        diagnostics.extend(s.diagnostics)

    opening = any(s.session_phase == "opening_window" for s in statuses)
    closing = any(s.session_phase == "closing_window" for s in statuses)
    all_unknown = all(s.session_phase == "unknown" for s in statuses)

    if is_crypto:
        session_risk, reason = "normal", "Crypto trades 24/7"
    elif all_unknown:
        session_risk, reason = "unknown", "Session calendar unavailable"
    elif opening:
        session_risk, reason = "manual_review", "Relevant market in opening window"
    elif closing:
        session_risk, reason = "manual_review", "Relevant market in closing window"
    elif any_open:
        session_risk, reason = "normal", "Relevant market open"
    else:
        session_risk, reason = "manual_review", "No relevant primary market is open"

    return AssetSessionContext(
        asset_code=asset_code.upper(),
        relevant_markets=statuses,
        any_relevant_market_open=any_open,
        primary_market_open=primary.is_open,
        session_risk=session_risk,
        reason=reason,
        diagnostics=_dedup(diagnostics),
    )


def _clamp_multiplier(value: float) -> float:
    """Market sessions may only RESTRICT — never above 1.0 (no size boost)."""
    return min(1.0, max(0.0, value))


def evaluate(
    inp: MarketSessionDecisionInput, cfg: MarketSessionsConfig | None = None
) -> MarketSessionDecision:
    """Map asset session context → restrictive trading-gate decision.

    Sessions produce *context only*; RiskGate stays final and is applied
    separately. Precedence: block > manual_ready > caution > allow.
    """
    cfg = cfg or load_config()
    now_utc = _norm_now(inp.now_utc)
    ctx = asset_context(inp.asset_code, now_utc, cfg)
    markets = cfg.markets_for_asset(inp.asset_code)
    is_crypto = any(m.kind == "continuous" for m in markets)
    diagnostics = list(ctx.diagnostics)
    evidence: list[str] = []

    # Crypto: open 24/7 → allow, but carry caution evidence when a correlated
    # equity session is at a high-volatility boundary (risk assets may react).
    if is_crypto:
        for s in ctx.relevant_markets:
            if s.session_phase in ("opening_window", "closing_window"):
                evidence.append(f"{s.market_id} {s.session_phase} — risk assets may react")
        us = cfg.market_by_id("US_EQUITY")
        if us is not None:
            us_status = market_status(us, now_utc, cfg.thresholds)
            if us_status.session_phase in ("opening_window", "closing_window"):
                evidence.append(f"US_EQUITY {us_status.session_phase} — crypto/risk correlation")
        return MarketSessionDecision(
            action="allow",
            size_multiplier=1.0,
            reason="Crypto market open 24/7",
            reason_code=None,
            evidence=evidence,
            diagnostics=diagnostics,
        )

    # Unmapped asset or calendar genuinely unknown → caution (restrictive, not fake allow).
    if ctx.session_risk == "unknown":
        diagnostics.append("calendar_unknown")
        return MarketSessionDecision(
            action="caution",
            size_multiplier=_clamp_multiplier(0.75),
            reason="Session calendar unknown — restrictive",
            reason_code="market_session_calendar_unknown",
            evidence=evidence,
            diagnostics=_dedup(diagnostics),
        )

    opening = next((s for s in ctx.relevant_markets if s.session_phase == "opening_window"), None)
    if opening is not None:
        evidence.append(f"{opening.market_id} opening_window")
        return MarketSessionDecision(
            action="manual_ready",
            size_multiplier=_clamp_multiplier(0.5),
            reason="Opening window volatility",
            reason_code="market_session_opening_window",
            evidence=evidence,
            diagnostics=_dedup(diagnostics),
        )

    closing = next((s for s in ctx.relevant_markets if s.session_phase == "closing_window"), None)
    if closing is not None:
        evidence.append(f"{closing.market_id} closing_window")
        return MarketSessionDecision(
            action="manual_ready",
            size_multiplier=_clamp_multiplier(0.5),
            reason="Closing window liquidity/volatility risk",
            reason_code="market_session_closing_window",
            evidence=evidence,
            diagnostics=_dedup(diagnostics),
        )

    if not ctx.any_relevant_market_open:
        return MarketSessionDecision(
            action="manual_ready",
            size_multiplier=_clamp_multiplier(0.5),
            reason="No relevant primary market is open",
            reason_code="market_session_no_relevant_market",
            evidence=[f"{s.market_id} {s.session_phase}" for s in ctx.relevant_markets],
            diagnostics=_dedup(diagnostics),
        )

    # Relevant market open, mid-session → allow at full (deterministic) size.
    return MarketSessionDecision(
        action="allow",
        size_multiplier=1.0,
        reason="Relevant market open (mid-session)",
        reason_code=None,
        evidence=[f"{s.market_id} {s.session_phase}" for s in ctx.relevant_markets if s.is_open],
        diagnostics=_dedup(diagnostics),
    )
