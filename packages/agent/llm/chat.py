"""State-grounded chat — kullanıcı sorularını mevcut backend state'iyle yanıtlar.

Akış: injection guard → deterministik grounded yanıt (her zaman üretilir)
→ LLM varsa aynı bağlamla daha akıcı anlatım. LLM yoksa/başarısızsa
deterministik yanıt döner; state'te olmayan şey UYDURULMAZ.
"""
from __future__ import annotations

import hashlib
import re
import time

from packages.agent.llm import budget, cache, guard, system_memory, web_search
from packages.agent.llm import client as llm_client
from packages.agent.llm import context as ctx_mod
from packages.notifications import list_recent as list_notifications

_SYMBOL_ALIASES = {
    "btc": "BTCUSD",
    "bitcoin": "BTCUSD",
    "eth": "ETHUSD",
    "ethereum": "ETHUSD",
    "xau": "XAUUSD",
    "altın": "XAUUSD",
    "gold": "XAUUSD",
    "xag": "XAGUSD",
    "gümüş": "XAGUSD",
    "silver": "XAGUSD",
}

# İşlem evreni (otomatik işlem yalnızca bunlarda).
_TRADE_UNIVERSE = {"BTCUSD", "ETHUSD", "XAUUSD", "XAGUSD"}

# Geçici (ephemeral) teknik analiz için DESTEKLENEN sembol alias'ları —
# işlem evreni + provider'da çekilebilen diğer varlıklar.
_ANALYZE_ALIASES = {
    **_SYMBOL_ALIASES,
    "sp500": "SP500", "s&p": "SP500", "spx": "SP500", "hisse": "SP500",
    "stocks": "SP500", "borsa": "SP500",
    "qqq": "QQQ", "nasdaq": "QQQ",
    "brent": "BRENT", "petrol": "BRENT", "oil": "BRENT",
    "tlt": "TLT", "tahvil": "TLT", "bond": "TLT", "bonds": "TLT",
    "dxy": "DXY", "dolar endeks": "DXY", "dollar index": "DXY",
    "vix": "VIX", "korku endeks": "VIX",
    "hyg": "HYG", "lqd": "LQD",
}

# Analiz niyeti — sembol + bu kelimelerden biri → ephemeral teknik analiz.
_ANALYZE_INTENT = (
    "analiz", "teknik", "incele", "yorumla", "yorum", "rsi", "trend",
    "nasıl görün", "nasil gorun", "ne durumda", "grafik", "momentum",
)

_TIMEFRAMES = ("15m", "1h", "4h", "1d", "1w")

# Yön eşiği (consensus.bullish_min) — config tek kaynak, hardcode etme.
def _directional_threshold() -> float:
    try:
        from packages.data.registry.loader import load_thresholds

        return float(load_thresholds().get("consensus", {}).get("bullish_min", 55))
    except Exception:
        return 55.0


_SCORE_DIRECTIONAL = _directional_threshold()

_SIDE_TR = {"long": "alış", "short": "satış", "open_long": "alış", "open_short": "satış"}

# Sesli okuma + Türkçe akıcılık için: İngilizce/teknik etiketleri Türkçeye çevir.
_REGIME_TR = {
    "OFFENSIVE": "atak", "NEUTRAL": "nötr", "DEFENSIVE": "savunmacı", "CRISIS": "kriz",
}
_RISK_ACTION_TR = {
    "HOLD": "beklemede", "WATCH": "izlemede",
    "NO_POSITION_INCREASE": "yeni pozisyon açma durduruldu",
    "RISK_REDUCE": "riski azalt", "HEDGE_INCREASE": "korunmayı artır",
    "KILL_SWITCH": "acil durdurma",
}


def _regime_tr(label: str | None) -> str:
    return _REGIME_TR.get((label or "").upper(), label or "bilinmiyor")


def _risk_tr(action: str | None) -> str:
    return _RISK_ACTION_TR.get((action or "").upper(), action or "?")


def _money(x) -> str:
    try:
        return f"${float(x):,.0f}"
    except (TypeError, ValueError):
        return "?"


def _positions_phrase(ctx: dict) -> str:
    """Açık pozisyonları patron diline çevirir (jargon yok)."""
    pos = ctx["paper"]["open_positions"]
    if not pos:
        return "açık pozisyonun yok"
    if len(pos) == 1:
        p = pos[0]
        side = _SIDE_TR.get(p.get("side", ""), p.get("side", ""))
        return f"1 açık pozisyonun var ({p['symbol']} {side}, {_money(p['size_usd'])})"
    total = sum(p.get("size_usd", 0) for p in pos)
    return f"{len(pos)} açık pozisyonun var (toplam {_money(total)})"


def _detect_symbol(folded: str) -> str | None:
    for alias, sym in _SYMBOL_ALIASES.items():
        if alias in folded:
            return sym
    return None


def _detect_timeframe(folded: str) -> str | None:
    for tf in _TIMEFRAMES:
        if tf in folded:
            return tf
    return None


def _detect_analyze_symbol(folded: str) -> str | None:
    """Geçici teknik analiz için desteklenen sembol (geniş alias seti)."""
    for alias, sym in _ANALYZE_ALIASES.items():
        if alias in folded:
            return sym
    return None


