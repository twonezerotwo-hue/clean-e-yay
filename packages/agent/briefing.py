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


# ── Patron dili: kod/jargon yerine günlük Türkçe (yönetici özeti sesli okunur) ──
_REGIME_TR = {"OFFENSIVE": "atak", "NEUTRAL": "nötr", "DEFENSIVE": "savunmacı", "CRISIS": "kriz"}
_SYMBOL_TR = {"BTCUSD": "Bitcoin", "ETHUSD": "Ethereum", "XAUUSD": "Altın", "XAGUSD": "Gümüş"}
_TF_TR = {
    "15m": "15 dakikalık grafik", "1h": "1 saatlik grafik", "4h": "4 saatlik grafik",
    "1d": "günlük grafik", "1w": "haftalık grafik",
}
_DIRECTION_TR = {"bullish": "alış (yukarı)", "bearish": "satış (aşağı)", "neutral": "henüz yönsüz"}


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
    regime_clause = f"piyasanın genel modu {_regime_tr(regime_label)}"
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
        pos_clause = f"masada {len(positions)} açık pozisyon var (toplam {_usd_tr(total)})"
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

    # En güçlü hücre — patron diline çevrilir: hangi varlık, hangi grafik,
    # hangi yön, sinyal gücü ne ve eşiğe göre nerede.
    top = max(cells, key=lambda c: c.get("score") or 0) if cells else None
    top_score = (top.get("score") or 0) if top else 0
    gap = SCORE_DIRECTIONAL - top_score
    if top:
        sym_txt = _symbol_tr(top.get("symbol"))
        tf_txt = _tf_tr(top.get("timeframe"))
        dir_txt = _DIRECTION_TR.get(str(top.get("direction") or ""), "yukarı")
        if gap <= 0:
            market_clause = (
                f"en güçlü sinyal {sym_txt} tarafında: {tf_txt}, {dir_txt} yönü; sinyal gücü "
                f"{top_score:.0f} puan ve işlem için aradığımız alt sınır ({SCORE_DIRECTIONAL:.0f} puan) aşıldı"
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
        event_clause = f"takvimdeki en yakın önemli olay {label}, {when}"
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

    # ── Duruş (öncelik sırası: en kritik kazanır) ──
    if halts:
        stance, label_, tone = "halt", "İŞLEM DURDURULDU", "alert"
        headline = f"İşlemler güvenlik nedeniyle durduruldu — {len(halts)} acil durdurma devrede."
        narrative = (
            f"Risk tarafında acil durdurma tetiklendi; sistem yeni pozisyon açmıyor ve bu kilidi "
            f"yalnızca sen elle kaldırabilirsin. {pos_clause.capitalize()}; mevcut pozisyonlar "
            f"yönetilmeye devam ediyor. {regime_clause.capitalize()}."
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
            f"eksik veriyle işlem açmak körleme olurdu. {pos_clause.capitalize()}. "
            f"Veri düzelince adaylar otomatik olarak yeniden üretilir."
        )
        recommendation = "Veri kaynaklarının düzelmesini bekle; bu tabloda işlem zorlamak risklidir."
    elif down:
        stance, label_, tone = "data_gap", "VERİ BOŞLUĞU", "warn"
        headline = f"Veri boşluğu var — şu kaynaklar yanıt vermiyor: {', '.join(down)}."
        narrative = (
            f"Bir veya birden fazla veri kaynağı çevrimdışı; sistem karar üretmeye devam ediyor ama "
            f"kör noktası var. Şu an {market_clause}. {regime_clause.capitalize()}; {pos_clause}."
        )
        recommendation = "Veri kaynakları düzelene kadar yeni pozisyonlara temkinli yaklaşmak doğru olur."
    elif gap <= 0:
        stance, label_, tone = "signal", "SİNYAL VAR", "ok"
        headline = f"İşlem sinyali oluştu — {market_clause}."
        narrative = (
            f"{regime_clause.capitalize()}, risk tarafında engel yok; {pos_clause}. "
            f"{event_clause.capitalize()}."
        )
        recommendation = (
            "Sinyal şimdi risk kontrolünden geçecek; onaylanırsa işlem deneme hesabında (gerçek para "
            "değil) otomatik açılır ve Trade Ticket panelinde görünür. Senin bir şey yapman gerekmiyor."
        )
    elif gap <= 2:
        stance, label_, tone = "watching", "İZLEMEDE", "info"
        headline = f"Fırsata yaklaşıyoruz — {market_clause}."
        narrative = (
            f"Henüz işlem açacak güçte bir sinyal yok ama bir aday sınırın hemen altında. "
            f"{regime_clause.capitalize()}, risk tarafı temiz; {pos_clause}. {event_clause.capitalize()}."
        )
        recommendation = "Şu an yapılacak bir şey yok; aday sınırı geçerse anında haber veririm."
    else:
        stance, label_, tone = "calm", "SAKİN", "info"
        headline = "Piyasa sakin — işlem açacak güçte bir sinyal yok."
        narrative = (
            f"Şu an {market_clause}. {regime_clause.capitalize()}, risk tarafı temiz; {pos_clause}. "
            f"{event_clause.capitalize()}."
        )
        recommendation = "Beklemek en doğrusu; sistem güçlü bir sinyal görmeden işlem zorlamaz."

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
