"""Agent Briefing — sistem state'inden deterministik başlık listesi üretir.

LLM gerektirmez. Her başlık: tone (ok/info/warn/alert) + kategori + bir
satırlık özet + isteğe bağlı detay. UI tarafı bunu poll'lar veya SSE
tick.complete event'inde yeniler.

Karar mantığı yok — sadece "şu an state şu, kullanıcı tek bakışta görsün".
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from packages.agent.localization import localize_headline, localize_text
from packages.data.ingestion.pipeline import get_cached_snapshot
from packages.data.registry import assets as asset_registry
from packages.decision import paper_policy
from packages.decision.cockpit import finalize_matrix_view
from packages.decision.engine import matrix_view
from packages.decision.tick_artifact import decide_matrix_for
from packages.learning import event_outcomes
from packages.notifications import list_recent as list_notifications
from packages.ops import heartbeat
from packages.paper import state as paper_state
from packages.regime.classifier import classify
from packages.risk import halt as halt_store
from packages.risk.engine import risk_input_from_state

Tone = Literal["ok", "info", "warn", "alert"]


@dataclass
class Headline:
    tone: Tone
    category: str  # "market" | "agent" | "risk" | "events" | "news" | "providers" | "system"
    title: str
    detail: str | None = None


# ── Eşikler — TEK kaynak config (thresholds_v1.0.yaml); hardcode etme. ──
def _consensus_th() -> dict:
    try:
        from packages.data.registry.loader import load_thresholds

        return load_thresholds().get("consensus", {}) or {}
    except Exception:
        return {}


_TH = _consensus_th()
SCORE_DIRECTIONAL = float(_TH.get("bullish_min", 55))        # yön/open_long eşiği
SCORE_STRONG = float(_TH.get("strong_bullish_min", 65))      # güçlü yön eşiği

# Karar motoru (tick worker) bu süreden uzun süredir cycle kapatmadıysa
# "bayat" sayılır — pozisyon/karar verisi artık canlı değildir. Normal cycle
# saniyeler sürer; 5 dk fazlasıyla toleranslı bir eşik.
ENGINE_STALE_SECONDS = 300

# Başlık önceliği: genel müdür önce sorunu söyler, sonuna "her şey yolunda"yı bırakır.
_TONE_RANK: dict[str, int] = {"alert": 0, "warn": 1, "info": 2, "ok": 3}


def _fmt_age(seconds: float | None) -> str:
    """İnsan-okur yaş: 45 sn / 12 dk / 3.1 sa."""
    if seconds is None:
        return "bilinmiyor"
    if seconds < 90:
        return f"{seconds:.0f} sn"
    if seconds < 5400:
        return f"{seconds / 60:.0f} dk"
    return f"{seconds / 3600:.1f} sa"


def _engine_health() -> dict[str, Any]:
    """Karar motorunun (tick worker) canlılığı — briefing render zamanı DEĞİL.

    'Bayat' (stale) = motor TAZE CYCLE ÜRETMİYOR. Bu yalnızca YAŞ + ölü-durum
    meselesidir; veri kalitesi DEĞİL:
      * RUNNING → cycle tam şu an sürüyor (sağlıklı). completed_at henüz yok,
        started_at'tan yaş okunur.
      * OK / DEGRADED → cycle bitti; DEGRADED yalnızca veri/sağlayıcı bozuk
        demek (ayrı flag), motor yine de canlı. Yaş eskiyse bayattır.
      * FAILED / UNKNOWN / zaman damgası yok → bayat.
    """
    hb = heartbeat.load_all() or {}
    tick = hb.get("tick_worker") or {}
    status = tick.get("status") or "UNKNOWN"
    # En taze damga: cycle bittiyse completed_at, sürüyorsa started_at.
    stamp = tick.get("completed_at") or tick.get("started_at")
    age: float | None = None
    if isinstance(stamp, str):
        try:
            ts = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            age = (datetime.now(UTC) - ts).total_seconds()
        except Exception:
            age = None
    if status in ("FAILED", "UNKNOWN") or age is None:
        stale = True
    else:
        stale = age > ENGINE_STALE_SECONDS
    return {
        "status": status,
        "age_seconds": age,
        "cycle_count": tick.get("cycle_count") or 0,
        "stale": bool(stale),
    }


def _safe_cells(snap, paper_state_obj=None):
    """matrix_view cells — direction/score/timeframe/final_action içerir."""
    try:
        ps = paper_state_obj if paper_state_obj is not None else paper_state.load()
        risk_in = risk_input_from_state(ps, snap.quality.score)
        symbols = asset_registry.trade_symbols()
        regime, risk, decisions = decide_matrix_for(
            symbols,
            snap,
            risk_in,
            open_positions=ps.open_positions,
            paper_exploration=paper_policy.enabled(),
        )
        view = matrix_view(regime, risk, decisions, snap, symbols)
        view = finalize_matrix_view(view, snap, ps)
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
            f"Yön: {len(bullish)} yukarı, {len(bearish)} aşağı, {len(neutral)} nötr.",
        ))
    else:
        out.append(Headline(
            "info", "market",
            f"Piyasa nötr — {len(neutral)} hücrenin tamamı yön vermiyor.",
        ))

    actionable = _actionable_cells(cells)
    top = max(actionable or cells, key=_directional_strength)
    score = _directional_strength(top)
    sym = top.get("symbol", "?")
    tf = top.get("timeframe", "?")
    thr = SCORE_DIRECTIONAL
    gap_dir = thr - score
    if gap_dir <= 0 and actionable:
        out.append(Headline(
            "ok", "market",
            f"{sym} {tf} skor {score:.0f}/{thr:.0f} → yön eşiğini geçti.",
            f"Güçlü yön eşiğine ({SCORE_STRONG:.0f}) {SCORE_STRONG - score:+.1f} puan.",
        ))
    elif gap_dir <= 0:
        out.append(Headline(
            "info", "market",
            f"{sym} {tf} adayı {score:.0f}/{thr:.0f} ile eşiği geçti; son karar yeni girişe açık değil.",
            str(top.get("reason") or "Risk/veri kapıları yeniden kontrol ediliyor."),
        ))
    elif gap_dir <= 2:
        out.append(Headline(
            "info", "market",
            f"En yakın: {sym} {tf} skor {score:.1f}/{thr:.0f} — yön eşiğine {gap_dir:.1f} puan.",
        ))
    else:
        out.append(Headline(
            "info", "market",
            f"En yüksek: {sym} {tf} = {score:.1f}/{thr:.0f}. Yön sinyali zayıf.",
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


_HORIZON_TR = {"15m": "15dk", "1h": "1sa", "4h": "4sa", "1d": "1g"}


def _release_headlines() -> list[Headline]:
    """Son 24 saatte açıklanan takvim olayı: sonuç + beklenen yönde tutan oran."""
    try:
        recent = event_outcomes.compact_for_chat(hours=24)["recent_releases"]
    except Exception:
        return []
    out: list[Headline] = []
    for rec in recent[:1]:
        parts = [
            f"{_HORIZON_TR.get(h, h)} {v['in_expected_direction']}"
            for h, v in rec["reaction"].items()
            if not str(v["in_expected_direction"]).endswith("/0")
        ]
        detail = ("Beklenen yönde: " + " · ".join(parts)) if parts else "Tepki ölçümü sürüyor."
        out.append(Headline(
            "info", "events",
            f"Açıklandı: {rec['title']} → {rec['outcome'] or 'sonuç henüz belirsiz'}.",
            detail,
        ))
    return out


def _event_headlines(snap) -> list[Headline]:
    out: list[Headline] = _release_headlines()
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
            upcoming.append((hours, getattr(c, "title", None) or getattr(c, "label", None) or getattr(c, "id", "?"),
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
        f"{len(headlines)} başlık akışta · {bullish} yukarı · {bearish} aşağı.",
    ))
    # En son (NewsHeadline.title field'i)
    latest = headlines[0] if headlines else None
    if latest is not None:
        src = getattr(latest, "source", "?")
        txt = localize_headline(latest)[:120]
        out.append(Headline("info", "news", f"Son ({src}): {txt}"))
    return out


def _intel_headlines(cells) -> list[Headline]:
    """Haber istihbaratı (owner kararı 2026-10-05): inceleme tavsiyeleri + canlı aday ile
    çelişen güçlü haber öngörüsü. Kanıttır; karar değişmez (haber girdisi gölge)."""
    out: list[Headline] = []
    try:
        from packages.discovery import ideas, news_decision_shadow, news_forecast

        for r in ideas.review_recommendations()[:2]:
            out.append(Headline(
                "info", "news",
                f"İnceleme tavsiyesi: {r['symbol']} ({r['name']}) — haber zinciri + teknik sinyal.",
                f"{r['chain']} · {r['technical']} · YZ {r['ai_verdict'] or '—'}. İşlem önerisi değildir.",
            ))
        cfg = news_decision_shadow.config()
        conflicts = [c for c in news_decision_shadow.checks(cells, news_forecast.load_forecasts(),
                                                            cfg["min_strength"])
                     if c["relation"] == "conflict" and c["strength"] >= 40]
        for c in conflicts[:1]:
            arrow = "↑" if c["forecast"] == "up" else "↓"
            out.append(Headline(
                "warn", "news",
                f"Haber öngörüsü {_symbol_tr(c['symbol'])} {_tf_tr(c['timeframe'])} "
                f"{'alış' if c['side'] == 'long' else 'satış'} adayıyla çelişiyor ({arrow}, güç {c['strength']}).",
                f"{localize_text((c.get('evidence') or '')[:100])} — gölge ölçüm; karar değişmedi.",
            ))
    except Exception:  # brifing asla düşmesin
        return []
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


# Alert headline'ları yalnızca SON cycle'lara ait olmalı; aksi halde okunmamış
# bayat bildirimler (ör. mock dönemi kalıntısı) sonsuza dek "taze" gibi görünür.
_ALERT_FRESHNESS_SECONDS = 1800  # 30 dk


def _notification_headlines() -> list[Headline]:
    out: list[Headline] = []
    try:
        unread = list_notifications(
            limit=3, unread_only=True, max_age_seconds=_ALERT_FRESHNESS_SECONDS
        )
    except Exception:
        return out
    # İnceleme tavsiyeleri _intel_headlines'ta zincir + teknikle ayrıntılı; burada tekrar edilmez.
    # Operasyon alarmları zilde kalır; yönetici özetindeki işlem uyarılarını itmesin.
    unread = [n for n in unread if getattr(n, "type", None) not in {"review_recommendation", "ops_alert"}]
    if not unread:
        return out
    for n in unread[:3]:
        tone_map = {"critical": "alert", "high": "warn", "medium": "info", "low": "info"}
        tone: Tone = tone_map.get(getattr(n, "priority", "low"), "info")  # type: ignore[assignment]
        title = getattr(n, "title", None) or "(başlıksız)"
        body = getattr(n, "body_short", None)
        out.append(Headline(tone, "alerts", title, body))
    return out


# ── Patron dili: kod/jargon yerine günlük Türkçe (yönetici özeti sesli okunur) ──
_REGIME_TR = {"OFFENSIVE": "atak", "NEUTRAL": "nötr", "DEFENSIVE": "savunmacı", "CRISIS": "kriz"}
_SYMBOL_TR = {
    "BTCUSD": "Bitcoin",
    "ETHUSD": "Ethereum",
    "XAUUSD": "Altın",
    "XAGUSD": "Gümüş",
    "DXY": "dolar endeksi",
    "CPI": "enflasyon verisi",
}
_TF_TR = {
    "15m": "15 dakikalık grafik", "1h": "1 saatlik grafik", "4h": "4 saatlik grafik",
    "1d": "günlük grafik", "1w": "haftalık grafik",
}
_DIRECTION_TR = {"bullish": "alış (yukarı)", "bearish": "satış (aşağı)", "neutral": "henüz yönsüz"}

# Dünya özeti yalnızca haber akışında gerçekten görünen aktörleri kullanır.
# Bu liste bir jeopolitik iddia üretmez; başlık/evidence metnindeki isimleri
# okunur hale getirir. Eşleşme yoksa aktör adı uydurulmaz.
_ACTOR_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Trump / ABD", ("trump", "donald trump", "white house", "washington", "abd", "u.s.")),
    ("Çin", ("china", "çin", "chinese", "pekin", "beijing", "pboc")),
    ("Rusya", ("russia", "rusya", "russian", "moscow", "moskova")),
    ("İran", ("iran", "iranian", "tehran", "tahran")),
    ("İsrail", ("israel", "israil", "israeli", "tel aviv")),
    ("Türkiye", ("turkey", "türkiye", "turkish", "ankara")),
)

_WORLD_CHANNEL_TR = {
    "energy_supply_risk": "enerji arzı/petrol",
    "energy_infrastructure_attack": "enerji altyapısı",
    "shipping_risk": "deniz taşımacılığı ve navlun",
    "trade_risk": "ticaret ve tedarik zinciri",
    "sanctions_pressure": "yaptırım ve finans akışı",
    "risk_aversion": "risk iştahı ve güvenli limanlar",
}
_WORLD_EVENT_TR = {
    "CHOKEPOINT_THREAT": "boğaz/koridor tehdidi",
    "CHOKEPOINT_DISRUPTION": "boğaz/koridor kesintisi",
    "SHIPPING_ATTACK": "gemi saldırısı",
    "PORT_DISRUPTION": "liman kesintisi",
    "SANCTIONS": "yaptırım",
    "TRADE_RESTRICTION": "ticaret kısıtlaması",
    "AIRSTRIKE": "hava saldırısı",
    "MISSILE_ATTACK": "füze saldırısı",
    "DRONE_ATTACK": "İHA saldırısı",
    "GROUND_OFFENSIVE": "kara harekâtı",
    "MILITARY_ESCALATION": "askeri tırmanma",
    "MILITARY_DEESCALATION": "askeri gerilim azalması",
    "CEASEFIRE": "ateşkes",
    "PEACE_TALKS": "barış görüşmesi",
    "NUCLEAR_ESCALATION": "nükleer tırmanma",
}


def _regime_tr(label: str | None) -> str:
    return _REGIME_TR.get(str(label or "").upper(), str(label or "belirsiz").lower())


def _symbol_tr(symbol: str | None) -> str:
    sym = str(symbol or "?")
    return _SYMBOL_TR.get(sym, sym)


def _tf_tr(tf: str | None) -> str:
    return _TF_TR.get(str(tf or ""), str(tf or "?"))


def _usd_tr(value: float) -> str:
    """10538.4 → '10.538 dolar' (Türkçe binlik ayraç, sesli okunur)."""
    return f"{value:,.0f}".replace(",", ".") + " dolar"


def _side_tr(side: str | None) -> str:
    return {"long": "alış", "short": "satış"}.get(str(side or "").lower(), "?")


def _position_clause(positions: list[Any], rechecks: list[dict] | None = None) -> str:
    """Açık pozisyonları brief'e bağlayan kısa, karar-dışı durum özeti.

    Brief daha önce yalnızca toplam pozisyon sayısını söylüyordu. Bu, aynı anda
    ekranda görünen açık pozisyonlarla hangi sinyalin ilişkili olduğunun
    anlaşılmasını engelliyordu. Buradaki verdict yalnızca son recheck gözlemidir;
    otomatik kapatma veya yeni emir üretmez.
    """
    if not positions:
        return "masada açık pozisyon yok"

    checks = {
        str(item.get("position_id")): item
        for item in (rechecks or ())
        if isinstance(item, dict) and item.get("position_id")
    }
    details: list[str] = []
    for position in positions[:4]:
        verdict = (checks.get(str(getattr(position, "id", ""))) or {}).get("verdict")
        verdict_text = {
            "WATCH": "izlemede",
            "HOLD": "beklemede",
            "CLOSE": "kapatma sinyali",
            "REDUCE": "azaltma sinyali",
        }.get(str(verdict or "").upper(), "izlemede")
        try:
            pnl = float(position.unrealized_pnl_usd)
            pnl_text = f"{pnl:+.2f} dolar"
        except (AttributeError, TypeError, ValueError):
            pnl_text = "PnL bekleniyor"
        details.append(
            f"{_symbol_tr(getattr(position, 'symbol', None))} "
            f"{_side_tr(getattr(position, 'side', None))} "
            f"{_tf_tr(getattr(position, 'timeframe', None))} "
            f"({pnl_text}, {verdict_text})"
        )
    suffix = f"; ayrıca {len(positions) - 4} pozisyon daha" if len(positions) > 4 else ""
    return f"açıklar: {' · '.join(details)}{suffix}"


def _actionable_cells(cells: list[dict]) -> list[dict]:
    """Yalnızca final kararı gerçekten girişe açık hücreleri seçer.

    Score eşiğini aşan ama concentration/EV/entry-quality/data kapılarıyla
    kısıtlanan bir aday brief'te "işlem sinyali" diye anlatılmamalıdır.
    """
    return [
        cell
        for cell in cells
        if bool(cell.get("actionable"))
        # Older snapshots do not carry the additive field; their existing
        # actionable contract remains compatible.  Live matrix cells always
        # include it, so exploration/negative-EV cells are excluded there.
        and bool(cell.get("execution_ready", True))
        and cell.get("action") in {"open_long", "open_short"}
        and cell.get("paper_action") in {"open_long", "open_short"}
    ]


def _directional_strength(cell: dict) -> float:
    """Normalize bullish and bearish scores to the same 0–100 strength.

    Consensus stores a directional score (50 is neutral): a bearish score of
    35 is a 65-point short signal, not a weak 35-point signal.  The old brief
    compared the raw score to the bullish threshold, so a valid short and its
    chat/ticket surfaces described different states.
    """
    canonical = cell.get("directional_strength")
    if canonical is not None:
        try:
            return max(0.0, min(100.0, float(canonical)))
        except (TypeError, ValueError):
            pass
    try:
        score = max(0.0, min(100.0, float(cell.get("score") or 0.0)))
    except (TypeError, ValueError):
        return 0.0
    direction = str(cell.get("direction") or "").casefold()
    action = str(cell.get("action") or "").casefold()
    if direction in {"bearish", "down"} or action == "open_short":
        return 100.0 - score
    return score


def _position_public_row(position: Any) -> dict[str, Any]:
    """Brief sözleşmesi için güvenli, hesap yapmayan pozisyon satırı."""
    try:
        pnl = round(float(position.unrealized_pnl_usd), 2)
    except (AttributeError, TypeError, ValueError):
        pnl = None
    return {
        "id": getattr(position, "id", None),
        "symbol": getattr(position, "symbol", None),
        "side": getattr(position, "side", None),
        "timeframe": getattr(position, "timeframe", None),
        "size_usd": getattr(position, "size_usd", None),
        "unrealized_pnl_usd": pnl,
    }


def _nearest_event(snap):
    """En yakın gelecek olay (saat cinsinden, label) — yoksa None."""
    now = datetime.now(UTC)
    best = None
    for c in list(getattr(snap, "catalysts", None) or []):
        ts = getattr(c, "scheduled_at", None) or getattr(c, "ts", None)
        if not ts:
            continue
        try:
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            hours = (ts - now).total_seconds() / 3600
            if hours < -1:
                continue
            label = getattr(c, "title", None) or getattr(c, "label", None) or getattr(c, "id", "?")
            label = localize_text(label)
            imp = getattr(c, "importance", None) or getattr(c, "level", None)
            if best is None or hours < best[0]:
                best = (hours, label, imp)
        except Exception:
            continue
    return best


def _as_utc(value: Any) -> datetime | None:
    """Başlık zamanını karşılaştırılabilir UTC datetime'a çevirir."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _brief_news_rows(snap, limit: int = 3) -> list[Any]:
    """Son 24 saatin başlıklarını tarihe göre seç; tarih yoksa en yeniyi kullan."""
    rows = [item for item in (getattr(snap, "headlines", None) or ())
            if str(getattr(item, "title_tr", None) or getattr(item, "title", None) or "").strip()]
    rows.sort(key=lambda item: _as_utc(getattr(item, "ts", None)) or datetime.min.replace(tzinfo=UTC), reverse=True)
    now = datetime.now(UTC)
    recent = [item for item in rows if (stamp := _as_utc(getattr(item, "ts", None)))
              and now - timedelta(hours=24) <= stamp <= now + timedelta(minutes=5)]
    selected = recent or rows
    unique: list[Any] = []
    seen: set[str] = set()
    for item in selected:
        text = " ".join(str(getattr(item, key, None) or "") for key in ("title_tr", "title")).strip()
        key = " ".join(text.casefold().split())
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
        if len(unique) >= limit:
            break
    return unique