def _asset_analysis_answer(symbol: str) -> tuple[str, list[str]]:
    """Ephemeral teknik analiz — mevcut pipeline'ı sembol için on-demand çalıştırır."""
    from packages.analysis.ephemeral import analyze_symbol

    a = analyze_symbol(symbol)
    if not a.get("available"):
        return (
            f"{symbol} için on-demand veri kaynağı yok ({a.get('reason', '')}). "
            "Desteklenenlerde teknik analiz yapabilirim: BTC, ETH, Altın, Gümüş, "
            "SP500, QQQ, Brent, Tahvil (TLT), DXY, VIX.",
            ["analysis:unavailable"],
        )
    tf = a["timeframes"]
    parts = [f"{symbol} geçici teknik analiz (gözlemci):"]
    parts.append(f"Genel skor {a['overall_score']}/100 → {a['overall_direction']}.")
    if a.get("last_price") is not None:
        parts.append(f"Son fiyat {a['last_price']:,.2f}.")
    mom = a.get("momentum_pct") or {}
    mom_str = ", ".join(f"{k} {v:+.1f}%" for k, v in mom.items() if v is not None)
    if mom_str:
        parts.append(f"Momentum: {mom_str}.")
    for t, d in tf.items():
        rsi = f"RSI {d['rsi']}" if d.get("rsi") is not None else "RSI yok"
        parts.append(
            f"{t}: skor {d['score']} ({d['direction']}), {rsi}, EMA {d.get('ema_stack') or '—'}."
        )
    parts.append("Not: işlem evreni dışı / gözlemci — otomatik işlem yok.")
    evidence = [f"analysis:{symbol}", f"score:{a['overall_score']}"]
    evidence += [f"tf:{t}:{d['score']}" for t, d in tf.items()]
    return " ".join(parts), evidence


def _cells_for(ctx: dict, symbol: str, timeframe: str | None) -> list[dict]:
    cells = ctx["matrix"]["top_cells"] + ctx["matrix"]["candidate_vs_final_diffs"]
    # top_cells ve diffs farklı şekilli — normalize et (symbol/timeframe/final/blocked_by).
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for c in cells:
        key = (c["symbol"], c["timeframe"])
        if c["symbol"] != symbol or key in seen:
            continue
        if timeframe and c["timeframe"] != timeframe:
            continue
        seen.add(key)
        out.append(c)
    return out


def _fmt_cell(c: dict) -> str:
    blocked = ", ".join(c.get("blocked_by") or [])
    final = c.get("final", c.get("action", "?"))
    cand = c.get("candidate", "?")
    base = f"{c['symbol']} {c['timeframe']}: aday {cand} → final {final}"
    if blocked:
        base += f" (blocked_by: {blocked})"
    elif c.get("reason"):
        base += f" ({c['reason']})"
    return base


def _suspended_note(ctx: dict) -> str | None:
    if not ctx_mod.no_actionable_decision(ctx):
        return None
    rg = ctx["matrix"]["risk_gate"] or {}
    if ctx["dqs"]["status"] == "BLOCKED":
        return (
            f"Şu an işlem yapılamıyor: veri kalitesi engelli (puan {ctx['dqs']['score']:.0f}) — "
            "doğrulanmış veri yetersiz olduğu için yeni karar üretilmiyor."
        )
    return (
        f"Şu an yeni işlem yapılamıyor: risk kapısı kısıtlayıcı — "
        f"{_risk_tr(rg.get('action'))} ({rg.get('reason')})."
    )


def _missing_data_answer(ctx: dict) -> tuple[str, list[str]]:
    missing: list[str] = []
    for name, meta in (ctx.get("provider_issues") or {}).items():
        missing.append(f"{name}: {meta.get('status', 'sorunlu')}")
    missing += list(ctx["dqs"]["notes"])
    missing += [w for w in ctx.get("warnings") or [] if "DEGRADED" in w]
    if not missing:
        return (
            "State'e göre kritik veri eksiği görünmüyor; tüm sağlayıcılar OK.",
            [f"dqs:{ctx['dqs']['status']}"],
        )
    listing = "; ".join(missing[:6])
    return (
        f"Eksik/sorunlu veri: {listing}. DQS {ctx['dqs']['status']} "
        f"({ctx['dqs']['score']:.0f}).",
        [f"missing:{m}" for m in missing[:6]],
    )


def _risk_gate_answer(ctx: dict) -> tuple[str, list[str]]:
    rg = ctx["matrix"]["risk_gate"] or {}
    action = rg.get("action")
    if action in (None, "HOLD") and not ctx["halt"]["active"] and not ctx["matrix"]["blocked_by_reasons"]:
        return (
            "Risk tarafında seni durduran bir şey yok: kapı açık (HOLD), aktif halt "
            "yok ve adayları kesen bir kural çalışmıyor. Engel sinyal gücünde, riskte değil.",
            [f"risk_gate:{action}"],
        )
    if action == "HOLD":
        parts = ["Risk kapısı açık (HOLD)."]
    else:
        parts = [f"Risk kapısı şu an {action} ({rg.get('reason')})."]
    evidence = [f"risk_gate:{action}"]
    if ctx["halt"]["active"]:
        halts = ", ".join(f"{h['type']}→{h['level']}" for h in ctx["halt"]["events"])
        parts.append(f"Üstüne aktif halt var ({halts}) — bunu yalnızca senin manuel reset'in açar.")
        evidence += [f"halt:{h['type']}" for h in ctx["halt"]["events"]]
    blocked = ctx["matrix"]["blocked_by_reasons"]
    if blocked:
        parts.append("Asıl seni durduran, adayları kesen şu kurallar: " + ", ".join(blocked[:5]) + ".")
        evidence += [f"blocked_by:{b}" for b in blocked[:5]]
    return " ".join(parts), evidence


def _why_no_trade_answer(ctx: dict, symbol: str, timeframe: str | None) -> tuple[str, list[str]]:
    note = _suspended_note(ctx)
    cells = _cells_for(ctx, symbol, timeframe)
    if note:
        return (
            f"{symbol} için pozisyon açılmadı çünkü {note}",
            [f"dqs:{ctx['dqs']['status']}", "matrix:suspended"],
        )
    if not cells:
        # diff yoksa sembol matrix evreninde mi?
        if symbol not in (ctx["matrix"]["symbols"] or []):
            return (
                f"{symbol} decision matrix evreninde değil — bu sembol için "
                "state'te karar verisi yok.",
                ["matrix:symbols"],
            )
        return (
            f"{symbol} için gate'lerce kesilen bir aday yok: consensus eşiği "
            "aşılmadı (yön sinyali zayıf) ya da hücre zaten actionable.",
            [f"matrix:{symbol}"],
        )
    lines = [_fmt_cell(c) for c in cells[:5]]
    return (
        f"{symbol} kararının gerekçesi hücre bazında: " + " | ".join(lines),
        [f"matrix:{_fmt_cell(c)}" for c in cells[:5]],
    )


