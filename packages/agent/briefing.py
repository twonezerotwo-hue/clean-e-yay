"""Agent Briefing — sistem state'inden deterministik başlık listesi üretir.

LLM gerektirmez. Her başlık: tone (ok/info/warn/alert) + kategori + bir
satırlık özet + isteğe bağlı detay. UI tarafı bunu poll'lar veya SSE
tick.complete event'inde yeniler.

Karar mantığı yok — sadece "şu an state şu, kullanıcı tek bakışta görsün".
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from packages.data.ingestion.pipeline import DEFAULT_SYMBOLS, get_cached_snapshot
from packages.decision.engine import decide_matrix, matrix_view
from packages.notifications import list_recent as list_notifications
from packages.ops import heartbeat
from packages.paper import state as paper_state
from packages.regime.classifier import classify
from packages.risk import halt as halt_store
from packages.risk.engine import RiskInput

Tone = Literal["ok", "info", "warn", "alert"]


@dataclass
class Headline:
    tone: Tone
    category: str  # "market" | "agent" | "risk" | "events" | "news" | "providers" | "system"
    title: str
    detail: str | None = None


# ── Eşikler (config'le uyumlu, tek kaynak: thresholds_v1.0.yaml) ──
SCORE_DIRECTIONAL = 60   # consensus.bullish_min
SCORE_STRONG = 70        # consensus.strong_bullish_min
SCORE_SCOUT = 60         # decision.scout_alignment_min


def _safe_cells(snap):
    """matrix_view cells — direction/score/timeframe/final_action içerir."""
    try:
        ps = paper_state.load()
        risk_in = RiskInput(
            dqs_score=snap.quality.score,
            equity_usd=ps.equity_usd,
            peak_equity_usd=ps.peak_equity_usd,
            daily_pnl_usd=ps.daily_pnl_usd,
            open_position_count=len(ps.open_positions),
        )
        symbols = DEFAULT_SYMBOLS[:4]
        regime, risk, decisions = decide_matrix(
            symbols, snap, risk_in, open_positions=ps.open_positions
        )
        view = matrix_view(regime, risk, decisions, snap, symbols)
        return view.get("cells") or []
    except Exception:
        return []


def _market_headlines(snap, cells) -> list[Headline]:
    out: list[Headline] = []
    if not cells:
        out.append(Headline("info", "market", "Karar matrisi boş — veri bekleniyor."))
        return out

    bullish = [c for c in cells if c.get("direction") == "bullish"]
    bearish = [c for c in cells if c.get("direction") == "bearish"]
    neutral = [c for c in cells if c.get("direction") == "neutral"]

    if bullish or bearish:
        out.append(Headline(
            "info", "market",
            f"Yön: {len(bullish)} bullish, {len(bearish)} bearish, {len(neutral)} nötr.",
        ))
    else:
        out.append(Headline(
            "info", "market",
            f"Piyasa nötr — {len(neutral)} hücrenin tamamı yön vermiyor.",
        ))

    top = max(cells, key=lambda c: c.get("score") or 0)
    score = top.get("score") or 0
    sym = top.get("symbol", "?")
    tf = top.get("timeframe", "?")
    gap_dir = SCORE_DIRECTIONAL - score
    gap_scout = SCORE_SCOUT - score
    if gap_dir <= 0:
        out.append(Headline(
            "ok", "market",
            f"{sym} {tf} skor {score:.0f} → yön eşiğini geçti.",
            f"Aksiyon eşiğine ({SCORE_SCOUT}) {-gap_scout:+.1f} puan.",
        ))
    elif gap_dir <= 2:
        out.append(Headline(
            "info", "market",
            f"En yakın: {sym} {tf} skor {score:.1f}/60 — yön eşiğine {gap_dir:.1f} puan.",
            f"SCOUT için ek {gap_scout:.1f} puan gerek.",
        ))
    else:
        out.append(Headline(
            "info", "market",
            f"En yüksek: {sym} {tf} = {score:.1f}/60. Yön sinyali zayıf.",
        ))
    return out


def _agent_headlines() -> list[Headline]:
    out: list[Headline] = []
    hb = heartbeat.load_all() or {}
    tick = hb.get("tick_worker") or {}
    learn = hb.get("learning_worker") or {}

    if tick:
        cycles = tick.get("cycle_count") or 0
        status = tick.get("status") or "?"
        tone: Tone = "ok" if status == "OK" else ("warn" if status == "DEGRADED" else "alert")
        age_txt = "?"
        completed = tick.get("completed_at")
        if isinstance(completed, str):
            try:
                ts = datetime.fromisoformat(completed.replace("Z", "+00:00"))
                age = (datetime.now(UTC) - ts).total_seconds()
                age_txt = f"{age:.0f}s"
            except Exception:
                pass
        out.append(Headline(
            tone, "agent",
            f"Tick: {status} · {cycles} cycle · son {age_txt} önce.",
            f"{tick.get('decisions_generated', 0)} karar / {tick.get('snapshots_written', 0)} snapshot bu cycle.",
        ))

    if learn:
        status = learn.get("status") or "?"
        outcomes = learn.get("learning_outcomes_seen") or 0
        if status == "NO_DATA":
            out.append(Headline(
                "info", "agent",
                "Öğrenme: henüz veri yok (kapanmış paper trade gerekli).",
            ))
        else:
            out.append(Headline(
                "ok", "agent",
                f"Öğrenme: {status} · {outcomes} outcome görüldü.",
            ))
    return out


def _risk_headlines(snap) -> list[Headline]:
    out: list[Headline] = []
    try:
        halts = halt_store.active_halts() or []
    except Exception:
        halts = []
    if halts:
        out.append(Headline(
            "alert", "risk",
            f"AKTİF HALT: {len(halts)}",
            ", ".join(getattr(h, "kind", None) or "?" for h in halts),
        ))
    else:
        out.append(Headline("ok", "risk", "Aktif halt yok."))

    try:
        ps = paper_state.load()
        n = len(ps.open_positions or [])
        if n:
            total = sum(p.size_usd for p in ps.open_positions)
            out.append(Headline(
                "info", "risk",
                f"{n} açık pozisyon · toplam ${total:,.0f}.",
            ))
        else:
            out.append(Headline("info", "risk", "Açık pozisyon yok."))
    except Exception:
        pass

    return out


def _event_headlines(snap) -> list[Headline]:
    out: list[Headline] = []
    cats = list(getattr(snap, "catalysts", None) or [])
    if not cats:
        out.append(Headline("info", "events", "Yaklaşan takvim olayı yok."))
        return out

    now = datetime.now(UTC)
    upcoming = []
    for c in cats:
        ts = getattr(c, "scheduled_at", None) or getattr(c, "ts", None)
        if not ts:
            continue
        try:
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            delta = ts - now
            hours = delta.total_seconds() / 3600
            if hours < -1:
                continue
            upcoming.append((hours, getattr(c, "label", None) or getattr(c, "id", "?"),
                             getattr(c, "importance", None) or getattr(c, "level", None)))
        except Exception:
            continue

    upcoming.sort(key=lambda x: x[0])
    if not upcoming:
        out.append(Headline("info", "events", "Yaklaşan olay yok."))
        return out

    nearest = upcoming[0]
    hours, label, importance = nearest
    days = hours / 24
    when = f"{days:.0f}g sonra" if days >= 1 else f"{hours:.0f}sa sonra"
    tone: Tone = "warn" if hours < 24 and (importance or "").lower() in ("high", "critical") else "info"
    out.append(Headline(
        tone, "events",
        f"En yakın olay: {label} ({when}).",
        f"Önümüzdeki dönemde {len(upcoming)} olay takvimde." if len(upcoming) > 1 else None,
    ))
    return out


def _news_headlines(snap) -> list[Headline]:
    out: list[Headline] = []
    headlines = list(getattr(snap, "headlines", None) or [])
    if not headlines:
        out.append(Headline("info", "news", "Yeni haber yok."))
        return out

    # Etiket: sentiment / sembol
    bullish = sum(1 for h in headlines if (getattr(h, "sentiment", None) or "").lower() == "bullish")
    bearish = sum(1 for h in headlines if (getattr(h, "sentiment", None) or "").lower() == "bearish")
    out.append(Headline(
        "info", "news",
        f"{len(headlines)} başlık akışta · {bullish} bullish · {bearish} bearish.",
    ))
    # En son (NewsHeadline.title field'i)
    latest = headlines[0] if headlines else None
    if latest is not None:
        src = getattr(latest, "source", "?")
        txt = (getattr(latest, "title", None) or getattr(latest, "headline", "") or "")[:90]
        out.append(Headline("info", "news", f"Son ({src}): {txt}"))
    return out


def _provider_headlines(snap) -> list[Headline]:
    out: list[Headline] = []
    ps = getattr(snap, "provider_status", None) or {}
    deg, down, dis = [], [], []
    for name, info in ps.items():
        st = (info.get("status") if isinstance(info, dict) else info) or ""
        st = str(st).lower()
        if st == "degraded":
            deg.append(name)
        elif st == "down":
            down.append(name)
        elif st == "disabled":
            dis.append(name)

    if down:
        out.append(Headline("alert", "providers", f"DOWN: {', '.join(down)}"))
    if deg:
        out.append(Headline("warn", "providers", f"Degraded: {', '.join(deg)}"))
    if dis and not down and not deg:
        out.append(Headline(
            "info", "providers",
            f"Devre dışı (config eksik): {', '.join(dis)}",
        ))
    return out


def _notification_headlines() -> list[Headline]:
    out: list[Headline] = []
    try:
        unread = list_notifications(limit=3, unread_only=True)
    except Exception:
        return out
    if not unread:
        return out
    for n in unread[:3]:
        tone_map = {"critical": "alert", "high": "warn", "medium": "info", "low": "info"}
        tone: Tone = tone_map.get(getattr(n, "priority", "low"), "info")  # type: ignore[assignment]
        title = getattr(n, "title", None) or "(başlıksız)"
        body = getattr(n, "body_short", None)
        out.append(Headline(tone, "alerts", title, body))
    return out


def build() -> dict[str, Any]:
    """Tek çağrı: tüm başlıkları üretir."""
    snap = get_cached_snapshot()
    regime = classify(snap)
    cells = _safe_cells(snap)

    sections: list[Headline] = []
    sections.extend(_market_headlines(snap, cells))
    sections.extend(_agent_headlines())
    sections.extend(_risk_headlines(snap))
    sections.extend(_event_headlines(snap))
    sections.extend(_news_headlines(snap))
    sections.extend(_provider_headlines(snap))
    sections.extend(_notification_headlines())

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "snapshot_id": getattr(snap, "id", None) or getattr(snap, "snapshot_id", None),
        "headlines": [asdict(h) for h in sections],
        "regime_label": getattr(regime, "label", None) or getattr(regime, "regime", None),
    }
