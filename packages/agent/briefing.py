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

from packages.data.ingestion.pipeline import get_cached_snapshot
from packages.data.registry import assets as asset_registry
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
        symbols = asset_registry.trade_symbols()
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
    thr = SCORE_DIRECTIONAL
    gap_dir = thr - score
    if gap_dir <= 0:
        out.append(Headline(
            "ok", "market",
            f"{sym} {tf} skor {score:.0f}/{thr:.0f} → yön eşiğini geçti.",
            f"Güçlü yön eşiğine ({SCORE_STRONG:.0f}) {SCORE_STRONG - score:+.1f} puan.",
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
    if not unread:
        return out
    for n in unread[:3]:
        tone_map = {"critical": "alert", "high": "warn", "medium": "info", "low": "info"}
        tone: Tone = tone_map.get(getattr(n, "priority", "low"), "info")  # type: ignore[assignment]
        title = getattr(n, "title", None) or "(başlıksız)"
        body = getattr(n, "body_short", None)
        out.append(Headline(tone, "alerts", title, body))
    return out


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
            imp = getattr(c, "importance", None) or getattr(c, "level", None)
            if best is None or hours < best[0]:
                best = (hours, label, imp)
        except Exception:
            continue
    return best


def _executive(snap, regime, cells, engine) -> dict[str, Any]:
    """Genel müdür → CEO brifingi: tek cümle sonuç + kısa sentez + tavsiye.

    Tamamen deterministik (LLM yok). Önceliklendirilmiş duruş (stance) belirler,
    sonra olguları patron diline çevirir. Karar VERMEZ — sadece durumu okur.
    """
    regime_label = getattr(regime, "label", None) or getattr(regime, "regime", None) or "?"
    dqs_status = snap.quality.status
    dqs_score = snap.quality.score

    # Açık pozisyon / equity
    try:
        ps = paper_state.load()
        positions = list(ps.open_positions or [])
    except Exception:
        positions = []
    if positions:
        total = sum(p.size_usd for p in positions)
        pos_clause = f"{len(positions)} açık pozisyon (${total:,.0f})"
    else:
        pos_clause = "açık pozisyon yok"

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

    # En güçlü hücre
    top = max(cells, key=lambda c: c.get("score") or 0) if cells else None
    top_score = (top.get("score") or 0) if top else 0
    gap = SCORE_DIRECTIONAL - top_score
    if top:
        sym, tf = top.get("symbol", "?"), top.get("timeframe", "?")
        if gap <= 0:
            market_clause = f"en güçlü kanaat {sym} {tf} skor {top_score:.0f}/{SCORE_DIRECTIONAL:.0f}, yön eşiğini geçti"
        else:
            market_clause = f"en güçlü aday {sym} {tf} skor {top_score:.0f}/{SCORE_DIRECTIONAL:.0f}, eşiğin {gap:.1f} puan altında"
    else:
        market_clause = "karar matrisi boş, veri bekleniyor"

    ev = _nearest_event(snap)
    if ev:
        hours, label, _imp = ev
        when = f"{hours / 24:.0f} gün sonra" if hours >= 24 else f"{hours:.0f} sa sonra"
        event_clause = f"en yakın olay {label} ({when})"
    else:
        event_clause = "takvimde yakın olay yok"

    flags: list[str] = []
    if halts:
        flags.append(f"AKTİF HALT: {len(halts)} — yalnızca owner reset kapatır")
    if engine["stale"]:
        age = engine["age_seconds"]
        when = f"son cycle {_fmt_age(age)} önce" if age is not None else "son cycle zamanı bilinmiyor"
        flags.append(f"Karar motoru taze cycle üretmiyor ({when}, durum {engine['status']})")
    if down:
        flags.append(f"Sağlayıcı DOWN: {', '.join(down)}")
    if dqs_status == "BLOCKED":
        flags.append(f"DQS BLOCKED ({dqs_score:.0f}) — doğrulanmış veri yetersiz")
    if deg:
        flags.append(f"Sağlayıcı degraded: {', '.join(deg)}")

    # ── Duruş (öncelik sırası: en kritik kazanır) ──
    if halts:
        stance, label_, tone = "halt", "İŞLEM DURDURULDU", "alert"
        headline = f"İşlem durduruldu — {len(halts)} aktif halt var, sistem yeni pozisyon açmıyor."
        narrative = (
            f"Patron, risk tarafında halt tetiklendi ve yalnızca senin manuel reset'inle açılır. "
            f"O zamana kadar motor beklemede. Rejim {regime_label}, {pos_clause}."
        )
        recommendation = "Halt sebebini risk panelinden gör; uygun bulursan owner reset ile aç, aksi halde bekle."
    elif engine["stale"]:
        stance, label_, tone = "stale", "MOTOR BAYAT", "alert"
        age = engine["age_seconds"]
        when = f"{_fmt_age(age)} önce" if age is not None else "ne zaman olduğu belirsiz bir süre önce"
        headline = (
            f"Karar motoru durdu ({when} son cycle) — masadaki pozisyon/karar rakamları artık canlı değil."
        )
        narrative = (
            f"Patron, piyasa verisi taze (DQS {dqs_score:.0f}/{dqs_status}) ama tick worker {when} cycle "
            f"kapattı ve o gün durdu. Bu süre boyunca yeni fırsatı da risk değişimini de yakalayamadık; "
            f"{market_clause} bilgisi o son cycle'a ait."
        )
        recommendation = (
            "Önce motoru ayağa kaldıralım (python -m apps.tick_worker.main); o çalışmadan işlem kararına güvenme."
        )
    elif dqs_status == "BLOCKED":
        stance, label_, tone = "blocked", "VERİ KISITI", "warn"
        headline = f"İşlem yok — DQS BLOCKED (skor {dqs_score:.0f}), doğrulanmış veri yetersiz."
        narrative = (
            f"Patron, veri kalitesi karar üretmeye yetmiyor, bu yüzden yeni pozisyon açılmıyor. "
            f"Rejim {regime_label}, {pos_clause}. Eksikler kapanınca motor tekrar aday üretir."
        )
        recommendation = "Sağlayıcı/veri eksiklerinin kapanmasını bekle; bu skorla işlem açmak körlemedir."
    elif down:
        stance, label_, tone = "data_gap", "VERİ BOŞLUĞU", "warn"
        headline = f"Veri boşluğu — {', '.join(down)} DOWN, kör nokta var."
        narrative = (
            f"Patron, bir veya birden fazla sağlayıcı çökmüş durumda. Karar hâlâ üretiliyor ama "
            f"eksik girdiyle; {market_clause}. Rejim {regime_label}, {pos_clause}."
        )
        recommendation = "Sağlayıcı sağlığı düzelene kadar yeni riske temkinli yaklaş."
    elif gap <= 0:
        stance, label_, tone = "signal", "SİNYAL VAR", "ok"
        headline = f"Yön sinyali oluştu — {market_clause}."
        narrative = (
            f"Patron, en az bir hücre yön eşiğini geçti. Rejim {regime_label}, risk temiz, {pos_clause}. "
            f"{event_clause.capitalize()}."
        )
        recommendation = "Aday RiskGate'ten geçerse paper tick'te uygulanır; Trade Ticket panelini izle."
    elif gap <= 2:
        stance, label_, tone = "watching", "İZLEMEDE", "info"
        headline = f"Fırsata yakınız — {market_clause}."
        narrative = (
            f"Patron, henüz tetik yok ama bir aday eşiğin hemen altında. Rejim {regime_label}, risk temiz, "
            f"{pos_clause}. {event_clause.capitalize()}."
        )
        recommendation = "İşlem henüz yok; aday eşiği geçerse anında haber veririm, beklemede kal."
    else:
        stance, label_, tone = "calm", "SAKİN", "info"
        headline = f"İşlem yok — yön sinyali zayıf, {market_clause}."
        narrative = (
            f"Patron, piyasa sakin: {market_clause}. Rejim {regime_label}, risk temiz, {pos_clause}. "
            f"{event_clause.capitalize()} — kısa vadede takvim baskısı düşük."
        )
        recommendation = "Beklemeye devam; güçlü bir sinyal gelmeden zorlama işlem yok."

    return {
        "stance": stance,
        "stance_label": label_,
        "tone": tone,
        "headline": headline,
        "narrative": narrative,
        "recommendation": recommendation,
        "flags": flags[:4],
    }


def build() -> dict[str, Any]:
    """Tek çağrı: yönetici özeti + önceliklendirilmiş başlıklar üretir."""
    snap = get_cached_snapshot()
    regime = classify(snap)
    cells = _safe_cells(snap)
    engine = _engine_health()

    sections: list[Headline] = []
    sections.extend(_market_headlines(snap, cells))
    sections.extend(_agent_headlines())
    sections.extend(_risk_headlines(snap))
    sections.extend(_event_headlines(snap))
    sections.extend(_news_headlines(snap))
    sections.extend(_provider_headlines(snap))
    sections.extend(_notification_headlines())

    # Genel müdür mantığı: önce sorun, sonra rutin "yolunda". Stable sort
    # kategori gruplamasını aynı tonda korur.
    sections.sort(key=lambda h: _TONE_RANK.get(h.tone, 2))

    executive = _executive(snap, regime, cells, engine)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "snapshot_id": getattr(snap, "id", None) or getattr(snap, "snapshot_id", None),
        "headlines": [asdict(h) for h in sections],
        "regime_label": getattr(regime, "label", None) or getattr(regime, "regime", None),
        "executive": executive,
        "engine": engine,
        "stale": engine["stale"],
        "dqs": {"score": snap.quality.score, "status": snap.quality.status},
    }