def _open_positions_clause(ctx: dict) -> str:
    """'İşlem yok' yanılgısını giderir: kısıt yalnızca YENİ girişi durdurur,
    mevcut pozisyonlar açık kalır ve yönetilir."""
    n = len(ctx["paper"]["open_positions"])
    if not n:
        return ""
    return (
        f"Bu 'işlem yok', YALNIZCA yeni giriş yok demek — mevcut {n} pozisyonun "
        "açık ve SL/TP/time-stop ile yönetiliyor."
    )


def _waiting_answer(ctx: dict) -> tuple[str, list[str]]:
    note = _suspended_note(ctx)
    if note:
        missing, _ = _missing_data_answer(ctx)
        pos = _open_positions_clause(ctx)
        body = f"{note} {pos}".strip()
        return (
            f"{body} Agent'ın beklediği şey: kısıtların kalkması. {missing}",
            [f"dqs:{ctx['dqs']['status']}"],
        )
    actions = ctx["matrix"]["paper_actions"]
    blocked = ctx["matrix"]["blocked_by_reasons"]
    if actions:
        acts = ", ".join(
            f"{a['symbol']} {a['timeframe']} {_SIDE_TR.get(a['paper_action'], a['paper_action'])}"
            for a in actions[:4]
        )
        ev = [f"paper_action:{a['symbol']}:{a['timeframe']}" for a in actions[:4]]
        if blocked:
            return (
                f"Sinyaller oluştu ({acts}) ama şu kurallar paper'da gerçek açılışı "
                f"engelliyor: {', '.join(blocked[:4])}. Bu yüzden ekranda 'işlem yok' "
                "görüyorsun — engeller kalkmadan pozisyon açılmaz.",
                ev + [f"blocked_by:{b}" for b in blocked[:4]],
            )
        return (
            f"İşleme hazır sinyal var: {acts}. Risk kapısı onaylayınca paper "
            "tarafında açılır.",
            ev,
        )
    diffs = ctx["matrix"]["candidate_vs_final_diffs"]
    if diffs:
        lines = " | ".join(_fmt_cell(d) for d in diffs[:3])
        return (
            f"İzleme modundayım: adaylar oluştu ama risk kapıları kesiyor — {lines}. "
            "Bu engeller kalkana kadar pozisyon açmıyorum.",
            [f"matrix:{_fmt_cell(d)}" for d in diffs[:3]],
        )
    return (
        "İzleme modundayım: hiçbir adayın yön gücü işlem eşiğini geçmedi, yani "
        "daha güçlü bir sinyal bekliyorum. Zorlama işlem yok.",
        [f"regime:{ctx['matrix']['regime']}"],
    )


def _best_cell(ctx: dict) -> dict | None:
    cells = ctx["matrix"]["top_cells"]
    return max(cells, key=lambda c: c.get("score") or 0) if cells else None


def _overview_answer(ctx: dict) -> tuple[str, list[str]]:
    """30 saniyelik piyasa bülteni — dünya piyasası/ekonomi haberi okuyan üslup;
    yalnızca state'teki gerçek manşet + makro rejim + portföy (uydurma yok)."""
    m = ctx["matrix"]
    news = [h for h in (ctx.get("news") or []) if h]
    note = _suspended_note(ctx)
    parts: list[str] = ["Piyasa bülteni."]

    parts.append(f"Piyasa rejimi {_regime_tr(m['regime'])}.")

    # Dünya piyasası & ekonomi manşetleri (gerçek, state'ten).
    if news:
        parts.append("Masada öne çıkan başlıklar: " + " · ".join(h[:80] for h in news[:3]) + ".")

    if note:
        parts.append(note)

    best = _best_cell(ctx)
    if best:
        score = best.get("score") or 0
        gap = _SCORE_DIRECTIONAL - score
        if gap <= 0:
            parts.append(
                f"En güçlü kanaat {best['symbol']} {best['timeframe']}: skor "
                f"{score:.0f}/{_SCORE_DIRECTIONAL:.0f} ile yön eşiğini geçti."
            )
        else:
            parts.append(
                f"En güçlü aday {best['symbol']} {best['timeframe']}: skor {score:.0f}/{_SCORE_DIRECTIONAL:.0f}, "
                f"eşiğe {gap:.1f} puan var — henüz tetik yok."
            )

    parts.append(
        f"Portföy tarafında {_positions_phrase(ctx)}; kasada {_money(ctx['paper']['equity_usd'])}."
    )
    evidence = [f"snapshot:{ctx['snapshot_id']}", f"dqs:{ctx['dqs']['status']}"]
    evidence += [f"news:{h[:40]}" for h in news[:2]]
    return " ".join(parts), evidence


def _opportunity_answer(ctx: dict) -> tuple[str, list[str]]:
    """'İşleme en yakın aday?' / '15 dakikalık fırsat var mı?' — net cevap."""
    note = _suspended_note(ctx)
    best = _best_cell(ctx)
    if not best:
        return ("Şu an matris boş, değerlendirilecek bir aday yok.", ["matrix:empty"])
    score = best.get("score") or 0
    gap = _SCORE_DIRECTIONAL - score
    sym, tf = best["symbol"], best["timeframe"]
    if gap <= 0:
        msg = (
            f"İşleme en yakın aday {sym} {tf}: skor {score:.0f}/{_SCORE_DIRECTIONAL:.0f} ile yön eşiğini geçti. "
            "Risk kapısından da geçerse paper tick'te uygulanır."
        )
    else:
        msg = (
            f"İşleme en yakın aday {sym} {tf}: skor {score:.0f}/{_SCORE_DIRECTIONAL:.0f} — eşiğe {gap:.1f} puan kaldı, "
            "yani fırsata yakınız ama henüz tetiklenmedi."
        )
    if note:
        msg += f" Yalnız şunu da bil: {note}"
    return msg, [f"matrix:{sym}/{tf}:{score:.0f}"]


