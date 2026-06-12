"""DecisionEngine — consensus + risk + learning'i birleştirir.

G6 — Confidence calibration:
- Ham confidence (`|score-50|/50`) Platt scaling ile kalibre edilir.
- "insufficient" damgası TradeDecision'a yansır.

G3 — Mistake memory gate:
- Consensus eşiği aşıldıktan sonra mistake memory `evaluate(fingerprint)`
  çağrılır. AVOID→hold, BOOST→size_factor×, WARNING→size_factor×.
- NEUTRAL/insufficient → no_adjustment (size_factor=1.0).

G4 — Correlation-aware sizing:
- Mistake gate'ten sonra `cluster_exposure(open_positions, aday)` çağrılır.
  Aynı yönlü |rho| ≥ 0.7 cluster toplamı `max_cluster_pct`'yi aştıysa →
  hold; yarısını aştıysa size×0.5. **Sadece küçültür, asla artırmaz.**
  Veri yetersizse neutral fallback (adjustment yok).

**Hard kural:** mistake memory, calibration ve correlation sizing
**RiskGate'i bypass ETMEZ**. KILL_SWITCH→blocked;
RISK_REDUCE/NO_POSITION_INCREASE→hold.
DQS < 55 zaten risk engine'inde KILL_SWITCH üretir → BLOCKED state'te trade
yok (calibration BOOST veya mistake BOOST yüksek olsa bile).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

from packages.consensus.engine import ConsensusResult
from packages.consensus.engine import build as build_consensus
from packages.data.ingestion.pipeline import MarketSnapshot
from packages.data.registry.loader import load_thresholds
from packages.data.types import TIMEFRAMES
from packages.learning import mistake_memory
from packages.learning.calibration_store import (
    predict_calibrated,
    raw_confidence_from_score,
)
from packages.learning.fingerprint import make as make_fingerprint
from packages.learning.mistake_memory import MistakeVerdict
from packages.regime.classifier import RegimeOutput, classify
from packages.risk import correlation, derivatives_risk, event_risk
from packages.risk.engine import RiskDecision, RiskInput
from packages.risk.engine import evaluate as evaluate_risk

Action = Literal["open_long", "open_short", "hold", "blocked"]


@dataclass
class TradeDecision:
    symbol: str
    action: Action
    confidence: float           # calibrated p(win) ∈ [0,1]
    size_multiplier: float      # 0–1.5
    consensus: ConsensusResult
    risk: RiskDecision
    reason: str
    raw_confidence: float = 0.0
    confidence_source: str = "identity"
    fingerprint: str | None = None
    mistake_verdict: dict = field(default_factory=dict)
    cluster_report: dict = field(default_factory=dict)
    # v2.7 D2 — kripto türev riski (yalnızca kısıtlayıcı; crypto sembolleri).
    derivatives_report: dict = field(default_factory=dict)
    timeframe: str = "1d"  # T2 — (symbol, timeframe) karar uzayı aktif
    # T2 additive — candidate (consensus niyeti) vs final (gate'ler sonrası)
    # ayrımı görünür olsun; blocked_by hangi kapının kararı kestiğini söyler.
    candidate_action: Action = "hold"
    blocked_by: list[str] = field(default_factory=list)
    actionable: bool = False


def _timeframe_policy(timeframe: str) -> dict:
    """thresholds.timeframe_risk — yalnızca risk azaltıcı okunur.

    risk_multiplier 1.0'a clamp'lenir (hiçbir TF boyut ARTIRAMAZ);
    paper_execution=False (1w) doğrudan paper açılışını kapatır.
    """
    cfg = load_thresholds().get("timeframe_risk") or {}
    pol = cfg.get(timeframe) or {}
    return {
        "role": str(pol.get("role", "")),
        "risk_multiplier": min(1.0, float(pol.get("risk_multiplier", 1.0))),
        "paper_execution": bool(pol.get("paper_execution", True)),
        "time_stop_hours": int(pol.get("time_stop_hours", 0)),
    }


def time_stop_hours(timeframe: str) -> int:
    """Paper katmanı için TF time-stop süresi (saat; 0 → time-stop yok)."""
    return _timeframe_policy(timeframe)["time_stop_hours"]


def _candidate_from_score(score: float, th: dict) -> tuple[Action, float]:
    """Consensus skorundan ham niyet (candidate) + taban boyut."""
    if score >= th["strong_bullish_min"]:
        return "open_long", 1.5
    if score >= th["bullish_min"]:
        return "open_long", 1.0
    if score <= th["strong_bearish_max"]:
        return "open_short", 1.5
    if score <= th["bearish_max"]:
        return "open_short", 1.0
    return "hold", 0.0


def _regime_multiplier(label: str) -> float:
    return {"OFFENSIVE": 1.0, "NEUTRAL": 0.8, "DEFENSIVE": 0.5, "CRISIS": 0.35}.get(label, 0.5)


def _verdict_to_dict(v: MistakeVerdict) -> dict:
    return {
        "action": v.action,
        "reason": v.reason,
        "size_factor": v.size_factor,
        "evidence": list(v.evidence),
        "fingerprint": v.fingerprint,
        "record": asdict(v.record) if v.record else None,
    }


def decide_for_symbol(
    symbol: str,
    snap: MarketSnapshot,
    regime: RegimeOutput,
    risk: RiskDecision,
    mistakes: list | None = None,
    open_positions: list | None = None,
    equity_usd: float = 0.0,
    corr_entries: list | None = None,
    timeframe: str = "1d",
) -> TradeDecision:
    th = load_thresholds()["consensus"]
    cons = build_consensus(symbol, snap, regime, timeframe)
    pol = _timeframe_policy(timeframe)

    raw_conf = raw_confidence_from_score(cons.score)
    cal_conf, conf_source = predict_calibrated(raw_conf)

    # Candidate = consensus'un ham niyeti (gate'lerden önce) — dashboard
    # candidate vs final ayrımını bununla gösterir.
    candidate, base_size = _candidate_from_score(cons.score, th)

    # Fingerprint hesabı (mistake memory için her zaman üret — debugging).
    # T2: gerçek timeframe segmenti taşır → 15m hatası 1d'yi cezalandırmaz.
    fp = make_fingerprint(
        symbol=symbol,
        regime=regime.label,
        direction=cons.direction,
        score=cons.score,
        confluence=cons.confluence_aligned,
        dominant_module=cons.dominant_module or "?",
        timeframe=timeframe,
    )

    # ----- Risk hard gate'leri ÖNCE (timeframe dahil hiçbir katman bypass etmez) -----
    if risk.action == "KILL_SWITCH":
        return TradeDecision(
            symbol=symbol,
            action="blocked",
            confidence=0.0,
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=f"Risk kapısı: {risk.action}",
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
            fingerprint=fp,
            timeframe=timeframe,
            candidate_action=candidate,
            blocked_by=[f"risk_gate:{risk.action}"],
        )
    if risk.action in {"NO_POSITION_INCREASE", "RISK_REDUCE"}:
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=0.0,
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=f"Risk kapısı: {risk.action}",
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
            fingerprint=fp,
            timeframe=timeframe,
            candidate_action=candidate,
            blocked_by=[f"risk_gate:{risk.action}"],
        )

    # ----- Consensus eşikleri -----
    action: Action = candidate
    size = base_size
    if action == "hold":
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=round(cal_conf, 3),
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason="Consensus eşiği aşılmadı",
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
            fingerprint=fp,
            timeframe=timeframe,
            candidate_action=candidate,
        )

    # Confluence yoksa boyut yarıya iner
    if not cons.confluence_aligned:
        size *= 0.5
    size *= _regime_multiplier(regime.label)

    # ----- G3: Mistake memory gate (RiskGate'i ASLA bypass etmez) -----
    verdict = mistake_memory.evaluate(fp, mistakes)
    if verdict.action == "AVOID":
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=round(cal_conf, 3),
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=f"mistake_memory: {verdict.reason}",
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
            fingerprint=fp,
            mistake_verdict=_verdict_to_dict(verdict),
            timeframe=timeframe,
            candidate_action=candidate,
            blocked_by=["mistake_memory:AVOID"],
        )

    size *= verdict.size_factor
    size = max(0.0, min(1.5, size))

    # ----- G4: Correlation cluster cap (sadece küçültür, RiskGate'i bypass etmez) -----
    cluster = correlation.cluster_exposure(
        open_positions or [],
        symbol,
        "long" if action == "open_long" else "short",
        equity_usd,
        entries=corr_entries,
    )
    cluster_dict = asdict(cluster)
    if cluster.size_factor <= 0.0:
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=round(cal_conf, 3),
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=(
                f"correlation_cluster: aynı yönlü exposure {cluster.cluster_pct:.0%}"
                f" ≥ cap {cluster.max_cluster_pct:.0%}"
            ),
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
            fingerprint=fp,
            mistake_verdict=_verdict_to_dict(verdict),
            cluster_report=cluster_dict,
            timeframe=timeframe,
            candidate_action=candidate,
            blocked_by=["correlation_cluster_cap"],
        )
    size *= min(1.0, cluster.size_factor)
    size = max(0.0, min(1.5, size))

    # ----- v2.7 D2: kripto türev riski (RiskGate'ten SONRA; yalnızca kısıtlayıcı) -----
    # Yalnızca crypto sembolleri + verified/OK snapshot karar zincirine girer.
    # 15m/1h reaksiyon için derivatives daha önemli (timeframe ağırlığı); asla
    # size artırmaz, asla RiskGate/DQS/halt'ı bypass etmez (bu kod yalnızca
    # RiskGate açıkken çalışır — hard gate'ler yukarıda zaten dönmüş olur).
    derivatives_dict: dict = {}
    deriv_snap = (snap.derivatives or {}).get(symbol)
    deriv_weight = derivatives_risk.timeframe_weight(timeframe)
    if deriv_snap is not None and deriv_weight > 0.0:
        dv = derivatives_risk.apply_timeframe(
            derivatives_risk.assess(deriv_snap, action), deriv_weight
        )
        derivatives_dict = {
            "level": dv.level,
            "size_factor": dv.size_factor,
            "block": dv.block,
            "reason": dv.reason,
            "evidence": list(dv.evidence),
            "squeeze_level": deriv_snap.squeeze_level,
            "squeeze_proxy": deriv_snap.squeeze_proxy,
            "funding_bias": deriv_snap.funding_bias,
            "is_proxy": deriv_snap.is_proxy,
        }
        if dv.block:
            return TradeDecision(
                symbol=symbol,
                action="hold",
                confidence=round(cal_conf, 3),
                size_multiplier=0.0,
                consensus=cons,
                risk=risk,
                reason=f"derivatives_risk: {dv.reason}",
                raw_confidence=round(raw_conf, 4),
                confidence_source=conf_source,
                fingerprint=fp,
                mistake_verdict=_verdict_to_dict(verdict),
                cluster_report=cluster_dict,
                derivatives_report=derivatives_dict,
                timeframe=timeframe,
                candidate_action=candidate,
                blocked_by=[f"derivatives_risk:{dv.level}"],
            )
        size *= dv.size_factor
        size = max(0.0, min(1.5, size))

    # ----- T2: timeframe politikası EN SON (RiskGate'ten sonra; sadece azaltır) -----
    blocked_by: list[str] = []
    if not pol["paper_execution"]:
        # 1w strategic view — doğrudan paper trade açmaz; yön bilgisi
        # matrix'te bias olarak görünür.
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=round(cal_conf, 3),
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=f"timeframe {timeframe} ({pol['role']}): paper execution kapalı — sadece bias",
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
            fingerprint=fp,
            mistake_verdict=_verdict_to_dict(verdict),
            cluster_report=cluster_dict,
            derivatives_report=derivatives_dict,
            timeframe=timeframe,
            candidate_action=candidate,
            blocked_by=["timeframe_policy:no_paper_execution"],
        )
    # Çarpan sadece küçültür (≤1.0 clamp'li) — blocked_by'a girmez,
    # reason + size_multiplier üzerinden görünür.
    size *= pol["risk_multiplier"]

    return TradeDecision(
        symbol=symbol,
        action=action,
        confidence=round(min(0.99, cal_conf), 3),
        size_multiplier=round(size, 3),
        consensus=cons,
        risk=risk,
        reason=(
            f"{cons.direction} signal · dominant={cons.dominant_module}"
            + (f" · mistake:{verdict.action.lower()}" if verdict.action != "NEUTRAL" else "")
            + (f" · correlation:{cluster.status.lower()}" if cluster.status != "OK" else "")
            + (
                f" · deriv:{derivatives_dict['level'].lower()}"
                if derivatives_dict and derivatives_dict.get("level") not in (None, "NONE")
                else ""
            )
            + (f" · tf:{timeframe}×{pol['risk_multiplier']}" if pol["risk_multiplier"] < 1.0 else "")
        ),
        raw_confidence=round(raw_conf, 4),
        confidence_source=conf_source,
        fingerprint=fp,
        mistake_verdict=_verdict_to_dict(verdict),
        cluster_report=cluster_dict,
        derivatives_report=derivatives_dict,
        timeframe=timeframe,
        candidate_action=candidate,
        blocked_by=blocked_by,
        actionable=size > 0.0,
    )


def decide_all(
    symbols: list[str],
    snap: MarketSnapshot,
    paper_state_input: RiskInput,
    open_positions: list | None = None,
) -> tuple[RegimeOutput, RiskDecision, list[TradeDecision]]:
    regime = classify(snap)
    # P0 — olay riski yalnızca kısıtlayıcı ek candidate; DQS/halt'ı ezemez.
    risk = evaluate_risk(
        paper_state_input,
        event_candidates=event_risk.risk_candidates(snap.catalysts),
    )
    # Tek pass mistake özeti — tüm semboller için aynı snapshot.
    mems = mistake_memory.summary()
    positions = open_positions or []
    # Korelasyon matrisi tek pass (aday + açık pozisyon sembolleri).
    corr_entries = correlation.matrix(
        sorted({*symbols, *(p.symbol for p in positions)})
    )
    decisions = [
        decide_for_symbol(
            s,
            snap,
            regime,
            risk,
            mistakes=mems,
            open_positions=positions,
            equity_usd=paper_state_input.equity_usd,
            corr_entries=corr_entries,
        )
        for s in symbols
    ]
    return regime, risk, decisions


def decide_matrix(
    symbols: list[str],
    snap: MarketSnapshot,
    paper_state_input: RiskInput,
    open_positions: list | None = None,
    timeframes: list[str] | None = None,
) -> tuple[RegimeOutput, RiskDecision, list[TradeDecision]]:
    """T2 — (symbol, timeframe) karar matrisi.

    Her hücre decide_for_symbol'dan geçer (RiskGate önce, timeframe sonra).
    Üst-TF bias kuralı: 1w consensus yönü alt TF open kararının TERSİYSE
    boyut ×0.5 (asla artırma yok; 1w zaten kendi başına trade açamaz).
    """
    regime = classify(snap)
    # P0 — olay riski yalnızca kısıtlayıcı ek candidate; DQS/halt'ı ezemez.
    risk = evaluate_risk(
        paper_state_input,
        event_candidates=event_risk.risk_candidates(snap.catalysts),
    )
    mems = mistake_memory.summary()
    positions = open_positions or []
    corr_entries = correlation.matrix(
        sorted({*symbols, *(p.symbol for p in positions)})
    )
    tfs = [tf for tf in (timeframes or list(TIMEFRAMES)) if tf in TIMEFRAMES]
    decisions: list[TradeDecision] = []
    for s in symbols:
        per_tf = {
            tf: decide_for_symbol(
                s,
                snap,
                regime,
                risk,
                mistakes=mems,
                open_positions=positions,
                equity_usd=paper_state_input.equity_usd,
                corr_entries=corr_entries,
                timeframe=tf,
            )
            for tf in tfs
        }
        weekly = per_tf.get("1w")
        if weekly is not None:
            bias = weekly.consensus.direction
            for tf, d in per_tf.items():
                if tf == "1w" or d.action not in {"open_long", "open_short"}:
                    continue
                conflict = (d.action == "open_long" and bias == "bearish") or (
                    d.action == "open_short" and bias == "bullish"
                )
                if conflict:
                    d.size_multiplier = round(d.size_multiplier * 0.5, 3)
                    d.blocked_by.append("1w_bias_conflict:scale_down")
                    d.reason += f" · 1w bias {bias} → size×0.5"
        decisions.extend(per_tf[tf] for tf in tfs)
    return regime, risk, decisions


# Matrix hücresinin actionable/suspended rozetini frontend HESAPLAMAZ —
# backend ViewModel üretir (DASHBOARD_RULES).
def matrix_view(
    regime: RegimeOutput,
    risk: RiskDecision,
    decisions: list[TradeDecision],
    snap: MarketSnapshot,
    symbols: list[str],
    timeframes: list[str] | None = None,
) -> dict:
    from datetime import UTC, datetime

    tfs = [tf for tf in (timeframes or list(TIMEFRAMES)) if tf in TIMEFRAMES]
    suspended = (
        risk.action in {"KILL_SWITCH", "RISK_REDUCE", "NO_POSITION_INCREASE"}
        or snap.quality.status == "BLOCKED"
    )
    # P0 — olay riski ayrı görünür blok (RiskGate'i bypass etmez; hangi olayın
    # hücreleri kıstığını dashboard'da göstermek için). Restrictive olduğunda
    # zaten yukarıdaki `risk` içine NO_POSITION_INCREASE candidate olarak girmiş.
    ev = event_risk.assess(snap.catalysts)
    # v2.7 D2 — kripto türev özeti (yalnızca kısıtlayıcı; etkilenen hücreler
    # cell.blocked_by="derivatives_risk:*" ile zaten görünür). Bu blok panel
    # banner'ı için per-symbol squeeze/funding durumunu taşır.
    derivatives_summary = [
        {
            "symbol": d.symbol,
            "squeeze_level": d.squeeze_level,
            "squeeze_proxy": d.squeeze_proxy,
            "funding_bias": d.funding_bias,
            "funding_rate": d.funding_rate,
            "is_proxy": d.is_proxy,
            "status": d.status,
            "verified": d.verified,
        }
        for d in (snap.derivatives or {}).values()
        if d.status == "OK"
    ]
    cells = []
    for d in decisions:
        actionable = bool(d.actionable) and not suspended
        if suspended:
            status = "SUSPENDED"
        elif actionable:
            status = "ACTIONABLE"
        else:
            status = "NOT_ACTIONABLE"
        cells.append(
            {
                "symbol": d.symbol,
                "timeframe": d.timeframe,
                "action": d.action,
                "candidate_action": d.candidate_action,
                "score": d.consensus.score,
                "direction": d.consensus.direction,
                "confidence": d.confidence,
                "size_multiplier": d.size_multiplier,
                "reason": d.reason,
                "blocked_by": list(d.blocked_by),
                "actionable": actionable,
                "status": status,
                "paper_action": d.action if actionable else "none",
            }
        )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "symbols": list(symbols),
        "timeframes": tfs,
        "regime": regime.label,
        "risk_gate": {
            "action": risk.action,
            "reason": risk.reason,
            "evidence": list(risk.evidence),
        },
        "dqs_status": snap.quality.status,
        "suspended": suspended,
        "event_risk": {
            "level": ev.level,
            "action": ev.action,
            "reason": ev.reason,
            "evidence": list(ev.evidence),
            "restrictive": ev.restrictive,
            "triggers": [
                {
                    "id": t.id,
                    "title": t.title,
                    "importance": t.importance,
                    "hours_until": t.hours_until,
                    "days_until": t.days_until,
                    "level": t.level,
                }
                for t in ev.triggers
            ],
        },
        "derivatives": derivatives_summary,
        "cells": cells,
    }
