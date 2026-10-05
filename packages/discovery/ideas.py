"""Fikir Panosu (owner kararı 2026-10-05) — keşif + haber öngörüsü + teknik analiz
+ yapay zekâ değerlendirmesi. SALT-GÖZLEM.

Aday küme: keşif evreninden teknik hükmü WOULD_OPEN_LONG olanlar ∪ haber öngörüsü
güçlü YUKARI olanlar. Her fikir için deterministik, şeffaf bir FİKİR SKORU
(teknik + gölge karne + haber − risk) ve ilk birkaç fikir için yapay zekâ
"fikir eleştirmeni" değerlendirmesi (GÜÇLÜ / İZLE / ZAYIF + tez/lehte/aleyhte/riskler).

Kırmızı çizgiler: hiçbir fikir işlem açmaz, evrene eklenmez, RiskGate'e girmez.
YZ hükmü anlatıdır; terfi kriterleri deterministik kalır ve owner onayı şarttır
(CP5). LLM yoksa (AWS'te yerel model yok) kurallı yedek değerlendirme döner.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from packages.learning.mistake_memory import wilson_bounds
from packages.ops.store import write_text_atomic

SCHEMA_VERSION = 1
MAX_IDEAS = 12
AI_TOP_N = 5
AI_CALLS_PER_RUN = 2
AI_MAX_AGE = timedelta(hours=12)
STRONG_NEWS = 40
_VERDICTS = {"GÜÇLÜ": "STRONG", "GUCLU": "STRONG", "İZLE": "WATCH", "IZLE": "WATCH",
             "ZAYIF": "WEAK", "STRONG": "STRONG", "WATCH": "WATCH", "WEAK": "WEAK"}
VERDICT_LABEL = {"STRONG": "GÜÇLÜ", "WATCH": "İZLE", "WEAK": "ZAYIF"}
STATUS_LABEL = {"WATCHING": "izleniyor", "PROMOTION_READY": "terfi eşiğinde",
                "AWAITING_APPROVAL": "onayını bekliyor"}
HONESTY = ("Fikirler hipotetiktir: hiçbiriyle işlem açılmaz, evrene otomatik eklenmez. "
           "Yapay zekâ değerlendirmesi anlatıdır; terfi deterministik eşik + owner onayı ister.")


def _path() -> Path:
    return Path(os.environ.get("IDEA_BOARD_PATH", "data/runtime/idea_board.json"))


def _iso(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat()


def _parse(ts: Any) -> datetime | None:
    try:
        out = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return out if out.tzinfo else out.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fikir kümesi + skor
# ---------------------------------------------------------------------------

def _market_info(art: Mapping[str, Any]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for key, kind in (("crypto_universe", "crypto"), ("commodity_universe", "commodity")):
        for c in (art.get(key) or {}).get("candidates") or []:
            out[str(c["symbol"])] = {"kind": kind, "name": c.get("name") or c["symbol"],
                                     "chg_7d_pct": c.get("chg_7d_pct"), "chg_30d_pct": c.get("chg_30d_pct")}
    for s in art.get("rising_sectors") or []:
        out[str(s["symbol"])] = {"kind": "sector_etf", "name": s.get("label") or s["symbol"],
                                 "chg_7d_pct": None, "chg_30d_pct": None}
    return out


def _scorecard(sc: Mapping[str, Any]) -> dict:
    wins, losses = int(sc.get("missed_win") or 0), int(sc.get("avoided_loss") or 0)
    decisive = wins + losses
    low = wilson_bounds(wins, decisive)[0] if decisive else None
    return {"signals": int(sc.get("n_signals") or 0), "resolved": int(sc.get("resolved") or 0),
            "missed_win": wins, "avoided_loss": losses, "decisive": decisive,
            "win_rate": round(wins / decisive, 3) if decisive else None,
            "wilson_low": round(low, 3) if low is not None else None,
            "avg_r": sc.get("avg_r")}


def score_idea(technical: Mapping[str, Any], card: Mapping[str, Any], news: Mapping[str, Any] | None,
               market: Mapping[str, Any]) -> tuple[int, dict, list[str]]:
    """Şeffaf fikir skoru (0–100) + bileşenler + risk notları."""
    risk_notes: list[str] = []
    if technical.get("verdict") == "WOULD_OPEN_LONG":
        tech = 20 + min(20.0, max(0.0, float(technical.get("expected_value") or 0)) * 40)
    else:
        ds = ((technical.get("per_tf") or {}).get("1d") or {}).get("direction_score") or 0
        tech = 10 if ds >= 55 else 0
    sc_pts = 0.0
    if card.get("decisive", 0) >= 5 and card.get("wilson_low") is not None:
        sc_pts = max(0.0, min(1.0, (card["wilson_low"] - 0.3) / 0.4)) * 25
    elif card.get("decisive", 0) < 5:
        risk_notes.append("gölge karne henüz yetersiz (<5 kararlı sonuç)")
    news_pts = 0.0
    if news and news.get("direction") == "up":
        news_pts = news["strength"] / 100 * 25
    elif news and news.get("direction") == "down":
        news_pts = -news["strength"] / 100 * 15
        risk_notes.append(f"haber öngörüsü aşağı (güç {news['strength']})")
    risk = 0.0
    chg30 = market.get("chg_30d_pct")
    if chg30 is not None and chg30 > 100:
        risk -= 10
        risk_notes.append(f"son 30 günde %{chg30:.0f} yükselmiş — çok oynak, geri çekilme riski")
    elif chg30 is not None and chg30 > 50:
        risk -= 5
        risk_notes.append(f"son 30 günde %{chg30:.0f} yükselmiş")
    bias_4h = (((technical.get("per_tf") or {}).get("4h") or {}).get("ta") or {}).get("bias")
    if bias_4h == "BEARISH":
        risk -= 5
        risk_notes.append("4 saatlik teknik yön düşüşte")
    comps = {"technical": round(tech, 1), "scorecard": round(sc_pts, 1),
             "news": round(news_pts, 1), "risk": round(risk, 1)}
    total = int(max(0, min(100, round(tech + sc_pts + news_pts + risk))))
    return total, comps, risk_notes


def _pending_proposals() -> dict[str, str]:
    try:
        from packages.governor import proposals

        out: dict[str, str] = {}
        for p in proposals.load().get("pending") or []:
            sym = (p.get("requested_change") or {}).get("add_custom_asset")
            if sym and p.get("status") == "PENDING":
                out[str(sym)] = str(p.get("proposal_id"))
        return out
    except Exception:
        return {}


def build_ideas(art: Mapping[str, Any], shadow_cands: Mapping[str, Any], forecasts: Mapping[str, Any],
                pending: Mapping[str, str], promotion_min: int = 20) -> list[dict]:
    market = _market_info(art)
    results = dict(art.get("results") or {})
    keys = {s for s, r in results.items() if r.get("verdict") == "WOULD_OPEN_LONG" and s in market}
    keys |= {s for s, f in forecasts.items()
             if s in market and f.get("direction") == "up" and f.get("strength", 0) >= STRONG_NEWS}
    ideas: list[dict] = []
    for sym in keys:
        res = dict(results.get(sym) or {})
        card = _scorecard(shadow_cands.get(sym) or {})
        news = forecasts.get(sym)
        info = market[sym]
        score, comps, notes = score_idea(res, card, news, info)
        entry_tf = res.get("entry_timeframe")
        per_tf = res.get("per_tf") or {}
        status = ("AWAITING_APPROVAL" if sym in pending
                  else "PROMOTION_READY" if card["decisive"] >= promotion_min and (card["wilson_low"] or 0) > 0.5
                  else "WATCHING")
        ideas.append({
            "symbol": sym, "kind": info["kind"], "name": str(info["name"]),
            "score": score, "components": comps, "status": status, "status_label": STATUS_LABEL[status],
            "proposal_id": pending.get(sym),
            "technical": {
                "verdict": res.get("verdict") or "NO_DATA", "entry_timeframe": entry_tf,
                "entry": res.get("entry"), "sl": res.get("sl"), "tp": res.get("tp"), "rr": res.get("rr"),
                "expected_value": res.get("expected_value"), "confidence": res.get("confidence"),
                "bullish_tfs": list(res.get("bullish_tfs") or []), "checked_at": res.get("checked_at"),
                "ta": (per_tf.get(entry_tf or "1h") or {}).get("ta"), "ta_1d": (per_tf.get("1d") or {}).get("ta"),
                "reasons": list(res.get("reasons") or []),
            },
            "scorecard": card,
            "news": None if not news else {k: news.get(k) for k in ("direction", "strength", "n_headlines", "evidence")},
            "market": {"chg_7d_pct": info.get("chg_7d_pct"), "chg_30d_pct": info.get("chg_30d_pct")},
            "risk_notes": notes,
        })
    ideas.sort(key=lambda i: (-i["score"], i["symbol"]))
    return ideas[:MAX_IDEAS]


# ---------------------------------------------------------------------------
# Yapay zekâ değerlendirmesi
# ---------------------------------------------------------------------------

def _fingerprint(idea: Mapping[str, Any]) -> str:
    """Kaba parmak izi: anlamlı değişim olmadıkça YZ yeniden sorulmaz."""
    t, n, c = idea["technical"], idea.get("news") or {}, idea["scorecard"]
    key = [idea["symbol"], t.get("verdict"), t.get("entry_timeframe"),
           round(float(t.get("expected_value") or 0), 1), n.get("direction"), int((n.get("strength") or 0) // 20),
           c.get("decisive", 0) // 5, idea["score"] // 10]
    return hashlib.sha1(json.dumps(key).encode()).hexdigest()[:12]


def dossier(idea: Mapping[str, Any]) -> dict:
    """LLM'e giden kompakt dosya (yalnız sistemin ürettiği kanıt)."""
    t = idea["technical"]
    ta = t.get("ta") or {}
    ta1d = t.get("ta_1d") or {}
    news = idea.get("news") or {}
    return {
        "varlik": {"sembol": idea["symbol"], "ad": idea["name"], "tur": idea["kind"]},
        "piyasa": idea.get("market"),
        "teknik": {"hukum": t.get("verdict"), "giris_tf": t.get("entry_timeframe"), "giris": t.get("entry"),
                   "stop": t.get("sl"), "hedef": t.get("tp"), "risk_odul": t.get("rr"),
                   "beklenen_deger_R": t.get("expected_value"), "guven": t.get("confidence"),
                   "yukselis_tfler": t.get("bullish_tfs"),
                   "giris_tf_ozet": {k: ta.get(k) for k in ("bias", "trend", "adx", "support", "resistance",
                                                              "patterns", "confirmations", "fib")},
                   "gunluk_ozet": {k: ta1d.get(k) for k in ("bias", "trend", "support", "resistance", "patterns")}},
        "golge_karne": idea["scorecard"],
        "haber_ongorusu": {"yon": news.get("direction"), "guc": news.get("strength"),
                           "baslik_sayisi": news.get("n_headlines"),
                           "basliklar": [f"{e.get('source')}: {e.get('title')}" for e in (news.get("evidence") or [])]},
        "fikir_skoru": idea["score"], "bilesenler": idea["components"], "risk_notlari": idea["risk_notes"],
    }