def _news_answer(ctx: dict) -> tuple[str, list[str]]:
    """Haber özeti — başlıklar bağlamdır; tek başına işlem üretmez."""
    news = list(ctx.get("news") or [])
    if not news:
        return ("Akışta yeni öne çıkan haber yok.", ["news:none"])
    listing = " • ".join(h[:90] for h in news[:3])
    return (
        f"Öne çıkan başlıklar: {listing}. Haber yalnızca bağlamdır; sembol etkisi "
        "doğrulanmadan tek başına işlem açtırmaz.",
        [f"news:{h[:40]}" for h in news[:3]],
    )


_LIVE_WEB_DIRECT = (
    "son dakika", "son haber", "son 1 saat", "son bir saat", "guncel haber",
    "güncel haber", "latest news", "breaking news",
)
_LIVE_WEB_NEWS_WORDS = ("haber", "news", "manset", "manşet", "baslik", "başlık", "guncel", "güncel")
_LIVE_WEB_TIME_WORDS = ("bugun", "bugün", "son", "yeni", "az once", "az önce", "simdi", "şimdi")
_LIVE_WEB_SUBJECTS = (
    "trump", "israil", "israel", "iran", "abd", "amerika", "fed", "fomc",
    "powell", "rusya", "russia", "ukrayna", "ukraine", "cin", "china",
    "bitcoin", "btc", "altin", "altın", "petrol", "oil",
)
_LIVE_WEB_SPEECH = ("ne dedi", "aciklama", "açıklama", "konustu", "konuştu", "statement", "said")


def _is_live_web_question(folded: str) -> bool:
    """Only route genuinely current/public-world questions to live web search."""
    if any(k in folded for k in _LIVE_WEB_DIRECT):
        return True
    has_news_word = any(k in folded for k in _LIVE_WEB_NEWS_WORDS)
    has_time_word = any(k in folded for k in _LIVE_WEB_TIME_WORDS)
    has_subject = any(k in folded for k in _LIVE_WEB_SUBJECTS)
    has_speech = any(k in folded for k in _LIVE_WEB_SPEECH)
    return (has_news_word and (has_time_word or has_subject)) or (has_subject and has_speech)


def _web_topic_for(folded: str) -> str:
    if any(k in folded for k in ("btc", "bitcoin", "borsa", "fed", "fomc", "piyasa", "market", "altin", "altın", "petrol", "oil")):
        return "finance"
    return "news"


def _web_news_answer(message: str, ctx: dict) -> tuple[str, list[str]]:
    """Live public news answer; read-only and source-linked."""
    folded = message.casefold()
    result = web_search.search(
        message,
        topic=_web_topic_for(folded),
        time_range="day" if any(k in folded for k in ("son", "bugun", "bugün", "simdi", "şimdi")) else "week",
        max_results=5,
    )
    fallback, fallback_ev = _news_answer(ctx)
    if result.error:
        if result.error == "missing_api_key":
            prefix = "Canli web aramasi kapali: TAVILY_API_KEY backend env'de yok."
        else:
            prefix = f"Canli web aramasi su an alinamadi ({result.error})."
        return (
            f"{prefix} Mevcut backend haber akisi: {fallback}",
            [f"web:tavily:{result.error}", *fallback_ev],
        )
    if not result.answer and not result.results:
        return (
            f"Canli web aramasi bu soru icin sonuc dondurmedi. Mevcut backend haber akisi: {fallback}",
            ["web:tavily:no_results", *fallback_ev],
        )

    lines: list[str] = []
    if result.answer:
        lines.append(f"Kisa sonuc: {result.answer}")
    for idx, hit in enumerate(result.results[:3], 1):
        stamp = f" ({hit.published_date})" if hit.published_date else ""
        snippet = f" - {hit.content[:180].rstrip()}" if hit.content else ""
        lines.append(f"{idx}. {hit.title}{stamp}{snippet} Kaynak: {hit.url}")
    usage = f" Tavily kredi: {result.usage_credits}." if result.usage_credits is not None else ""
    return (
        "Canli web ozeti (emir/karar uretmez): " + " ".join(lines) + usage,
        ["web:tavily:live_search", *[f"web:{hit.url}" for hit in result.results[:3]]],
    )


_CONTEXT_ONLY_NOTE = (
    " Bu dimensiyon karar zincirinde yalnızca kısıtlayıcı/bağlamdır — "
    "asla pozisyon büyütmez ve RiskGate'i gevşetmez."
)


def _options_answer(ctx: dict) -> tuple[str, list[str]]:
    opts = (ctx.get("deep_data") or {}).get("options") or []
    if not opts:
        return (
            "Options state'te dikkat çeken bir IV/skew rejimi yok (rejim NORMAL "
            "ya da veri doğrulanmadı) — options gate şu an kısıt üretmiyor.",
            ["deep_data:options:none"],
        )
    parts, ev = [], []
    for o in opts[:3]:
        proxy = " (25Δ skew proxy — gerçek greeks değil)" if o.get("is_proxy") else ""
        parts.append(
            f"{o['symbol']}: rejim {o['regime']}, ATM IV {o['atm_iv']}, "
            f"IV-RV {o['iv_rv_spread']}, skew {o['skew_25d']}{proxy}"
        )
        ev.append(f"options:{o['symbol']} {o['regime']}")
    return "Options zekâsı: " + " | ".join(parts) + "." + _CONTEXT_ONLY_NOTE, ev


def _volatility_answer(ctx: dict) -> tuple[str, list[str]]:
    vol = (ctx.get("deep_data") or {}).get("volatility") or []
    if not vol:
        return (
            "Realized volatilite state'te kısıtlayıcı bir rejim göstermiyor "
            "(NORMAL/LOW veya veri doğrulanmadı) — volatilite gate kısıt üretmiyor.",
            ["deep_data:volatility:none"],
        )
    parts, ev = [], []
    for v in vol[:3]:
        parts.append(
            f"{v['symbol']}/{v['timeframe']}: rejim {v['regime']}, durum "
            f"{v['vol_state']}, z-skor {v['vol_zscore']}"
        )
        ev.append(f"volatility:{v['symbol']}/{v['timeframe']} {v['regime']}")
    return (
        "Volatilite zekâsı: " + " | ".join(parts) + "." + _CONTEXT_ONLY_NOTE,
        ev,
    )


