"""Trade Ticket builder — TradeDecision + snapshot + paper state → canonical Ticket.

Trade Ticket: broker'a manuel girmeden önce tek kartta her şey (entry/SL/TP/
size/confidence/checks/why/expiry). Karar zincirine dokunmaz — gözlemleyici.

Şema iki katmanlı:
  - `summary`: stable field names (agent + UI direkt kullanır)
  - `technical_detail`: 7 bölüm derin veri (collapsed UI + agent deep query)
  - `display`: plain-Türkçe pre-rendered string'ler (UI ve agent için template)

R/R adaptif (`packages/risk/trade_economics.compute_adaptive_targets`):
  - SL = ATR×1.5
  - TP = max(SL×3, doğal direnç/destek) but cap at SL×4.5
  - R/R floor 1:3 — yetersizse ticket `status="insufficient_rr"` (görünmez)

PAPER_SAFE / NO_EXECUTION — karar üretmez, mevcut state'i sunar.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from packages.data.ingestion.pipeline import MarketSnapshot
from packages.decision.engine import TradeDecision
from packages.paper.guards import price_sanity
from packages.paper.state import PaperState
from packages.risk.trade_economics import compute_adaptive_targets

# TF süresi (saat) — ticket expires_at için
_TF_HOURS = {"15m": 0.25, "1h": 1, "4h": 4, "1d": 24, "1w": 168}


@dataclass
class TradeTicket:
    id: str
    symbol: str
    side: str               # long | short
    timeframe: str
    status: str             # active | insufficient_rr | invalid
    expires_at: str
    ttl_seconds: int

    summary: dict[str, Any] = field(default_factory=dict)
    technical_detail: dict[str, Any] = field(default_factory=dict)
    display: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _confidence_label(p: float) -> str:
    if p >= 0.70:
        return "çok yüksek"
    if p >= 0.60:
        return "yüksek"
    if p >= 0.50:
        return "orta"
    return "düşük"


def _direction_action_label(direction: str, action: str) -> str:
    if action == "open_long":
        return "AL"
    if action == "open_short":
        return "SAT"
    if direction == "bullish":
        return "AL (zayıf)"
    if direction == "bearish":
        return "SAT (zayıf)"
    return "BEKLE"


def _why_bullets(decision: TradeDecision) -> list[str]:
    """Modül skorlarından sade Türkçe gerekçe."""
    bullets: list[str] = []
    cons = decision.consensus
    if not cons or not cons.modules:
        return ["Modül skorları henüz hesaplanmadı."]
    by_name = {m.name: m for m in cons.modules}

    touche = by_name.get("touche")
    if touche and touche.score >= 55:
        bullets.append(f"{decision.symbol}'in teknik göstergeleri yukarı yönlü")
    elif touche and touche.score <= 45:
        bullets.append(f"{decision.symbol}'in teknik göstergeleri aşağı yönlü")

    fund = by_name.get("fundamental")
    if fund and fund.score >= 55:
        bullets.append("Genel ekonomi koşulları risk almaya uygun")
    elif fund and fund.score <= 45:
        bullets.append("Genel ekonomi koşulları temkinli")

    sentinel = by_name.get("sentinel")
    if sentinel and sentinel.score >= 55:
        bullets.append("Yatırımcı iştahı normalin üzerinde")
    elif sentinel and sentinel.score <= 45:
        bullets.append("Yatırımcı iştahı düşük — korku var")

    news = by_name.get("news")
    if news and news.score >= 55:
        bullets.append("Haber akışı genel olarak olumlu")
    elif news and news.score <= 45:
        bullets.append("Haber akışı genel olarak olumsuz")

    quantum = by_name.get("quantum")
    if quantum and quantum.score >= 55:
        bullets.append("Sermaye akışı bu yönde rotasyona uygun")
    elif quantum and quantum.score <= 45:
        bullets.append("Sermaye akışı tersi yönde")

    if cons.confluence_aligned:
        bullets.append("3+ modül aynı yönde — uyumlu sinyal")
    return bullets[:5]


def _safety_lines(decision: TradeDecision, dqs_score: float | None) -> list[dict[str, str]]:
    """Güvenlik kontrolleri — her satır {level, text}."""
    lines: list[dict[str, str]] = []
    risk = decision.risk
    if risk:
        if risk.action == "ALLOW_NORMAL":
            lines.append({"level": "ok", "text": "Risk sistemleri açılışa onay verdi"})
        elif risk.action == "NO_POSITION_INCREASE":
            lines.append({"level": "warn", "text": "Risk sistemleri yeni girişi kısıtlıyor"})
        elif risk.action == "RISK_REDUCE":
            lines.append({"level": "warn", "text": "Risk sistemleri boyut azaltma öneriyor"})
        elif risk.action == "KILL_SWITCH":
            lines.append({"level": "error", "text": "Risk sistemleri tüm girişleri durdurdu"})

    if dqs_score is not None:
        if dqs_score >= 80:
            lines.append({"level": "ok", "text": f"Fiyat verisi güvenilir (sağlamlık %{int(dqs_score)})"})
        elif dqs_score >= 65:
            lines.append({"level": "warn", "text": f"Fiyat verisi orta sağlamlıkta (%{int(dqs_score)})"})
        else:
            lines.append({"level": "error", "text": f"Fiyat verisi zayıf (sağlamlık %{int(dqs_score)})"})

    catalyst = decision.catalyst_report or {}
    if catalyst.get("blocked"):
        lines.append({"level": "error", "text": "Önemli haber kısıtı aktif — pozisyon engellendi"})
    elif catalyst.get("imminent"):
        lines.append({"level": "warn", "text": "Yaklaşan önemli haber var — etki gözlemleniyor"})

    return lines


def _modules_table(decision: TradeDecision) -> list[dict[str, Any]]:
    cons = decision.consensus
    if not cons or not cons.modules:
        return []
    labels = {
        "touche": "Teknik",
        "fundamental": "Makro",
        "news": "Haber sentiment",
        "sentinel": "Risk iştahı",
        "quantum": "Sermaye rotasyonu",
        "chart_pattern": "Grafik desen",
    }
    return [
        {
            "name": m.name,
            "label": labels.get(m.name, m.name),
            "score": m.score,
            "weight": m.weight,
            "contribution": m.contribution,
        }
        for m in cons.modules
    ]


def _build_summary(
    decision: TradeDecision,
    entry: float,
    targets: Any,  # AdaptiveTargets
    size_usd: float,
    equity_usd: float,
) -> dict[str, Any]:
    risk_usd = (targets.sl_distance / entry * size_usd) if entry > 0 else 0.0
    return {
        "entry_price": round(entry, 4),
        "stop_loss": targets.sl,
        "take_profit": targets.tp,
        "rr_ratio": targets.rr,
        "rr_source": targets.tp_basis,  # resistance | support | atr_floor | atr_max | below_floor
        "size_usd": round(size_usd, 2),
        "size_pct_equity": round(size_usd / equity_usd * 100, 4) if equity_usd > 0 else 0.0,
        "risk_usd": round(risk_usd, 2),
        "risk_pct_equity": round(risk_usd / equity_usd * 100, 4) if equity_usd > 0 else 0.0,
        "confidence_calibrated": round(decision.confidence, 4),
        "confidence_raw": round(decision.raw_confidence, 4),
        "confidence_label": _confidence_label(decision.confidence),
        "consensus_score": decision.consensus.score if decision.consensus else 0.0,
        "consensus_direction": decision.consensus.direction if decision.consensus else "neutral",
        "atr": targets.sl_distance / 1.5 if targets.sl_distance > 0 else 0.0,
    }


def _build_technical_detail(
    decision: TradeDecision,
    snap: MarketSnapshot,
    targets: Any,
    paper_state: PaperState,
) -> dict[str, Any]:
    """7 bölüm: konsensüs · piyasa · geçmiş · güvenlik · sizing · kalibrasyon · audit."""
    cons = decision.consensus
    tech = None
    if snap.technicals_by_tf and decision.symbol in snap.technicals_by_tf:
        tech = snap.technicals_by_tf[decision.symbol].get(decision.timeframe)
    if tech is None:
        tech = snap.technicals.get(decision.symbol)

    return {
        "consensus": {
            "final_score": cons.score if cons else 0.0,
            "direction": cons.direction if cons else "neutral",
            "confluence_aligned": cons.confluence_aligned if cons else False,
            "dominant_module": cons.dominant_module if cons else "",
            "modules": _modules_table(decision),
            "warnings": cons.warnings if cons else [],
        },
        "market_state": {
            "symbol": decision.symbol,
            "timeframe": decision.timeframe,
            "rsi": getattr(tech, "rsi", None) if tech else None,
            "macd": getattr(tech, "macd", None) if tech else None,
            "atr": getattr(tech, "atr", None) if tech else None,
            "ema_stack": getattr(tech, "ema_stack", None) if tech else None,
            "technical_score": getattr(tech, "score", None) if tech else None,
            "technical_status": getattr(tech, "status", "UNKNOWN") if tech else "UNKNOWN",
            "support": targets.tp if targets.tp_basis == "support" else None,
            "resistance": targets.tp if targets.tp_basis == "resistance" else None,
            "dqs_score": snap.quality.score if snap.quality else None,
        },
        "fingerprint_history": {
            "fingerprint": decision.fingerprint,
            "mistake_verdict": decision.mistake_verdict or {},
        },
        "safety_checks": {
            "risk_action": decision.risk.action if decision.risk else None,
            "risk_reason": decision.risk.reason if decision.risk else None,
            "risk_evidence": decision.risk.evidence if decision.risk else [],
            "equity_usd": paper_state.equity_usd,
            "peak_equity_usd": paper_state.peak_equity_usd,
            "daily_pnl_usd": paper_state.daily_pnl_usd,
            "open_position_count": len(paper_state.open_positions),
            "blocked_by": decision.blocked_by,
            "derivatives_report": decision.derivatives_report or {},
            "volatility_report": decision.volatility_report or {},
            "catalyst_report": decision.catalyst_report or {},
            "options_report": decision.options_report or {},
        },
        "position_sizing": {
            "size_multiplier": decision.size_multiplier,
            "sl_basis": targets.sl_basis,
            "tp_basis": targets.tp_basis,
            "sl_distance": targets.sl_distance,
            "rr": targets.rr,
            "rr_floor_met": targets.rr_floor_met,
            "notes": targets.notes,
        },
        "calibration": {
            "raw_confidence": decision.raw_confidence,
            "calibrated_confidence": decision.confidence,
            "source": decision.confidence_source,
        },
        "audit": {
            "snapshot_id": snap.snapshot_id if snap.snapshot_id else None,
            "fingerprint": decision.fingerprint,
            "candidate_action": decision.candidate_action,
            "final_action": decision.action,
        },
    }


def _build_display(
    decision: TradeDecision,
    targets: Any,
    summary: dict[str, Any],
    expires_at: datetime,
    safety: list[dict[str, str]],
    why: list[str],
) -> dict[str, Any]:
    action_label = _direction_action_label(
        decision.consensus.direction if decision.consensus else "neutral",
        decision.action,
    )
    title = f"{decision.symbol} {action_label} · {decision.timeframe.upper()} Timeframe Sinyal"
    now = datetime.now(UTC)
    mins_left = int((expires_at - now).total_seconds() / 60)
    if mins_left >= 60:
        expiry = f"{mins_left // 60}sa {mins_left % 60}dk sonra fırsat kapanır"
    else:
        expiry = f"{max(0, mins_left)}dk sonra fırsat kapanır"

    rr = summary["rr_ratio"]
    if targets.tp_basis == "resistance":
        rr_note = f"Min 1:3 — doğal direnç hedefi 1:{rr:.1f}'a taşıdı"
    elif targets.tp_basis == "support":
        rr_note = f"Min 1:3 — doğal destek hedefi 1:{rr:.1f}'a taşıdı"
    elif targets.tp_basis == "atr_max":
        rr_note = f"Doğal hedef çok uzakta; ATR tavanı 1:{rr:.1f}"
    elif targets.tp_basis == "atr_floor":
        rr_note = f"Doğal hedef yok; ATR tabanı 1:{rr:.1f}"
    else:
        rr_note = f"R/R yetersiz: 1:{rr:.2f} (minimum 1:3)"

    return {
        "title": title,
        "expiry_text": expiry,
        "rr_text": f"1 dolara karşılık {rr:.1f} dolar kazanç",
        "rr_note": rr_note,
        "why_bullets": why,
        "safety_lines": safety,
        "confidence_text": f"%{int(decision.confidence * 100)} {_confidence_label(decision.confidence)}",
    }


def build_ticket(
    decision: TradeDecision,
    snap: MarketSnapshot,
    paper_state: PaperState,
    *,
    base_size_usd: float = 25_000.0,
) -> TradeTicket:
    """Karar + snapshot + state → TradeTicket. Sadece actionable kararlar için.

    Karar action `open_long`/`open_short` değilse status="invalid" döner.
    R/R floor (1:3) yetersizse status="insufficient_rr" — UI bu ticket'ı göstermez.
    """
    side = "long" if decision.action == "open_long" else "short" if decision.action == "open_short" else None
    ts = datetime.now(UTC)
    tf_hours = _TF_HOURS.get(decision.timeframe, 1.0)
    expires_at = ts + timedelta(hours=tf_hours)
    ticket_id = f"tk_{decision.symbol}_{decision.timeframe}_{int(ts.timestamp())}"

    if side is None:
        return TradeTicket(
            id=ticket_id,
            symbol=decision.symbol,
            side=decision.action,
            timeframe=decision.timeframe,
            status="invalid",
            expires_at=expires_at.isoformat(),
            ttl_seconds=int(tf_hours * 3600),
        )

    # Entry: current price (snapshot prices)
    entry = 0.0
    for q in snap.prices:
        if q.symbol == decision.symbol and q.price:
            entry = float(q.price)
            break
    sane_reason = price_sanity.price_sane_with_ohlcv_reason(
        decision.symbol, entry, timeframe=decision.timeframe
    )
    if sane_reason is not None:
        return TradeTicket(
            id=ticket_id,
            symbol=decision.symbol,
            side=side,
            timeframe=decision.timeframe,
            status="invalid",
            expires_at=expires_at.isoformat(),
            ttl_seconds=int(tf_hours * 3600),
            technical_detail={
                "safety_checks": {
                    "blocked_by": ["price_sanity"],
                    "price_sanity_reason": sane_reason,
                    "entry_price": round(entry, 4) if entry > 0 else entry,
                }
            },
        )

    tech = None
    if snap.technicals_by_tf and decision.symbol in snap.technicals_by_tf:
        tech = snap.technicals_by_tf[decision.symbol].get(decision.timeframe)
    if tech is None:
        tech = snap.technicals.get(decision.symbol)
    atr = float(getattr(tech, "atr", 0) or 0)

    # Support/resistance — for now use snapshot key_levels if available; else None
    support = None
    resistance = None
    # snap.technicals may carry key_levels in newer schema; fallback graceful
    if tech is not None and hasattr(tech, "key_levels") and tech.key_levels is not None:
        kl = tech.key_levels
        support = getattr(kl, "support", None)
        resistance = getattr(kl, "resistance", None)

    targets = compute_adaptive_targets(
        side=side,
        entry=entry,
        atr=atr,
        support=support,
        resistance=resistance,
    )

    size_usd = base_size_usd * decision.size_multiplier
    summary = _build_summary(decision, entry, targets, size_usd, paper_state.equity_usd)
    technical_detail = _build_technical_detail(decision, snap, targets, paper_state)
    why = _why_bullets(decision)
    safety = _safety_lines(decision, snap.quality.score if snap.quality else None)
    display = _build_display(decision, targets, summary, expires_at, safety, why)

    if not targets.rr_floor_met or entry <= 0 or atr <= 0:
        status = "insufficient_rr" if (entry > 0 and atr > 0) else "invalid"
    else:
        status = "active"

    return TradeTicket(
        id=ticket_id,
        symbol=decision.symbol,
        side=side,
        timeframe=decision.timeframe,
        status=status,
        expires_at=expires_at.isoformat(),
        ttl_seconds=int(tf_hours * 3600),
        summary=summary,
        technical_detail=technical_detail,
        display=display,
    )


def build_tickets_from_decisions(
    decisions: list[TradeDecision],
    snap: MarketSnapshot,
    paper_state: PaperState,
    *,
    base_size_usd: float = 25_000.0,
) -> list[TradeTicket]:
    """Bir tick'in tüm karar matrisinden ticket listesi üret.

    Yalnız actionable (open_long/open_short) ve status="active" olanlar UI'da
    görünür. status="insufficient_rr" telemetry için saklı; "invalid" atılır.
    """
    out: list[TradeTicket] = []
    for d in decisions:
        if d.action not in {"open_long", "open_short"}:
            continue
        t = build_ticket(d, snap, paper_state, base_size_usd=base_size_usd)
        if t.status != "invalid":
            out.append(t)
    return out