def _clean_text(value: Any, limit: int = 180) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _sentence_start(value: str) -> str:
    """Cümle başını büyütür; Türkçe metnin kalanını lower'a dönüştürmez."""
    text = str(value or "")
    return text[:1].upper() + text[1:] if text else text


def _headline_world_context(snap, world_state: Any | None, idea_context: Any | None = None) -> str:
    """Layer-0'a günlük haber → etki → fikir zincirini ekler.

    Bu fonksiyon gözlem metni üretir; sinyal, pozisyon, boyut veya emir üretmez.
    Kanıt yoksa açıkça "doğrulanmadı" der ve tahmin uydurmaz.
    """
    rows = _brief_news_rows(snap)
    if rows:
        bits = []
        for item in rows:
            title = _clean_text(localize_headline(item), 150)
            source = _clean_text(getattr(item, "source", None) or "kaynak bilinmiyor", 32)
            bits.append(f"{source}: {title}")
        news_clause = "Bugünün gündemi: " + " | ".join(bits) + "."
    else:
        news_clause = "Bugünün gündemi: doğrulanmış yeni haber alınamadı."

    if world_state is None:
        return f"{news_clause} Haber→piyasa etkisi henüz hesaplanamadı; fikir yalnızca izleme düzeyinde."

    events = [event for event in (getattr(world_state, "geopolitical_events", None) or ())
              if not bool(getattr(event, "expired", False))]
    channels: list[str] = []
    for event in events:
        for channel in (getattr(event, "channels", None) or ()):
            if channel not in channels and channel in _WORLD_CHANNEL_TR:
                channels.append(channel)

    impact_parts: list[str] = []
    # Haber sağlayıcısının varlık eşlemesi, gerçekleşmiş getiriyi değil,
    # haberin hangi varlıkta hangi yönde baskı beklediğini gösterir.
    asset_impacts: dict[str, float] = {}
    for item in _brief_news_rows(snap, limit=20):
        for symbol, raw_value in (getattr(item, "asset_impact", None) or {}).items():
            try:
                asset_impacts[str(symbol).upper()] = asset_impacts.get(str(symbol).upper(), 0.0) + float(raw_value or 0.0)
            except (TypeError, ValueError):
                continue
    for symbol, value in sorted(asset_impacts.items(), key=lambda pair: abs(pair[1]), reverse=True)[:4]:
        if abs(value) >= 0.15:
            impact_parts.append(f"{_symbol_tr(symbol)} üzerinde {'yukarı' if value > 0 else 'aşağı'} haber baskısı")
    pressure_fields = (
        ("energy_supply_risk", "enerji arzı/petrol"),
        ("shipping_risk", "taşımacılık/navlun"),
        ("sanctions_pressure", "yaptırım/finans"),
        ("trade_risk", "ticaret/tedarik"),
        ("risk_aversion", "riskten kaçış"),
    )
    for field, label in pressure_fields:
        value = getattr(world_state, field, None)
        try:
            numeric = float(value) if value is not None else None
        except (TypeError, ValueError):
            numeric = None
        if numeric is not None and abs(numeric) >= 0.15:
            impact_parts.append(f"{label} baskısı {'artıyor' if numeric > 0 else 'azalıyor'} ({abs(numeric) * 100:.0f}/100)")
    if not impact_parts and channels:
        impact_parts = [_WORLD_CHANNEL_TR[channel] + " kanalı izleniyor" for channel in channels[:3]]
    if impact_parts:
        impact_clause = "Piyasa etkisi: " + ", ".join(impact_parts) + "."
    else:
        impact_clause = "Piyasa etkisi: haberler henüz doğrulanmış bir fiyat kanalı oluşturmuyor; etki teyidi sürüyor."

    actors: list[str] = []
    searchable = " ".join(
        _clean_text(getattr(item, "title", None), 240) + " " + _clean_text(getattr(item, "title_tr", None), 240)
        for item in _brief_news_rows(snap, limit=20)
    ).casefold()
    for event in events:
        searchable += " " + " ".join(str(actor) for actor in (getattr(event, "actors", None) or ())).casefold()
    statement_parts: list[str] = []
    for statement in (getattr(world_state, "statements", None) or ()):
        name = getattr(statement, "speaker", None) or getattr(statement, "institution", None)
        if name and str(name).casefold() not in {"government", "unknown", "none"}:
            name_text = str(name)
            display_name = localize_text(name_text)
            if display_name not in actors:
                actors.append(display_name)
            direction = {
                "tightening": "sıkılaştırma",
                "easing": "gevşeme",
                "unknown": "yön belirsiz",
            }.get(str(getattr(statement, "policy_direction", None) or "unknown"), "yön belirsiz")
            evidence = next(iter(getattr(statement, "evidence", None) or ()), None)
            statement_parts.append(
                f"{display_name} — {direction}"
                + (f" ({_clean_text(localize_text(evidence), 100)})" if evidence else "")
            )
    for label, aliases in _ACTOR_ALIASES:
        if any(alias in searchable for alias in aliases) and label not in actors:
            actors.append(label)
    actor_events = []
    for event in events[:3]:
        event_type = _WORLD_EVENT_TR.get(str(getattr(event, "event_type", "")), "jeopolitik gelişme")
        event_actors = ", ".join(
            localize_text(str(actor)) for actor in (getattr(event, "actors", None) or ())
        )
        if event_actors:
            actor_events.append(f"{event_actors}: {event_type}")
    if statement_parts or actor_events:
        details = statement_parts[:3] + actor_events[:3]
        actor_clause = "Aktör açıklamaları/olaylar: " + " | ".join(details) + "."
    elif actors:
        actor_clause = "Başlıklarda geçen aktörler: " + ", ".join(actors[:6]) + "; resmi açıklama ayrıntısı sınırlı."
    else:
        actor_clause = "Aktör açıklaması: bugünkü akışta yapılandırılmış resmi açıklama bulunamadı."

    discovery = getattr(world_state, "asset_discovery", None) or {}
    candidates = discovery.get("candidates") if isinstance(discovery, dict) else None
    candidate_symbols = [str(item.get("symbol")).upper() for item in (candidates or ())
                         if isinstance(item, dict) and item.get("symbol")][:3]
    if candidate_symbols:
        idea_clause = ("Fikir kıvılcımı: haber kanalıyla ilişkili " + ", ".join(candidate_symbols) +
                       " izleme listesine alındı; fiyat/teknik teyit olmadan işlem açılmaz.")
    elif channels:
        idea_clause = ("Fikir kıvılcımı: " + ", ".join(_WORLD_CHANNEL_TR[channel] for channel in channels[:2]) +
                       " tarafında aday aranabilir; fiyat teyidi olmadan işlem açılmaz.")
    else:
        idea_clause = "Fikir kıvılcımı: doğrulanmış etki yok; yeni pozisyon fikri üretmek için veri bekleniyor."

    # Heart fikir panosu ile Brain anlatısının aynı gözlem kanıtını kullandığını
    # görünür kıl. Bu yalnızca anlatıdır; fikirler karar/emir üretmez.
    board_ideas = (idea_context or {}).get("ideas") if isinstance(idea_context, dict) else None
    board_bits: list[str] = []
    for idea in list(board_ideas or [])[:3]:
        news = idea.get("news") or {}
        direction = news.get("direction")
        if direction not in {"up", "down", "neutral"}:
            continue
        symbol = str(idea.get("symbol") or "").upper()
        if not symbol:
            continue
        direction_tr = {"up": "yukarı", "down": "aşağı", "neutral": "nötr"}[direction]
        families = news.get("independent_source_families")
        stories = news.get("n_stories")
        status = str(news.get("evidence_status") or "").upper()
        evidence = f"{families} bağımsız kaynak ailesi" if families is not None else "haber kanıtı"
        if stories is not None:
            evidence += f", {stories} öykü"
        if status == "CONFLICT" or news.get("conflict"):
            evidence += ", yön çelişkili"
        board_bits.append(f"{symbol} {direction_tr} ({evidence})")
    if board_bits:
        idea_clause += " Brain-Heart ortak fikir kanıtı: " + " | ".join(board_bits) + "."
    return " ".join((news_clause, impact_clause, actor_clause, idea_clause))