_PROMPT = (
    "Fikir eleştirmeni olarak aşağıdaki KEŞİF FİKRİNİ tart. Bu bir işlem emri DEĞİLDİR; "
    "alım-satım önermeden yalnız fikrin kalitesini değerlendir: haber öngörüsü, teknik analiz ve "
    "gölge karne birbirini destekliyor mu, en büyük risk ne? Yalnız dosyadaki kanıtı kullan; "
    "olmayan bilgiyi uydurma. Kısa ve Türkçe yaz.\n\nDOSYA:\n{dossier}\n\n"
    "Şu formatta yanıt ver (başka hiçbir şey yazma):\n"
    "HÜKÜM: <GÜÇLÜ | İZLE | ZAYIF>\n"
    "TEZ: <tek cümle>\n"
    "LEHTE:\n- <madde>\n"
    "ALEYHTE:\n- <madde>\n"
    "RİSKLER:\n- <madde>\n"
    "NE_DEĞİŞTİRİR: <tek cümle>"
)
# Bölüm başlığı eş-adları → kanonik ad. Python upper() Türkçe i/İ'yi bilmediği için
# IGNORECASE yerine açık eş-ad listesi (büyük/küçük/ASCII yazımlar).
_SECTION_ALIASES = {
    "HÜKÜM": ("HÜKÜM", "Hüküm", "hüküm", "HUKUM", "Hukum"),
    "TEZ": ("TEZ", "Tez", "tez"),
    "LEHTE": ("LEHTE", "Lehte", "lehte"),
    "ALEYHTE": ("ALEYHTE", "Aleyhte", "aleyhte"),
    "RİSKLER": ("RİSKLER", "Riskler", "riskler", "RISKLER"),
    "NE_DEĞİŞTİRİR": ("NE_DEĞİŞTİRİR", "NE DEĞİŞTİRİR", "Ne değiştirir", "Ne_değiştirir", "NE_DEGISTIRIR"),
}
_ALIAS_TO_SECTION = {alias: name for name, aliases in _SECTION_ALIASES.items() for alias in aliases}