def _derivatives_answer(ctx: dict) -> tuple[str, list[str]]:
    derivs = (ctx.get("deep_data") or {}).get("derivatives") or []
    if not derivs:
        return (
            "Kripto türev verisi (funding/OI/squeeze) state'te kısıtlayıcı sinyal "
            "göstermiyor ya da doğrulanmadı — türev gate kısıt üretmiyor.",
            ["deep_data:derivatives:none"],
        )
    parts, ev = [], []
    for d in derivs[:3]:
        proxy = " (squeeze proxy — gerçek liquidation değil)" if d.get("is_proxy") else ""
        parts.append(
            f"{d['symbol']}: squeeze {d['squeeze_level']}, funding bias "
            f"{d['funding_bias']}{proxy}"
        )
        ev.append(f"derivatives:{d['symbol']} {d['squeeze_level']}")
    return "Türev zekâsı: " + " | ".join(parts) + "." + _CONTEXT_ONLY_NOTE, ev


def _rotation_answer(ctx: dict) -> tuple[str, list[str]]:
    rot = (ctx.get("deep_data") or {}).get("rotation") or {}
    if rot.get("status") != "OK":
        return (
            f"Sermaye rotasyonu şu an {rot.get('status', 'UNAVAILABLE')} — "
            "yeterli doğrulanmış veri yok, mock skor üretilmez.",
            [f"rotation:{rot.get('status', 'UNAVAILABLE')}"],
        )
    ev_lines = "; ".join(rot.get("evidence") or []) or "—"
    return (
        f"Sermaye rotasyonu: yön {rot.get('direction')} (skor {rot.get('score')}). "
        f"Kanıt: {ev_lines}.",
        [f"rotation:{rot.get('direction')} {rot.get('score')}"],
    )


def _catalyst_answer(ctx: dict) -> tuple[str, list[str]]:
    cats = (ctx.get("deep_data") or {}).get("catalysts") or []
    if not cats:
        return (
            "Doğrulanmış, yarı-ömrü dolmamış ve kısıtlayıcı bir katalizör (haber "
            "etkisi) state'te yok — catalyst gate kısıt üretmiyor.",
            ["deep_data:catalysts:none"],
        )
    parts, ev = [], []
    for c in cats[:3]:
        assets = ", ".join(c.get("affected_assets") or []) or "genel"
        parts.append(
            f"{c['event_type']} → {c['actionability']} ({assets}; yarı-ömür "
            f"{c.get('half_life_minutes')}dk)"
        )
        ev.append(f"catalyst:{c['event_type']} {c['actionability']}")
    return "Catalyst zekâsı: " + " | ".join(parts) + "." + _CONTEXT_ONLY_NOTE, ev


def _tickets_answer(ctx: dict | None = None) -> tuple[str, list[str]]:
    # Lazy import — router-level cache; chat'i sıkı bağımlı yapmaz.
    try:
        from apps.api.routers.paper_trading import _LAST_TICKETS as tickets  # noqa
    except Exception:
        tickets = []
    active = [t for t in (tickets or []) if t.get("status") == "active"]
    if not active:
        msg = (
            "Şu an broker'a gidecek aktif Trade Ticket yok — yeni bir sinyal ya "
            "gate'lere takıldı ya da yön eşiğini aşamadı."
        )
        # Pozisyon var ama ticket yok → görünür çelişkiyi açıkla.
        if ctx and ctx["paper"]["open_positions"]:
            msg += (
                f" Bu arada {_positions_phrase(ctx)}; ticket sadece YENİ sinyal için "
                "üretilir, mevcut açık pozisyon ondan ayrı bir şeydir."
            )
        return (msg, ["tickets:none"])
    parts = []
    ev = []
    for t in active[:4]:
        s = t.get("summary", {}) or {}
        side_label = "AL" if t.get("side") == "long" else "SAT"
        parts.append(
            f"{t.get('symbol')} {side_label} {t.get('timeframe', '?').upper()}: "
            f"entry {s.get('entry_price')}, SL {s.get('stop_loss')}, "
            f"TP {s.get('take_profit')}, R/R 1:{s.get('rr_ratio', 0):.1f}, "
            f"güven {int((s.get('confidence_calibrated') or 0) * 100)}%"
        )
        ev.append(f"ticket:{t.get('id')}")
    return "Aktif Trade Ticket'lar: " + " | ".join(parts) + ".", ev


def _notifications_answer() -> tuple[str, list[str]]:
    items = list_notifications(limit=8, unread_only=False)
    if not items:
        return ("Henüz bildirim yok.", ["notifications:none"])
    parts = []
    ev = []
    for n in items[:5]:
        prefix = "[okunmadı] " if not n.ack else ""
        parts.append(f"{prefix}{n.title} — {n.body_short}")
        ev.append(f"notif:{n.id}")
    return "Son bildirimler: " + " | ".join(parts) + ".", ev


# Bekleyen manuel emir (tek-owner sistem; süreç ömrü). Brain yön sorduğunda burada
# saklanır; sonraki "al/sat" mesajı bununla tamamlanır. 3 dk sonra geçersiz.
_PENDING_ORDER: dict | None = None
_PENDING_TTL_SEC = 180


def _bare_side(folded: str) -> str | None:
    f = folded.strip().rstrip(".!? ").strip()
    if f in ("al", "alış", "alis", "long", "buy", "alalım", "alalim", "uzun"):
        return "long"
    if f in ("sat", "satış", "satis", "short", "sell", "kısa", "kisa"):
        return "short"
    return None


def _parse_amount(folded: str) -> float | None:
    """'10 bin', '10k', '10000', '10.000' → dolar tutarı."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(bin|k|milyon|m)\b", folded)
    if m:
        # Çarpan dalında nokta ONDALIK'tır (2.5 bin = 2500), thousand-sep değil.
        base = float(m.group(1).replace(",", "."))
        return base * (1_000_000 if m.group(2) in ("milyon", "m") else 1000)
    m = re.search(r"(\d[\d.\s]{2,}\d|\d{3,})", folded)
    if m:
        digits = re.sub(r"[.\s]", "", m.group(1))
        if digits.isdigit():
            return float(digits)
    return None


_PRICE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:dolar|usd|\$)?\s*['’`]?(?:dan|den|tan|ten)\b")


def _parse_entry_price(folded: str) -> float | None:
    """'56 dolardan' / '56'dan' / '56 seviyesinden' → giriş (tetik) fiyatı."""
    m = _PRICE_RE.search(folded)
    if m:
        return float(m.group(1).replace(",", "."))
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:seviye|fiyat)", folded)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