def _safe_world_state(snap):
    """Dünya-state hesaplaması hata verse bile eski briefing akışı çalışır."""
    try:
        from packages.world_state.engine import build as build_world_state

        return build_world_state(snap)
    except Exception:
        return None


def _executive(
    snap,
    regime,
    cells,
    engine,
    world_state=None,
    paper_state_obj=None,
    idea_context=None,
) -> dict[str, Any]:
    """Genel müdür → CEO brifingi: tek cümle sonuç + kısa sentez + tavsiye.

    Tamamen deterministik (LLM yok). Önceliklendirilmiş duruş (stance) belirler,
    sonra olguları patron diline çevirir. Karar VERMEZ — sadece durumu okur.
    """
    regime_label = getattr(regime, "label", None) or getattr(regime, "regime", None) or "?"
    regime_clause = f"piyasanın genel modu {_regime_tr(regime_label)}"
    dqs_status = snap.quality.status
    dqs_score = snap.quality.score

    # Açık pozisyon / equity
    try:
        ps = paper_state_obj if paper_state_obj is not None else paper_state.load()
        positions = list(ps.open_positions or [])
    except Exception:
        ps = None
        positions = []
    if positions:
        total = sum(p.size_usd for p in positions)
        pos_clause = (
            f"masada {len(positions)} açık pozisyon var (toplam {_usd_tr(total)}); "
            f"{_position_clause(positions, getattr(ps, 'last_rechecks', None))}"
        )
    else:
        pos_clause = "masada açık pozisyon yok"

    # Aktif halt
    try:
        halts = halt_store.active_halts() or []
    except Exception:
        halts = []

    # Sağlayıcı sorunları
    down, deg = [], []
    for name, info in (getattr(snap, "provider_status", None) or {}).items():
        st = str((info.get("status") if isinstance(info, dict) else info) or "").lower()
        if st == "down":
            down.append(name)
        elif st == "degraded":
            deg.append(name)

    # Score eşiğini aşan her hücre işlem sinyali değildir. Decision matrix'in
    # ardından tick worker'ın uyguladığı haber-teknik kapısı da aynı read modelde
    # görünür olmalı; aksi halde brief sinyal derken defter boş kalır.
    from packages.decision.cockpit import _auto_open_readiness

    auto_open = _auto_open_readiness(cells, snap, ps)
    actionable = _actionable_cells(cells)
    if auto_open["enabled"] and auto_open["available"]:
        ready_keys = {
            (row["symbol"], row["timeframe"], row["side"])
            for row in auto_open["ready"]
        }
        actionable = [
            cell
            for cell in actionable
            if (
                cell.get("symbol"),
                cell.get("timeframe"),
                "long" if cell.get("action") == "open_long" else "short",
            ) in ready_keys
        ]
    top_actionable = max(actionable, key=_directional_strength) if actionable else None
    top = top_actionable or (max(cells, key=_directional_strength) if cells else None)
    top_score = _directional_strength(top) if top else 0.0
    gap = SCORE_DIRECTIONAL - top_score
    if top:
        sym_txt = _symbol_tr(top.get("symbol"))
        tf_txt = _tf_tr(top.get("timeframe"))
        dir_txt = _DIRECTION_TR.get(str(top.get("direction") or ""), "yukarı")
        if gap <= 0 and top_actionable:
            market_clause = (
                f"en güçlü sinyal {sym_txt} tarafında: {tf_txt}, {dir_txt} yönü; sinyal gücü "
                f"{top_score:.0f} puan ve işlem için aradığımız alt sınır ({SCORE_DIRECTIONAL:.0f} puan) aşıldı"
            )
        elif gap <= 0:
            market_clause = (
                f"en güçlü aday {sym_txt} tarafında: {tf_txt}, {dir_txt} yönü; skor "
                f"{top_score:.0f} puanla eşiği aşsa da son karar yeni girişe açık değil"
            )
        else:
            market_clause = (
                f"en güçlü aday {sym_txt} tarafında: {tf_txt}; sinyal gücü {top_score:.0f} puan, "
                f"işlem sınırı {SCORE_DIRECTIONAL:.0f} puan, yani {gap:.1f} puan eksik"
            )
    else:
        market_clause = "karar tablosu şu an boş, sistem veri bekliyor"

    ev = _nearest_event(snap)
    if ev:
        hours, label, _imp = ev
        when = f"{hours / 24:.0f} gün sonra" if hours >= 24 else f"{hours:.0f} saat sonra"
        event_clause = f"takvimdeki en yakın önemli olay {localize_text(label)}, {when}"
    else:
        event_clause = "takvimde yakın zamanda piyasayı oynatacak bir olay görünmüyor"

    flags: list[str] = []
    if halts:
        flags.append(f"Acil durdurma devrede ({len(halts)} adet) — yalnızca elle kaldırılır")
    if engine["stale"]:
        age = engine["age_seconds"]
        when = f"son tur {_fmt_age(age)} önce" if age is not None else "son tur zamanı bilinmiyor"
        flags.append(f"Karar motoru yeni tur üretmiyor ({when}, durum {engine['status']})")
    if down:
        flags.append(f"Veri kaynağı çevrimdışı: {', '.join(down)}")
    if dqs_status == "BLOCKED":
        flags.append(f"Veri kalitesi engelli (puan {dqs_score:.0f}) — doğrulanmış veri yetersiz")
    if deg:
        flags.append(f"Veri kaynağı zayıf çalışıyor: {', '.join(deg)}")

    restrictive = {
        str(blocker)
        for cell in cells
        for blocker in (cell.get("blocked_by") or [])
        if any(
            token in str(blocker)
            for token in ("concentration", "NO_POSITION_INCREASE", "RISK_REDUCE")
        )
    }
    risk_clause = (
        "risk kapısı açık; ancak açık pozisyon/yoğunlaşma kısıtları izleniyor"
        if restrictive
        else "risk tarafında engel yok"
    )

    # ── Duruş (öncelik sırası: en kritik kazanır) ──
    if halts:
        stance, label_, tone = "halt", "İŞLEM DURDURULDU", "alert"
        headline = f"İşlemler güvenlik nedeniyle durduruldu — {len(halts)} acil durdurma devrede."
        narrative = (
            f"Risk tarafında acil durdurma tetiklendi; sistem yeni pozisyon açmıyor ve bu kilidi "
            f"yalnızca sen elle kaldırabilirsin. {_sentence_start(pos_clause)}; mevcut pozisyonlar "
            f"yönetilmeye devam ediyor. {_sentence_start(regime_clause)}."
        )
        recommendation = (
            "Durdurmanın sebebini risk panelinden incele; uygun görürsen kilidi elle kaldır, "
            "aksi halde beklemek en güvenlisi."
        )
    elif engine["stale"]:
        stance, label_, tone = "stale", "MOTOR BAYAT", "alert"
        age = engine["age_seconds"]
        when = f"{_fmt_age(age)} önce" if age is not None else "ne zaman olduğu belirsiz bir süre önce"
        headline = (
            f"Karar motoru durdu (son tur {when}) — ekrandaki pozisyon ve sinyal rakamları artık güncel değil."
        )
        narrative = (
            f"Piyasa verisi akmaya devam ediyor ama kararları üreten motor son turunu {when} kapattı "
            f"ve o zamandan beri yeni tur açmadı. Bu süre boyunca ne yeni fırsat yakalanabildi ne de "
            f"risk değişimi izlenebildi; ekranda gördüğün her rakam o son tura ait."
        )
        recommendation = (
            "Önce motoru yeniden başlatmak gerekiyor (python -m apps.tick_worker.main); "
            "o çalışmadan ekrandaki hiçbir işlem kararına güvenme."
        )
    elif dqs_status == "BLOCKED":
        stance, label_, tone = "blocked", "VERİ KISITI", "warn"
        headline = (
            f"Yeni işlem yok — veri kalitesi puanı {dqs_score:.0f} ile yetersiz, sistem kendini korumaya aldı."
        )
        narrative = (
            f"Gelen piyasa verisi doğrulanamadığı için sistem bilerek yeni pozisyon açmıyor; "
            f"eksik veriyle işlem açmak körleme olurdu. {_sentence_start(pos_clause)}. "
            f"Veri düzelince adaylar otomatik olarak yeniden üretilir."
        )
        recommendation = "Veri kaynaklarının düzelmesini bekle; bu tabloda işlem zorlamak risklidir."
    elif down:
        stance, label_, tone = "data_gap", "VERİ BOŞLUĞU", "warn"
        headline = f"Veri boşluğu var — şu kaynaklar yanıt vermiyor: {', '.join(down)}."
        narrative = (
            f"Bir veya birden fazla veri kaynağı çevrimdışı; sistem karar üretmeye devam ediyor ama "
            f"kör noktası var. Şu an {market_clause}. {_sentence_start(regime_clause)}; {pos_clause}."
        )
        recommendation = "Veri kaynakları düzelene kadar yeni pozisyonlara temkinli yaklaşmak doğru olur."
    elif (
        auto_open["enabled"]
        and auto_open["available"]
        and auto_open["blocked_count"]
        and not top_actionable
        and _actionable_cells(cells)
    ):
        stance, label_, tone = "watching", "HABER-TEKNİK TEYİT BEKLENİYOR", "info"
        headline = f"Sinyal var ama işlem açılmadı — {market_clause}."
        narrative = (
            f"{_sentence_start(regime_clause)}, {risk_clause}; {pos_clause}. "
            "Karar matrisi teknik olarak aday gösterdi, fakat otomatik kâğıt açılışının "
            "son kapısı olan aynı varlık, zaman dilimi ve yönde canlı ARMED haber-teknik "
            "kurulumu bulunmadı. Bu yüzden sinyal yalnızca izlemeye alındı. "
            f"{_sentence_start(event_clause)}."
        )
        recommendation = (
            "Haber yönü ile teknik teyit aynı kuruluma bağlandığında kâğıt pozisyonu "
            "otomatik olarak yeniden değerlendirilir; mevcut durumda emir açılmadı."
        )
    elif gap <= 0 and top_actionable:
        stance, label_, tone = "signal", "SİNYAL VAR", "ok"
        headline = f"İşlem sinyali oluştu — {market_clause}."
        narrative = (
            f"{_sentence_start(regime_clause)}, {risk_clause}; {pos_clause}. "
            f"{_sentence_start(event_clause)}."
        )
        recommendation = (
            "Sinyal risk kontrolünden geçecek; yalnızca simülasyon modunda uygun bulunursa "
            "kâğıt üzerinde pozisyon açılır. Gerçek broker emri gönderilmez."
        )
    elif gap <= 2:
        stance, label_, tone = "watching", "İZLEMEDE", "info"
        headline = f"Fırsata yaklaşıyoruz — {market_clause}."
        watch_reason = (
            "Aday skor eşiğini geçmiş olsa da son karar yeni girişe açık değil."
            if gap <= 0
            else "Henüz işlem açacak güçte bir sinyal yok ama bir aday sınırın hemen altında."
        )
        narrative = (
            f"{watch_reason} "
            f"{_sentence_start(regime_clause)}, {risk_clause}; {pos_clause}. {_sentence_start(event_clause)}."
        )
        recommendation = "Şu an yapılacak bir şey yok; aday sınırı geçerse anında haber veririm."
    else:
        stance, label_, tone = "calm", "SAKİN", "info"
        headline = "Piyasa sakin — işlem açacak güçte bir sinyal yok."
        narrative = (
            f"Şu an {market_clause}. {_sentence_start(regime_clause)}, {risk_clause}; {pos_clause}. "
            f"{_sentence_start(event_clause)}."
        )
        recommendation = "Beklemek en doğrusu; sistem güçlü bir sinyal görmeden işlem zorlamaz."

    # Dünya özeti her duruşta gösterilir; yalnızca haber/world-state kanıtıdır.
    # Böylece statik "Piyasa sakin" cümlesi günün akışını gizleyemez.
    narrative = f"{narrative} {_headline_world_context(snap, world_state, idea_context)}"

    return {
        "stance": stance,
        "stance_label": label_,
        "tone": tone,
        "headline": headline,
        "narrative": narrative,
        "recommendation": recommendation,
        "flags": flags[:4],
    }