def parse_evaluation(text: str) -> dict | None:
    """LLM metnini yapıya çevir; HÜKÜM okunamazsa None (kurallı yedeğe düşülür)."""
    aliases = sorted(_ALIAS_TO_SECTION, key=len, reverse=True)
    pattern = r"^[ \t]*[*#]*[ \t]*(" + "|".join(re.escape(a) for a in aliases) + r")[ \t]*[*]*[ \t]*:"
    parts = re.split(pattern, text, flags=re.MULTILINE)
    found: dict[str, str] = {}
    for i in range(1, len(parts) - 1, 2):
        found.setdefault(_ALIAS_TO_SECTION[parts[i]], parts[i + 1].strip())
    head = (found.get("HÜKÜM") or "").split("\n")[0].replace("i", "İ").replace("ı", "I").upper()
    raw_verdict = re.sub(r"[^A-ZÇĞİÖŞÜ]", "", head)
    verdict = _VERDICTS.get(raw_verdict)
    if verdict is None:
        return None

    def items(key: str) -> list[str]:
        lines = [ln.strip().lstrip("-•* ").strip() for ln in (found.get(key) or "").splitlines()]
        return [ln for ln in lines if ln][:4]

    return {"verdict": verdict, "thesis": (found.get("TEZ") or "").split("\n")[0][:300],
            "pros": items("LEHTE"), "cons": items("ALEYHTE"), "risks": items("RİSKLER"),
            "change_mind": (found.get("NE_DEĞİŞTİRİR") or "").split("\n")[0][:300]}