def _parse_manual_order(folded: str) -> dict | None:
    """Owner emri mi? (sembol + tutar + emir niyeti). side belirsizse None döner
    (sorulur). entry_price varsa limit/stop, yoksa market. Dönen: {symbol, side,
    size_usd, entry_price}."""
    if not re.search(r"\b(al|sat|aç|ac|emir|pozisyon|işlem aç|islem ac|long|short|buy|sell)\b", folded):
        return None
    sym = _detect_analyze_symbol(folded)
    price = _parse_entry_price(folded)
    # Tutar: fiyat token'ını ('56 dolardan') çıkardıktan sonra ara — karışmasın.
    amt = _parse_amount(_PRICE_RE.sub(" ", folded) if price else folded)
    if sym is None or amt is None:
        return None
    side: str | None = None
    if "satın al" in folded or "satin al" in folded or "satınal" in folded:
        side = "long"
    elif re.search(r"\bsat\w*\b|\bshort\b|\bsell\b", folded):
        side = "short"
    elif re.search(r"\bal\b|\blong\b|\bbuy\b", folded):
        side = "long"
    return {"symbol": sym, "side": side, "size_usd": amt, "entry_price": price}


def _manual_order_answer(parsed: dict) -> tuple[str, list[str]]:
    from packages.paper import manual_order

    sym = parsed["symbol"]
    size = parsed["size_usd"]
    side = parsed["side"]
    price = parsed.get("entry_price")
    if side is None:
        global _PENDING_ORDER
        _PENDING_ORDER = {"symbol": sym, "size": size, "price": price, "ts": time.time()}
        return (
            f"{sym} için {size:.0f} dolarlık emir anladım ama yönü belirsiz — "
            "alış mı satış mı? 'al' ya da 'sat' diye yaz.",
            ["manual_order:need_side"],
        )
    try:
        r = manual_order.place(symbol=sym, side=side, size_usd=size, entry_price=price)
    except manual_order.ManualOrderError as exc:
        return (f"Emir açılamadı: {exc}.", ["manual_order:rejected"])
    yon = "alış" if r["side"] == "long" else "satış"
    if r["kind"] == "market":
        return (
            f"Emrini açtım (patron yetkisiyle, risk kapısını geçtim): {r['symbol']} {yon}, "
            f"{r['size_usd']:.0f} dolar, giriş {r['entry_price']:.2f}. "
            f"Zarar-kes {r['sl']:.2f}, kâr-al {r['tp']:.2f}. Kâğıt üzerinde pozisyon — gerçek emir yok.",
            [f"manual_order:{r['position_id']}"],
        )
    tip = "limit" if r["kind"] == "limit" else "stop"
    return (
        f"Bekleyen {tip} emri kurdum: {r['symbol']} {yon}, {r['size_usd']:.0f} dolar, "
        f"tetik fiyatı {r['trigger_price']:.2f} (şu an {r['market']:.2f}). "
        f"Fiyat tetiğe gelince otomatik açılacak. 'emirleri listele' / 'iptal et' diyebilirsin.",
        [f"pending_order:{r['order_id']}"],
    )


def _parse_pct(folded: str) -> float | None:
    """'%2' / 'yüzde 2' / '2%' / '1.5' → yüzde değeri (2 = %2)."""
    m = re.search(r"%\s*(\d+(?:[.,]\d+)?)|yüzde\s*(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*%", folded)
    if m:
        return float(next(g for g in m.groups() if g).replace(",", "."))
    m = re.search(r"\b(\d+(?:[.,]\d+)?)\b", folded)
    return float(m.group(1).replace(",", ".")) if m else None


def _parse_position_op(folded: str) -> dict | None:
    """Pozisyon yönetimi komutu (sembol şart). op: flip|trailing|partial|scale|sltp."""
    sym = _detect_analyze_symbol(folded)
    if sym is None:
        return None
    if re.search(r"ters[ie]?\s*çevir|tersine|\bflip\b|yönünü değiştir", folded):
        return {"op": "flip", "ref": sym}
    if re.search(r"trailing|takip stop|iz süren|takip eden stop", folded):
        pct = _parse_pct(folded)
        return {"op": "trailing", "ref": sym, "pct": pct}
    if re.search(r"\bekle\b|arttır|artır|büyüt|üstüne ekle|scale", folded):
        amt = _parse_amount(folded)
        return {"op": "scale", "ref": sym, "size_usd": amt}
    if re.search(r"kapat|sat|azalt|küçült", folded) and re.search(
        r"yarı|çeyrek|%|yüzde|kısmi|partial|\d", folded
    ):
        if "yarı" in folded:
            return {"op": "partial", "ref": sym, "fraction": 0.5}
        if "çeyrek" in folded:
            return {"op": "partial", "ref": sym, "fraction": 0.25}
        if re.search(r"%|yüzde", folded):
            pct = _parse_pct(folded)
            return {"op": "partial", "ref": sym, "fraction": (pct / 100) if pct else None}
        amt = _parse_amount(folded)
        if amt is not None:
            return {"op": "partial", "ref": sym, "size_usd": amt}
    if re.search(r"\bstop\b|\bsl\b|zarar.?kes|stop.?loss", folded):
        return {"op": "sltp", "ref": sym, "sl": _parse_amount(folded)}
    if re.search(r"\btp\b|kar.?al|kâr.?al|take.?profit|hedef", folded):
        return {"op": "sltp", "ref": sym, "tp": _parse_amount(folded)}
    return None