def build_executive(
    snap,
    regime,
    cells,
    engine,
    world_state=None,
    paper_state_obj=None,
    idea_context=None,
) -> dict[str, Any]:
    """Cockpit'in aynı snapshot'ından yönetici metnini üretir.

    HTTP katmanları bu public wrapper'ı kullanır; böylece Layer-0 metni ayrı
    bir karar/snapshot okumasıyla ekrandaki Cockpit özetinden kopmaz.
    """
    return _executive(
        snap,
        regime,
        cells,
        engine,
        world_state,
        paper_state_obj=paper_state_obj,
        idea_context=idea_context,
    )


def build() -> dict[str, Any]:
    """Tek çağrı: yönetici özeti + önceliklendirilmiş başlıklar üretir."""
    snap = get_cached_snapshot()
    try:
        ps = paper_state.load()
    except Exception:
        # Briefing gözlem katmanıdır; state okunamadığında eski güvenli
        # fallback'ler çalışmaya devam eder, yeni karar/emir üretilmez.
        ps = None
    regime = classify(snap)
    cells = _safe_cells(snap, paper_state_obj=ps)
    engine = _engine_health()
    world_state = _safe_world_state(snap)

    sections: list[Headline] = []
    sections.extend(_market_headlines(snap, cells))
    sections.extend(_agent_headlines())
    sections.extend(_risk_headlines(snap))
    sections.extend(_event_headlines(snap))
    sections.extend(_news_headlines(snap))
    sections.extend(_intel_headlines(cells))
    sections.extend(_provider_headlines(snap))
    sections.extend(_notification_headlines())

    # Genel müdür mantığı: önce sorun, sonra rutin "yolunda". Stable sort
    # kategori gruplamasını aynı tonda korur.
    sections.sort(key=lambda h: _TONE_RANK.get(h.tone, 2))

    executive = _executive(snap, regime, cells, engine, world_state, paper_state_obj=ps)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "snapshot_id": getattr(snap, "id", None) or getattr(snap, "snapshot_id", None),
        "headlines": [asdict(h) for h in sections],
        "regime_label": getattr(regime, "label", None) or getattr(regime, "regime", None),
        "executive": executive,
        "engine": engine,
        "stale": engine["stale"],
        "dqs": {"score": snap.quality.score, "status": snap.quality.status},
        "paper_state_revision": getattr(ps, "revision", None),
        "open_positions": [
            _position_public_row(position)
            for position in list(getattr(ps, "open_positions", None) or [])
        ],
    }