def fallback_evaluation(idea: Mapping[str, Any]) -> dict:
    """LLM yok/başarısız: kurallı, açıklanabilir değerlendirme."""
    t, card, news = idea["technical"], idea["scorecard"], idea.get("news") or {}
    pros, cons = [], []
    if t.get("verdict") == "WOULD_OPEN_LONG":
        pros.append(f"teknik sinyal var ({t.get('entry_timeframe')}, beklenen değer {t.get('expected_value')}R)")
    else:
        cons.append("güncel teknik sinyal yok")
    if news.get("direction") == "up":
        pros.append(f"haber öngörüsü yukarı (güç {news.get('strength')}, {news.get('n_headlines')} başlık)")
    elif news.get("direction") == "down":
        cons.append(f"haber öngörüsü aşağı (güç {news.get('strength')})")
    else:
        cons.append("haber kanıtı yok/nötr")
    if card.get("wilson_low") is not None and card["decisive"] >= 5:
        (pros if card["wilson_low"] > 0.5 else cons).append(
            f"gölge karne {card['missed_win']}/{card['decisive']} (alt sınır {card['wilson_low']})")
    score = idea["score"]
    verdict = ("STRONG" if score >= 65 and t.get("verdict") == "WOULD_OPEN_LONG" and news.get("direction") != "down"
               else "WEAK" if score < 35 else "WATCH")
    return {"verdict": verdict,
            "thesis": f"Fikir skoru {score}/100: teknik {idea['components']['technical']}, karne "
                      f"{idea['components']['scorecard']}, haber {idea['components']['news']}, risk {idea['components']['risk']}.",
            "pros": pros[:4], "cons": cons[:4], "risks": list(idea["risk_notes"])[:4] or ["belirgin ek risk notu yok"],
            "change_mind": "Gölge karnede ≥20 kararlı sonuç ve %50 üstü alt sınır ya da haber yönünün dönmesi."}


def _llm_evaluate(idea: Mapping[str, Any], client: Any) -> tuple[dict | None, dict]:
    from packages.agent.llm import budget
    from packages.agent.llm.guard import SYSTEM_RULES

    user = _PROMPT.format(dossier=json.dumps(dossier(idea), ensure_ascii=False, default=str))
    max_out = min(600, budget.max_tokens_per_request())
    est = (len(SYSTEM_RULES) + len(user)) // 4 + max_out
    if not budget.can_spend(est):
        return None, {"error": "budget"}
    comp = client.complete(SYSTEM_RULES, user, max_out)
    if comp is None:
        return None, {"error": "llm_unavailable"}
    budget.record((comp.input_tokens + comp.output_tokens) or est)
    parsed = parse_evaluation(comp.text)
    return parsed, {"source": comp.source, "model": comp.model, "error": None if parsed else "unparsed"}


# ---------------------------------------------------------------------------
# Koşu + görünüm
# ---------------------------------------------------------------------------

def _load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {"schema_version": SCHEMA_VERSION, "ideas": [], "evaluations": {}}