def _position_op_answer(p: dict) -> tuple[str, list[str]]:
    from packages.paper import position_ops as PO

    ref = p["ref"]
    op = p["op"]
    try:
        if op == "flip":
            r = PO.flip(ref)
            yon = "alış" if r["new_side"] == "long" else "satış"
            return (
                f"{r['symbol']} pozisyonunu ters çevirdim → şimdi {yon}, {r['size_usd']:.0f} dolar, "
                f"giriş {r['entry_price']:.2f}. Kapanan kâr-zarar {r['closed_pnl_usd']:.2f} dolar.",
                ["pos_op:flip"],
            )
        if op == "trailing":
            if not p.get("pct"):
                return ("Trailing mesafesini yüzde olarak yaz (ör. '%2').", ["pos_op:need_pct"])
            r = PO.set_trailing(ref, distance_pct=p["pct"] / 100)
            return (
                f"{r['symbol']} pozisyonuna takip eden stop ekledim: %{p['pct']:.1f} "
                f"(tepe {r['trail_peak']:.2f}). Lehe gidince kârı kilitler.",
                ["pos_op:trailing"],
            )
        if op == "scale":
            if not p.get("size_usd"):
                return ("Ne kadar ekleyeyim? Tutarı yaz (ör. '2 bin').", ["pos_op:need_amt"])
            r = PO.scale_in(ref, p["size_usd"])
            return (
                f"{r['symbol']} pozisyonuna ekledim → yeni boyut {r['size_usd']:.0f} dolar, "
                f"ortalama giriş {r['avg_entry']:.2f}.",
                ["pos_op:scale"],
            )
        if op == "partial":
            r = PO.partial_close(ref, fraction=p.get("fraction"), size_usd=p.get("size_usd"))
            return (
                f"{r['symbol']} pozisyonundan {r['closed_usd']:.0f} dolar kapattım "
                f"(kâr-zarar {r['pnl_usd']:.2f}). Kalan {r['remaining_usd']:.0f} dolar.",
                ["pos_op:partial"],
            )
        if op == "sltp":
            r = PO.modify_sltp(ref, sl=p.get("sl"), tp=p.get("tp"))
            return (
                f"{r['symbol']} pozisyonunu güncelledim: zarar-kes {r['sl']}, kâr-al {r['tp']}.",
                ["pos_op:sltp"],
            )
    except PO.PositionOpError as exc:
        return (f"İşlem yapılamadı: {exc}.", ["pos_op:rejected"])
    return ("Komutu anlayamadım.", ["pos_op:unknown"])


def _pending_orders_answer(folded: str) -> tuple[str, list[str]]:
    from packages.paper import manual_order

    # İptal mi?
    if re.search(r"\bipt[ae]l\b|\bvazgeç\b|\bsil\b|\bkaldır\b", folded):
        if re.search(r"\b(hep|tüm|tum|hepsi)\w*\b", folded):
            n = manual_order.cancel_all()
            return (f"{n} bekleyen emrin tümünü iptal ettim.", ["pending:cancel_all"])
        # tek id
        m = re.search(r"\b([0-9a-f]{6,10})\b", folded)
        if m and manual_order.cancel(m.group(1)):
            return (f"{m.group(1)} numaralı bekleyen emri iptal ettim.", ["pending:cancel"])
        return (
            "Hangi emri iptal edeyim? 'tümünü iptal' ya da emir numarasını yaz "
            "('emirleri listele' ile görebilirsin).",
            ["pending:cancel_need_id"],
        )
    # Listele
    orders = manual_order.list_pending()
    if not orders:
        return ("Bekleyen emrin yok.", ["pending:none"])
    lines = []
    for o in orders[:8]:
        yon = "alış" if o["side"] == "long" else "satış"
        lines.append(
            f"{o['id']}: {o['symbol']} {yon} {o['size_usd']:.0f}$, "
            f"{o['order_type']} tetik {o['trigger_price']:.2f}"
        )
    return ("Bekleyen emirler: " + " | ".join(lines), ["pending:list"])