def run(
    now: datetime | None = None,
    *,
    scan_artifact: Mapping[str, Any] | None = None,
    shadow_cands: Mapping[str, Any] | None = None,
    forecasts: Mapping[str, Any] | None = None,
    pending: Mapping[str, str] | None = None,
    client_factory: Callable[[], Any] | None = None,
) -> dict:
    from packages.discovery import news_forecast, scanner, shadow_ledger

    now = now or datetime.now(UTC)
    art = scan_artifact if scan_artifact is not None else scanner._load_artifact()
    if shadow_cands is None:
        shadow_cands = dict(shadow_ledger.candidate_summary().get("candidates") or {})
    forecasts = forecasts if forecasts is not None else news_forecast.load_forecasts()
    pending = pending if pending is not None else _pending_proposals()
    promo_min = int(((scanner.load_config().get("promotion") or {}).get("min_resolved_decisive")) or 20)
    ideas = build_ideas(art, shadow_cands, forecasts, pending, promo_min)

    state = _load()
    evals: dict[str, dict] = dict(state.get("evaluations") or {})
    client = None
    llm_calls, llm_errors = 0, []
    for rank, idea in enumerate(ideas):
        fp = _fingerprint(idea)
        prev = evals.get(idea["symbol"]) or {}
        fresh = (prev.get("fingerprint") == fp and prev.get("source") != "deterministic"
                 and now - (_parse(prev.get("evaluated_at")) or now - AI_MAX_AGE) < AI_MAX_AGE)
        if fresh:
            idea["ai"] = prev
            continue
        ev, meta = None, {"source": "deterministic", "model": None, "error": None}
        if rank < AI_TOP_N and llm_calls < AI_CALLS_PER_RUN:
            if client is None:
                from packages.agent.llm import client as llm_client

                client = (client_factory or llm_client.get_client)() or False
            if client:
                llm_calls += 1
                ev, meta = _llm_evaluate(idea, client)
                if meta.get("error"):
                    llm_errors.append(f"{idea['symbol']}:{meta['error']}")
        if ev is None:
            # LLM'e sırası gelmediyse ve elde güncel bir LLM değerlendirmesi varsa onu koru.
            if prev.get("source") not in (None, "deterministic") and prev.get("fingerprint") == fp:
                idea["ai"] = prev
                continue
            ev, meta = fallback_evaluation(idea), {"source": "deterministic", "model": None,
                                                    "error": meta.get("error")}
        record = {**ev, "verdict_label": VERDICT_LABEL[ev["verdict"]], "source": meta.get("source") or "deterministic",
                  "model": meta.get("model"), "fingerprint": fp, "evaluated_at": _iso(now)}
        evals[idea["symbol"]] = record
        idea["ai"] = record
    keep = {i["symbol"] for i in ideas}
    evals = {s: e for s, e in evals.items() if s in keep}
    state.update({"schema_version": SCHEMA_VERSION, "generated_at": _iso(now), "ideas": ideas,
                  "evaluations": evals})
    write_text_atomic(_path(), json.dumps(state, ensure_ascii=False, default=str))
    return {"status": "OK", "ideas": len(ideas), "llm_calls": llm_calls, "llm_errors": llm_errors[:3],
            "top": [f"{i['symbol']}:{i['score']}:{i['ai']['verdict']}" for i in ideas[:3]]}


def evaluation_for(symbol: str) -> dict | None:
    """Terfi paketine kanıt olarak eklenecek YZ değerlendirmesi (varsa)."""
    return dict(_load().get("evaluations") or {}).get(symbol)


def viewmodel() -> dict:
    from packages.discovery import news_forecast

    state = _load()
    nf = news_forecast.viewmodel()
    return {
        "generated_at": state.get("generated_at"),
        "mode": "observe_only",
        "honesty": HONESTY,
        "ideas": list(state.get("ideas") or []),
        "news": {"generated_at": nf.get("generated_at"), "headlines": nf.get("headlines", 0),
                 "scorecard": nf.get("scorecard")},
    }


def compact_for_chat(limit: int = 3) -> dict[str, Any]:
    """Sohbet bağlamı: en yüksek skorlu fikirlerin kısa özeti (salt-gözlem)."""
    state = _load()
    rows = []
    for idea in list(state.get("ideas") or [])[:limit]:
        ai = idea.get("ai") or {}
        news = idea.get("news") or {}
        rows.append({
            "symbol": idea.get("symbol"), "kind": idea.get("kind"), "score": idea.get("score"),
            "status": idea.get("status_label"), "technical": (idea.get("technical") or {}).get("verdict"),
            "news": f"{news['direction']}:{news.get('strength')}" if news.get("direction") else None,
            "ai_verdict": ai.get("verdict_label"), "ai_source": ai.get("source"), "thesis": ai.get("thesis"),
        })
    return {"generated_at": state.get("generated_at"), "top": rows,
            "note": "fikirler hipotetiktir; işlem emri değildir"}


__all__ = ["build_ideas", "compact_for_chat", "dossier", "evaluation_for", "fallback_evaluation",
           "parse_evaluation", "run", "score_idea", "viewmodel"]