def _grounded_answer(message: str, ctx: dict) -> tuple[str, list[str]]:
    folded = message.casefold()
    symbol = _detect_symbol(folded)
    timeframe = _detect_timeframe(folded)
    # Bekleyen emir + sadece yön ("al"/"sat") → önceki emri tamamla (chat hafızası).
    global _PENDING_ORDER
    if _PENDING_ORDER is not None:
        bs = _bare_side(folded)
        if bs and (time.time() - _PENDING_ORDER["ts"] < _PENDING_TTL_SEC):
            order = {
                "symbol": _PENDING_ORDER["symbol"],
                "side": bs,
                "size_usd": _PENDING_ORDER["size"],
                "entry_price": _PENDING_ORDER.get("price"),
            }
            _PENDING_ORDER = None
            return _manual_order_answer(order)
        if time.time() - _PENDING_ORDER["ts"] >= _PENDING_TTL_SEC:
            _PENDING_ORDER = None
    # Owner manuel emir — "BTC'ye 10 bin al" gibi komut. EN ÖNCE (action niyeti).
    manual = _parse_manual_order(folded)
    if manual is not None:
        return _manual_order_answer(manual)
    # Bekleyen emirleri listele / iptal.
    if re.search(r"bekleyen emir|emirleri|emir listele|açık emir|acik emir", folded) or (
        re.search(r"\bipt[ae]l\b", folded) and "emir" in folded
    ):
        return _pending_orders_answer(folded)
    # Pozisyon yönetimi — SL/TP, trailing, kısmi kapat, scale-in, flip.
    pos_op = _parse_position_op(folded)
    if pos_op is not None:
        return _position_op_answer(pos_op)
    if any(k in folded for k in ("ticket", "tiket", "sinyal listesi", "aktif sinyal")):
        return _tickets_answer(ctx)
    if any(k in folded for k in ("bildirim", "notification", "uyarı", "uyari", "alarm")):
        return _notifications_answer()
    memory = system_memory.answer(message)
    if memory is not None:
        return memory
    # Fırsat / en yakın aday — sembolden bağımsız "işleme yakın olan ne?" sorusu.
    if any(
        k in folded
        for k in ("fırsat", "firsat", "opportunity", "en yakın aday", "en yakin aday",
                  "yakın aday", "yakin aday", "aday hangi", "işleme yakın", "isleme yakin")
    ):
        return _opportunity_answer(ctx)
    if _is_live_web_question(folded):
        return _web_news_answer(message, ctx)
    if any(k in folded for k in ("haber", "news", "manşet", "manset", "başlık", "baslik")):
        return _news_answer(ctx)
    if any(k in folded for k in ("eksik", "missing", "hangi veri")):
        return _missing_data_answer(ctx)
    # v2.7 deep-data niyetleri (RiskGate/why fallback'inden ÖNCE — "volatility
    # neden kısıtladı?" gibi sorular ilgili dimensiyona gitsin).
    if any(k in folded for k in ("options", "opsiyon", "skew", "implied", "term structure")):
        return _options_answer(ctx)
    if any(k in folded for k in ("volatilite", "volatility", "oynaklık", "realized vol", "vol rejim")):
        return _volatility_answer(ctx)
    if any(k in folded for k in ("türev", "turev", "derivative", "funding", "open interest", "squeeze")):
        return _derivatives_answer(ctx)
    if any(k in folded for k in ("rotasyon", "rotation", "sermaye akış", "capital rotation")):
        return _rotation_answer(ctx)
    if any(k in folded for k in ("katalizör", "katalizor", "catalyst", "haber etkisi", "yarı ömür", "half-life", "half life")):
        return _catalyst_answer(ctx)
    if any(
        k in folded
        for k in ("riskgate", "risk gate", "risk kapısı", "risk kapisi", "engelledi",
                  "engelliyor", "engelle", "blocked", "ne durduruyor", "ne engel")
    ):
        return _risk_gate_answer(ctx)
    # Geçici teknik analiz: desteklenen sembol + analiz niyeti, VEYA işlem
    # evreni dışı bir sembol (onun için "neden işlem yok" mantığı yoktur).
    analyze_sym = _detect_analyze_symbol(folded)
    if analyze_sym and (
        any(k in folded for k in _ANALYZE_INTENT) or analyze_sym not in _TRADE_UNIVERSE
    ):
        return _asset_analysis_answer(analyze_sym)
    if symbol and any(
        k in folded for k in ("neden", "niye", "açmadın", "açılmadı", "hold", "why")
    ):
        return _why_no_trade_answer(ctx, symbol, timeframe)
    # Sembolsüz "neden işlem yok / ne bekliyorsun" → genel bekleme gerekçesi.
    if any(
        k in folded
        for k in ("bekliyor", "ne yapıyor", "waiting", "durum ne", "neden işlem",
                  "neden islem", "niye işlem", "niye islem", "neden açmıyor", "neden acmiyor")
    ):
        return _waiting_answer(ctx)
    if symbol:
        return _why_no_trade_answer(ctx, symbol, timeframe)
    return _overview_answer(ctx)


def answer(message: str) -> dict:
    """Chat yanıtı — her zaman state-grounded; LLM sadece anlatımı akıcılaştırır."""
    refusal = guard.screen(message)
    if refusal is not None:
        return {
            "answer": refusal,
            "refused": True,
            "evidence_used": ["safety:prompt_injection_guard"],
            "llm": {"mode": llm_client.get_mode(), "model": None, "source": "guard",
                    "cached": False},
        }

    ctx = ctx_mod.build_compact_context()
    grounded, evidence = _grounded_answer(message, ctx)
    live_evidence = any(e.startswith("web:tavily") or e.startswith("web:http") for e in evidence)
    mode = llm_client.get_mode()
    base = {
        "refused": False,
        "evidence_used": evidence,
        "snapshot_id": ctx["snapshot_id"],
    }

    client = llm_client.get_client()
    if client is None:
        return {
            **base,
            "answer": grounded,
            "llm": {"mode": mode, "model": None, "source": "fallback", "cached": False,
                    "fallback_reason": "llm_off" if mode == "off" else "no_api_key"},
        }

    digest = ctx_mod.context_digest(ctx)
    msg_hash = hashlib.sha1(message.casefold().strip().encode("utf-8")).hexdigest()[:12]
    live_bucket = f"|live:{int(time.time() // 900)}" if live_evidence else ""
    cache_key = f"chat|{mode}|{digest}|{msg_hash}{live_bucket}"
    cached = cache.get(cache_key)
    if cached is not None:
        return {**base, **cached, "llm": {**(cached.get("llm") or {}), "cached": True}}

    system = guard.SYSTEM_RULES
    source_label = (
        "STATE BAGLAMI + deterministik yanitta kaynak URL'leri verilen CANLI WEB BULGULARI"
        if live_evidence else "STATE BAGLAMI"
    )
    scope_rule = (
        "Yanitini YALNIZCA state baglami ve kaynakli web bulgularina dayandir."
        if live_evidence else "Yanitini YALNIZCA bu state baglamina dayandir."
    )
    user = (
        f"{source_label}:\n"
        f"{ctx_mod.context_for_prompt(ctx)}\n\n"
        "Deterministik motorun bu soru icin cikardigi kanit-temelli yanit:\n"
        f"{grounded}\n\n"
        f"KULLANICI SORUSU: {message}\n\n"
        f"{scope_rule} Baglamda olmayan seyi 'state'te yok' diye belirt. "
        "Karar/islem onerme. Kisa Turkce yanit ver."
    )
    max_out = budget.max_tokens_per_request()
    est = (len(system) + len(user)) // 4 + max_out
    comp = client.complete(system, user, max_out) if budget.can_spend(est) else None
    if comp is None:
        reason = "budget_exceeded" if not budget.can_spend(est) else "llm_error"
        return {
            **base,
            "answer": grounded,
            "llm": {"mode": mode, "model": None, "source": "fallback", "cached": False,
                    "fallback_reason": reason},
        }
    budget.record(comp.input_tokens + comp.output_tokens)
    result = {
        "answer": comp.text,
        "llm": {"mode": mode, "model": comp.model, "source": "llm", "cached": False,
                "fallback_reason": None},
    }
    cache.put(cache_key, result)
    return {**base, **result}
