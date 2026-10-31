"""Compact, change-aware executive brief for the Layer-0 cockpit.

This module is deliberately narrative-only.  It reuses the canonical world
evidence and starts an optional LLM rewrite in a single background worker when
that evidence changes.  The HTTP request always has a deterministic report to
return, so a slow or unavailable model cannot delay the cockpit or affect a
decision, risk gate, position, or order.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Iterable, Mapping
from concurrent.futures import Future
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from packages.agent.llm.world_report import build_world_brief
from packages.agent.localization import localize_headline

_LOCK = threading.Lock()
_LAST_DIGEST: str | None = None
_LAST_AI_DIGEST: str | None = None
_LAST_AI_RESULT: dict[str, Any] | None = None
_AI_FUTURE: Future[dict[str, Any]] | None = None
_AI_FUTURE_DIGEST: str | None = None
_LAST_SIGNIFICANT_KEYS: set[str] = set()

_DISPLAY_REPLACEMENTS = (
    ("Central Bank", "Merkez bankası"),
    ("Central banks", "Merkez bankaları"),
    ("Federal Reserve", "ABD Merkez Bankası"),
    ("US Foreign Affairs", "ABD Dışişleri"),
    ("Iran Foreign Affairs", "İran Dışişleri"),
    ("China Foreign Affairs", "Çin Dışişleri"),
    ("Russia Foreign Affairs", "Rusya Dışişleri"),
    ("Israel Foreign Affairs", "İsrail Dışişleri"),
    ("Senate", "Senato"),
    ("Congress", "Kongre"),
    ("Pentagon", "Pentagon"),
    ("ceasefire", "ateşkes"),
    ("peace talks", "barış görüşmeleri"),
    ("counter statement", "karşı açıklama"),
    ("Saudi-led coalition", "Suudi öncülüğündeki koalisyon"),
    ("Saudi", "Suudi"),
    ("Yemeni", "Yemenli"),
    ("Houthi", "Husi"),
    ("China Demonstrates Rapid Missile Response Amid US-Japan Drills Near Taiwan", "Çin, Tayvan yakınındaki ABD-Japonya tatbikatları sırasında füze hazırlığını gösterdi"),
    ("Trump’s Iran War Becomes Election Issue as Prices Rise Ahead of November 3 Midterms", "Trump'ın İran savaşı, fiyatlar yükselirken seçim gündeminin merkezine oturdu"),
    ("Trump's Iran War Becomes Election Issue as Prices Rise Ahead of November 3 Midterms", "Trump'ın İran savaşı, fiyatlar yükselirken seçim gündeminin merkezine oturdu"),
    ("Trump Says Iran Started the War, Claims Missiles Can Hit San Diego and Los Angeles", "Trump, İran'ın savaşı başlattığını ve füzelerin ABD'ye ulaşabileceğini söyledi"),
    ("Trump: Iran Was Two Weeks From A Nuclear Missile", "Trump, İran'ın nükleer füze üretimine iki hafta uzakta olduğunu söyledi"),
    ("12 outlets compared", "12 kaynak karşılaştırıldı"),
    ("how 9 outlets framed it", "9 kaynakta farklı biçimde aktarıldı"),
    ("other Mideast news", "Orta Doğu'dan diğer gelişmeler"),
    ("Inflation Data", "enflasyon verisi"),
    ("Economic Data", "ekonomik veri"),
    ("Oil", "petrol"),
    ("Gold", "altın"),
    ("Silver", "gümüş"),
    ("War", "savaş"),
    ("muhtemelen ilerideki noktada", "bu alanda daha hazırlıklı olabilir"),
    ("mafya bankacılık tuzağını", "mafya finans ağını"),
    ("mafya bankacılık tuzakını", "mafya finans ağını"),
    ("borsa yatırım fonu'leri", "borsa yatırım fonları"),
    ("borsa yatırım fonu'ları", "borsa yatırım fonları"),
    ("taksitler düşer", "getiriler geriledi"),
    ("İkinci ayın içinde ilk kez", "İki ay sonra ilk kez"),
    ("İkinci ayın başından beri ilk kez", "İki ay sonra ilk kez"),
    ("konut kredisi faizleri düşer", "konut kredisi faizleri geriledi"),
    ("taksit faizleri düşerken", "konut kredisi faizleri gerilerken"),
    ("Treasury yields fall", "Hazine tahvil getirileri geriliyor"),
    ("/ Hazine tahvil getirileri geriliyor", ", Hazine tahvil getirileri geriliyor"),
    ("Q3'da", "üçüncü çeyrekte"),
    ("Q3'te", "üçüncü çeyrekte"),
    ("Düşüşe Uşuyor", "düşüş yaşıyor"),
    ("3.7%", "%3,7"),
    ("$81,500", "81.500 dolar"),
    ("3 günlik", "3 günlük"),
    (" / borsa", "; borsa"),
    (" Seviyesine", " seviyesine"),
    (" Geri Dönmeye", " geri dönmeye"),
    (" Geri Dönüyor", " geri dönüyor"),
    ("3%", "%3"),
    ("5%", "%5"),
        ("$81.5K etrafında", "81,5 bin dolar çevresinde"),
        (
            "Update: US Equity Indexes Retreat as AI Trade Falters, Crude Oil Surges Amid Iran's Invasion Warning to Mid-East Neighbors",
            "ABD hisse endeksleri, yapay zekâ işlemleri zayıflarken geriledi; İran'ın Orta Doğu komşularına yönelik işgal uyarısı sürerken ham petrol yükseldi",
        ),
        (
            "Wall Street sinks as Nasdaq falls over 2% on AI cost worries",
            "Yapay zekâ maliyeti endişeleriyle Nasdaq %2'den fazla düşerken Wall Street geriledi",
        ),
        (
            "Tech stocks fall as Nvidia boss warns of AI funding slowdown",
            "Nvidia yöneticisinin yapay zekâ finansmanında yavaşlama uyarısıyla teknoloji hisseleri düştü",
        ),
        (
            "Iran says 7 oil tankers attacked in the Strait of Hormuz as fears grow of a return to war",
            "İran, savaşa dönüş endişeleri artarken Hürmüz Boğazı'nda yedi petrol tankerine saldırıldığını açıkladı",
        ),
)


def _row(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        try:
            return dict(asdict(value))
        except Exception:
            return {}
    # Runtime headlines are Pydantic models.  Without this branch the
    # presentation layer silently saw them as empty rows and could only show
    # the older event-ledger summary, which made the brief look stale.
    if hasattr(value, "model_dump"):
        try:
            result = value.model_dump(mode="json")
            return dict(result) if isinstance(result, Mapping) else {}
        except (TypeError, ValueError):
            try:
                result = value.model_dump()
                return dict(result) if isinstance(result, Mapping) else {}
            except Exception:
                return {}
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict"):
        try:
            result = value.to_dict()
            return dict(result) if isinstance(result, Mapping) else {}
        except Exception:
            return {}
    return {}


def _compact_text(value: Any, limit: int = 360) -> str:
    text = " ".join(str(value or "").split())
    for source, target in _DISPLAY_REPLACEMENTS:
        text = re.sub(re.escape(source), target, text, flags=re.IGNORECASE)
    # Ticker symbols are useful to the engine but distracting in the CFO
    # narrative.  Convert them at the final presentation boundary so the
    # decision and data layers continue using their canonical identifiers.
    for ticker, display_name in _ASSET_NAMES.items():
        text = re.sub(rf"(?<![A-Za-z0-9]){re.escape(ticker)}(?![A-Za-z0-9])", display_name, text, flags=re.IGNORECASE)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    if len(text) <= limit:
        return text
    # Keep a complete first thought rather than cutting a Turkish word in
    # half.  If a sentence is unusually long, use a hard safety bound.
    sentences = [item.strip() for item in text.replace("!", ".").replace("?", ".").split(".") if item.strip()]
    if sentences:
        first = sentences[0]
        if len(first) <= limit:
            return first + "."
    return text[: max(0, limit - 1)].rstrip() + "…"


def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if hasattr(value, "model_dump"):
        try:
            return _jsonable(value.model_dump(mode="json"))
        except (TypeError, ValueError):
            pass
    if hasattr(value, "to_dict"):
        try:
            return _jsonable(value.to_dict())
        except Exception:
            return None
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return value


def _digest(
    *,
    headlines: Iterable[Any] | None,
    world_brief: Mapping[str, Any],
    news_consensus: Mapping[str, Any] | None,
) -> str:
    """Hash only evidence, never generated timestamps or UI state."""
    rows = []
    for headline in headlines or ():
        item = _row(headline)
        rows.append({key: item.get(key) for key in ("id", "source", "ts", "title", "sentiment", "asset_impact", "article_excerpt", "article_fetched_at")})
    timeline = []
    for item in world_brief.get("event_timeline") or ():
        row = _row(item)
        timeline.append({key: row.get(key) for key in ("id", "ts", "source", "title", "phase", "asset_impact")})
    evidence = {
        "headlines": rows,
        "timeline": timeline,
        "timeline_summary": world_brief.get("timeline_summary"),
        "affected_assets": world_brief.get("affected_assets"),
        # Executive text contains live P&L, position counts and calendar
        # wording.  It is intentionally excluded: a market tick must not be
        # misreported as a new-news alert.
        "news_consensus": {
            key: (_row(news_consensus).get(key) if news_consensus else None)
            for key in ("status", "conflicts", "sources", "freshness")
        },
    }
    raw = json.dumps(_jsonable(evidence), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _significant_rows(world_brief: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in world_brief.get("event_timeline") or ():
        row = _row(item)
        if row.get("phase") in {"REVERSAL_OR_ESCALATION", "PEACE_SIGNAL"}:
            rows.append(row)
    return rows


def _significant_key(row: Mapping[str, Any]) -> str:
    return str(row.get("id") or f"{row.get('ts') or ''}|{row.get('title') or ''}")


def _consensus_view(news_consensus: Mapping[str, Any] | None) -> tuple[str, str, list[str]]:
    """Turn source-aware consensus into one readable market conclusion."""
    rows = [
        _row(item)
        for item in (_row(news_consensus).get("assets") or ())
        if isinstance(item, Mapping)
    ]
    conflicts = [_asset_name(row.get("symbol")) for row in rows if row.get("conflict")]
    bullish = [_asset_name(row.get("symbol")) for row in rows if row.get("consensus") == "BULLISH"]
    bearish = [_asset_name(row.get("symbol")) for row in rows if row.get("consensus") == "BEARISH"]
    if conflicts:
        consensus = "Kaynaklar bazı varlıklarda çelişkili; tek yön seçilmedi."
    elif bullish and bearish:
        consensus = "Varlıklar arasında yön ayrışıyor; piyasa geneli nötr/karışık."
    elif bullish:
        consensus = f"Kaynaklar ağırlıkla yukarı yönü destekliyor: {', '.join(bullish[:6])}."
    elif bearish:
        consensus = f"Kaynaklar ağırlıkla aşağı yönü destekliyor: {', '.join(bearish[:6])}."
    else:
        consensus = "Haber kaynakları doğrulanmış yön üretmiyor; fiyat teyidi gerekiyor."
    families = _row(news_consensus).get("independent_source_families")
    stories = _row(news_consensus).get("story_count")
    source_note = f"{families or 0} bağımsız kaynak ailesi, {stories or 0} ayrı haber öyküsü"
    return consensus, source_note, conflicts[:8]


def _conclusion(
    *,
    world_brief: Mapping[str, Any],
    consensus: str,
    conflicts: list[str],
) -> str:
    phases = {
        str(_row(item).get("phase"))
        for item in (world_brief.get("event_timeline") or ())
        if _row(item).get("phase")
    }
    if "REVERSAL_OR_ESCALATION" in phases and "PEACE_SIGNAL" in phases:
        return "Haber akışı karışık: barış beklentisi karşı açıklamalarla dengelenmiş. İlk yön teyitsiz; fiyat ve teknik teyit olmadan pozisyon açılmaz."
    if "REVERSAL_OR_ESCALATION" in phases:
        return "Gerilim haberleri baskın. Risk primi ve emtia tepkisi izlenmeli; teknik teyit olmadan yön seçilmez."
    if "PEACE_SIGNAL" in phases:
        return "Barış/ateşkes sinyali öne çıkıyor. Risk primi azalabilir; piyasa tepkisi teknik teyitle doğrulanmalı."
    if conflicts:
        return f"{', '.join(conflicts[:4])} için kaynak çelişkisi var. Konsensüs oluşmadan işlem görüşü üretilmez."
    return consensus


def _timestamp_value(value: Any) -> datetime:
    """Return a sortable UTC timestamp without making the report fragile."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=UTC)


def _headline_title(row: Mapping[str, Any]) -> str:
    """Choose the already-localized title, with the safe deterministic path."""
    title = str(row.get("title_tr") or row.get("title") or "").strip()
    if not title:
        return "Başlık yok"
    raw_title = str(row.get("title") or "").strip().casefold()
    # A few recurring market-shock headlines have stable wording but their
    # local model translations are demonstrably literal (for example
    # ``kırmızı petrol``).  Use a short, audited presentation translation for
    # these exact event families; the raw source title remains in evidence.
    if raw_title.startswith("update: us equity indexes retreat"):
        return "ABD hisse endeksleri, yapay zekâ işlemleri zayıflarken geriledi; İran'ın Orta Doğu komşularına yönelik uyarısı sürerken ham petrol yükseldi"
    if raw_title.startswith("wall street sinks as nasdaq falls"):
        return "Yapay zekâ maliyeti endişeleriyle Nasdaq yüzde 2'den fazla düşerken Wall Street geriledi"
    if raw_title.startswith("tech stocks fall as nvidia boss warns"):
        return "Nvidia yöneticisinin yapay zekâ finansmanında yavaşlama uyarısıyla teknoloji hisseleri düştü"
    if raw_title.startswith("iran says 7 oil tankers attacked") or raw_title.startswith("iran says 7 tankers attacked"):
        return "İran, savaşa dönüş endişeleri artarken Hürmüz Boğazı'nda tanker saldırısı olduğunu açıkladı"
    if "houthi attacks" in raw_title and "brent" in raw_title:
        return "Husi saldırıları tedarik kesintisi korkusunu artırırken Brent petrol beş ayın zirvesini aştı"
    if "nasdaq" in raw_title and "worst day" in raw_title and "ai" in raw_title:
        return "Yapay zekâ harcamaları ve petrol fiyatları nedeniyle Nasdaq en kötü günlerinden birini yaşadı"
    return _compact_text(
        localize_headline(
            SimpleNamespace(
                title=title,
                title_tr=str(row.get("title_tr") or ""),
            ),
            # Only the four visible development lines use the cached local
            # translator.  This keeps the rest of the cockpit hot path fast
            # while preventing English titles from leaking into the Turkish
            # CFO report (the deterministic dictionary remains the fallback).
            use_model=True,
        ),
        190,
    )


def _enrich_headline_rows(headlines: Iterable[Any] | None) -> tuple[dict[str, Any], ...]:
    """Attach cached article evidence to the one narrative input set.

    Discovery owns bounded fetching; the brief only reads the cache so a
    blocked publisher cannot delay the UI or decision loop.
    """
    source_rows = list(headlines or ())
    try:
        from packages.data.providers.news.article_enrichment import cached

        urls = [getattr(item, "url", None) or _row(item).get("url") for item in source_rows]
        article_rows = cached(urls)
    except Exception:
        article_rows = {}
    output: list[dict[str, Any]] = []
    for item in source_rows:
        row = _row(item)
        url = str(row.get("url") or getattr(item, "url", None) or "").strip()
        article = article_rows.get(url)
        if not article and str(row.get("article_summary") or "").strip():
            summary = str(row.get("article_summary") or "").strip()
            if len(summary) >= 80:
                article = {"status": "RSS_SUMMARY", "excerpt": summary[:1200],
                           "word_count": len(summary.split())}
        if article and article.get("excerpt"):
            row["article_excerpt"] = str(article.get("excerpt") or "")[:1200]
            row["article_status"] = str(article.get("status") or "OK")
            row["article_word_count"] = int(article.get("word_count") or 0)
            row["article_fetched_at"] = article.get("fetched_at")
        output.append(row)
    return tuple(output)


def _article_effect_sentence(row: Mapping[str, Any]) -> str | None:
    """Summarise what the article body adds, without inventing a quote."""
    excerpt = str(row.get("article_excerpt") or "").strip()
    if not excerpt:
        return None
    try:
        from packages.data.providers.news import classify

        text = " ".join(str(row.get(key) or "") for key in ("title", "title_tr", "article_excerpt"))
        sentiment = classify.classify_sentiment(text)
        impacts = classify.classify_asset_impact(text, sentiment)
    except Exception:
        sentiment, impacts = "neutral", {}
    named = [_asset_name(symbol) for symbol, value in impacts.items() if value]
    if not named:
        return "Makale gövdesi okundu; varlık yönü için henüz net bir teyit yok"
    direction = {"bullish": "yukarı", "bearish": "aşağı"}.get(sentiment, "nötr")
    return f"Makale gövdesi değerlendirmesi: {', '.join(named[:4])} üzerinde {direction} baskı işareti; fiyat ve teknik teyit bekleniyor"


def _article_digest(headlines: Iterable[Any] | None) -> str | None:
    """Expose a compact Turkish synthesis of cached article bodies."""
    notes: list[str] = []
    for item in headlines or ():
        row = _row(item)
        note = _article_effect_sentence(row)
        if note and note not in notes:
            notes.append(note)
        if len(notes) >= 3:
            break
    return "; ".join(notes) if notes else None


def _latest_developments(
    *,
    headlines: Iterable[Any] | None,
    world_brief: Mapping[str, Any],
    limit: int = 4,
) -> str:
    """Build the CFO's short ``what changed`` section from canonical evidence.

    Snapshot headlines and the 48-hour event ledger intentionally overlap.  A
    normalized title key keeps one story from being reported twice while still
    allowing a new official counter-statement to appear immediately.
    """
    def priority(row: Mapping[str, Any], *, snapshot: bool) -> int:
        title = " ".join(str(row.get("title") or "").casefold().split())
        explicit_market_shock = any(
            term in title
            for term in (
                "market sell-off", "market selloff", "market crash",
                "wall street sinks", "equity indexes retreat", "nasdaq falls",
                "ai funding slowdown", "ai trade falters", "risk-off",
            )
        )
        geopolitical_shock = any(
            term in title
            for term in (
                "iran war", "iran's invasion", "hormuz", "tanker", "blockade",
                "missile", "airstrike", "war escalat", "houthi attack",
            )
        )
        market_move = any(
            term in title
            for term in (
                "plunge", "plunges", "slump", "tumble", "tumbles", "falls",
                " fall ", "drops", "drop", "retreat from risk", "funding slowdown",
            )
        )
        if explicit_market_shock:
            return 12
        if geopolitical_shock:
            return 10
        if market_move:
            return 8
        if row.get("phase") != "NEWS":
            return 7
        if snapshot and row.get("verified"):
            return 4
        return 2

    candidates: list[dict[str, Any]] = []
    for item in world_brief.get("event_timeline") or ():
        row = _row(item)
        if row.get("title"):
            row["_priority"] = priority(row, snapshot=False)
            candidates.append(row)
    for item in headlines or ():
        row = _row(item)
        if row.get("title"):
            # Verified snapshot rows are the freshest source when the event
            # ledger has not yet caught up with the feed cycle.
            row["_priority"] = priority(row, snapshot=True)
            candidates.append(row)
    candidates.sort(
        key=lambda row: (row.get("_priority", 0), _timestamp_value(row.get("ts"))),
        reverse=True,
    )
    seen: set[str] = set()
    topic_seen: set[str] = set()
    selected: list[str] = []
    for row in candidates:
        key = " ".join(str(row.get("title") or "").casefold().split())
        if not key or key in seen:
            continue
        title = key
        topic = None
        if any(term in title for term in ("nasdaq", "wall street", "equity index")) and any(
            term in title for term in ("ai", "artificial intelligence", "oil", "crude")
        ):
            topic = "equity_ai_oil"
        elif any(term in title for term in ("hormuz", "tanker", "houthi", "blockade")):
            topic = "energy_geopolitical"
        elif any(term in title for term in ("bitcoin", "btc", "ethereum", "crypto")):
            topic = "crypto"
        elif any(term in title for term in ("gold", "silver", "precious metal")):
            topic = "metals"
        if topic and topic in topic_seen:
            seen.add(key)
            continue
        seen.add(key)
        if topic:
            topic_seen.add(topic)
        source = _compact_text(row.get("source") or "Haber kaynağı", 70)
        article_note = _article_effect_sentence(row)
        selected.append(
            f"{source}: {_headline_title(row).rstrip('.!?…')}"
            + (f" — {article_note}" if article_note else "")
        )
        if len(selected) >= limit:
            break
    if not selected:
        return "Yeni doğrulanmış kritik gelişme yok; mevcut akış izleniyor."
    return "; ".join(selected)


def _actor_updates(
    *,
    headlines: Iterable[Any] | None,
    world_brief: Mapping[str, Any],
    limit: int = 3,
) -> str | None:
    """Expose actor/country developments without inventing an official quote.

    The source headline is deliberately retained after the actor label.  If a
    feed only reports a claim (rather than an official statement), the report
    says so through the title itself instead of upgrading it to fact.
    """
    rows: list[dict[str, Any]] = []
    rows.extend(_row(item) for item in world_brief.get("event_timeline") or ())
    rows.extend(_row(item) for item in headlines or ())
    rows.sort(key=lambda row: _timestamp_value(row.get("ts")), reverse=True)
    buckets = (
        ("İran/Hormuz", ("hormuz", "tanker", "iran war", "iran's invasion", "iran says")),
        ("ABD/Trump", ("trump", "white house")),
        ("Rusya-Ukrayna", ("russia", "kyiv", "ukraine", "zelensky")),
        ("Suudi Arabistan/Yemen", ("saudi", "houthi", "yemen")),
        ("İsrail", ("israel", "israeli")),
        ("Çin", ("china", "chinese")),
    )
    updates: list[str] = []
    seen: set[str] = set()
    used_titles: set[str] = set()
    for label, terms in buckets:
        candidates: list[tuple[int, datetime, dict[str, Any]]] = []
        for row in rows:
            title = str(row.get("title") or "").strip()
            folded = title.casefold()
            if not title or label in seen or title in used_titles:
                continue
            if not any(term in folded for term in terms):
                continue
            statement_terms = (
                "says", "said", "warns", "warned", "threatens", "threatened",
                "statement", "announced", "declared", "claims", "claimed",
            )
            if not any(term in folded for term in statement_terms):
                continue
            if label == "İran/Hormuz" and "tanker" in folded and not any(
                term in folded for term in (
                    "iran", "attack", "attacked", "says", "war", "warning", "threat",
                )
            ):
                continue
            # A headline mentioning Trump's stance on Russia is not, by
            # itself, a Russian government statement.  Require an explicit
            # conflict/official context before assigning it to a country.
            if label == "ABD/Trump" and not (
                "white house" in folded
                or any(term in folded for term in ("iran", "escalat", "comments", "threat"))
            ):
                continue
            if label == "Rusya-Ukrayna" and not any(
                term in folded for term in ("missile", "attack", "bombard", "strike", "deadly", "russia says", "zelensky says")
            ):
                continue
            score = 1
            if label == "İran/Hormuz" and any(term in folded for term in ("hormuz", "tanker", "iran says")):
                score = 4
            elif label == "ABD/Trump" and any(term in folded for term in ("iran", "escalat", "comments", "threat", "white house")):
                score = 4
            elif label == "Rusya-Ukrayna" and any(term in folded for term in ("missile", "bombard", "russia says", "zelensky says")):
                score = 4
            candidates.append((score, _timestamp_value(row.get("ts")), row))
        if not candidates:
            continue
        _score, _timestamp, row = max(candidates, key=lambda item: (item[0], item[1]))
        title = str(row.get("title") or "")
        localized = _headline_title(row)
        updates.append(f"{label}: {localized.rstrip('.!?…')}")
        seen.add(label)
        used_titles.add(title)
        if len(updates) >= limit:
            break
    if not updates:
        return None
    return "; ".join(updates)


def _shock_explanation(
    *,
    headlines: Iterable[Any] | None,
    world_brief: Mapping[str, Any],
) -> str | None:
    """Explain a simultaneous risk-off move only when both legs are evidenced."""
    titles = " ".join(
        str(_row(item).get("title") or "").casefold()
        for item in (*tuple(headlines or ()), *(world_brief.get("event_timeline") or ()))
    )
    has_geopolitical = any(term in titles for term in ("iran", "hormuz", "war", "blockade", "tanker"))
    has_risk_off = any(
        term in titles
        for term in (
            "market sell-off", "market selloff", "wall street sinks", "nasdaq falls",
            "ai funding slowdown", "ai trade falters", "risk-off", "retreat from risk",
        )
    )
    if has_geopolitical and has_risk_off:
        return (
            "İran savaşı/Hormuz kaynaklı enerji ve enflasyon riski ile yüksek "
            "yapay zekâ harcamasının finansmanına ilişkin endişe aynı anda risk iştahını bozdu; "
            "bu yüzden teknoloji ve kripto satışı, petrolde yukarı baskı görüldü."
        )
    if has_risk_off:
        return "Riskten kaçış ve teknoloji/finansman endişesi başlıkları aynı anda yoğunlaştı; fiyat teyidi ayrıca izleniyor."
    if has_geopolitical:
        return "Jeopolitik ve enerji arzı riski öne çıktı; fiyat hareketinin kalıcılığı teknik teyit bekliyor."
    return None


def _market_move_text() -> str | None:
    """Read cached completed daily bars for a factual move cross-check.

    This is narrative-only and cache-only: it never fetches data, changes a
    decision, or opens an order.  Missing/stale bars are omitted rather than
    estimated, so the brief cannot invent a percentage move.
    """
    try:
        from packages.data.providers.ohlcv import cache as ohlcv_cache
    except Exception:
        return None
    moves: list[tuple[float, str]] = []
    for symbol in ("SP500", "NVDA", "XAGUSD", "XAUUSD", "BTCUSD", "ETHUSD", "BRENT"):
        try:
            cached = ohlcv_cache.load(symbol, "1d")
            bars = cached.bars if cached is not None and cached.fresh else []
            if len(bars) < 2 or not bars[-2].close:
                continue
            pct = (float(bars[-1].close) - float(bars[-2].close)) / float(bars[-2].close) * 100.0
        except (TypeError, ValueError, OSError):
            continue
        if abs(pct) >= 1.0:
            moves.append((abs(pct), f"{symbol} {pct:+.1f}%".replace(".", ",")))
    if not moves:
        return None
    moves.sort(reverse=True)
    return "Son tamamlanan günlük bar teyidi: " + ", ".join(text for _, text in moves[:6]) + "."


def _market_effect_text(
    *,
    consensus: str,
    assets: list[str],
    conflicts: list[str],
) -> str:
    """Explain the market consequence in investor language, not data labels."""
    asset_text = ", ".join(_asset_name(item) for item in assets[:8]) if assets else "henüz belirgin bir varlık"
    if conflicts:
        conflict_text = ", ".join(conflicts[:5])
        return (
            f"Fiyat tarafında ortak yön henüz oluşmadı. Haberlerin en çok etkilediği "
            f"varlıklar {asset_text}; {conflict_text} için kaynaklar birbirini doğrulamıyor. "
            "İlk hareket haberle gelebilir, kalıcı yönü fiyat ve teknik teyit belirleyecek."
        )
    if "yukarı" in consensus.casefold() and "aşağı" not in consensus.casefold():
        return f"Piyasa etkisi ağırlıkla yukarı yönlü görünüyor; ilk izlenecek varlıklar {asset_text}."
    if "aşağı" in consensus.casefold() and "yukarı" not in consensus.casefold():
        return f"Piyasa etkisi ağırlıkla aşağı yönlü görünüyor; ilk izlenecek varlıklar {asset_text}."
    return f"Piyasa etkisi karışık veya teyitsiz; haber zinciri özellikle {asset_text} üzerinde izleniyor."


def _evidence_sentence(world_brief: Mapping[str, Any], assets: list[str]) -> str | None:
    """Turn the structured world-event fallback into CFO language."""
    raw = " ".join(str(world_brief.get("summary") or "").split()).strip()
    if not raw or raw.startswith("Yeni haber akışında") or raw.startswith("Yeni doğrulanmış"):
        return None
    match = re.search(
        r"(?P<event>.+?)\s+için doğrulanmış kanıt bulundu\.\s*"
        r"Kaynak güveni\s+(?P<confidence>0?\.\d+|1(?:\.0+)?)\s*;\s*"
        r"etkilenen adaylar:\s*(?P<assets>.+?)\.?$",
        raw,
        flags=re.IGNORECASE,
    )
    if match:
        confidence = float(match.group("confidence"))
        confidence_text = f"%{round(confidence * 100):.0f}" if confidence <= 1 else f"%{round(confidence):.0f}"
        event = _compact_text(match.group("event"), 140)
        event = re.sub(r"^Inflation Data$", "Enflasyon verisi", event, flags=re.IGNORECASE)
        affected = ", ".join(_asset_name(item) for item in assets[:8]) or _compact_text(match.group("assets"), 180)
        return (
            f"{event} için doğrulanmış kanıt var; kanıt güveni {confidence_text}. "
            f"Bu gelişme {affected} üzerinde etkili olabilir."
        )
    return _compact_text(raw, 360)


def _clean_watch_items(items: Iterable[Any] | None) -> list[str]:
    """Keep only user-facing follow-ups; never expose internal diagnostics."""
    cleaned: list[str] = []
    for item in items or ():
        text = _compact_text(item, 180)
        folded = text.casefold()
        if not text or any(
            marker in folded
            for marker in (
                "graph_no_", "graph_", "dqs:", "missing_", "internal", "provider_",
                "forecast_", "scenario_", "no_entity_match", "warning:",
                "baseline_", "at_risk_", "verified_observation", "entity_match",
            )
        ):
            continue
        if "varlıklar:" in folded:
            continue
        # Machine identifiers generally look like ``namespace:value``.  Keep
        # normal prose such as ``Kaynak: Reuters`` but hide diagnostics.
        if re.match(r"^[a-z][a-z0-9_]{2,}:\S+", folded):
            continue
        if text not in cleaned:
            cleaned.append(text)
    if not cleaned:
        cleaned = [
            "Yeni resmi açıklama ve bağımsız kaynak teyidi",
            "Etkilenen varlıkların fiyat ve teknik tepkisi",
        ]
    return cleaned[:3]


_BLOCKER_LABELS = {
    "confidence_floor": "güven eşiği",
    "entry_quality_v2:entry_quality": "giriş kalitesi",
    "entry_quality_v2:reversal_risk": "tersine dönüş riski",
    "catalyst_risk:NO_POSITION_INCREASE": "yoğunlaşma / yeni giriş limiti",
    "ev_gate": "beklenen değer",
    "stale_ohlcv": "bayat fiyat verisi",
    "news_confluence": "haber–teknik teyit",
    "correlation": "korelasyon limiti",
    "risk_gate": "risk kapısı",
}

_ASSET_NAMES = {
    "XAGUSD": "gümüş",
    "XAUUSD": "altın",
    "BRENT": "Brent petrol",
    "WTI": "WTI petrol",
    "BTCUSD": "Bitcoin",
    "ETHUSD": "Ethereum",
    "DXY": "ABD doları endeksi",
    "SP500": "S&P 500",
    "US10Y": "ABD 10 yıllık tahvili",
    "VIX": "oynaklık endeksi",
}


def _asset_name(value: Any) -> str:
    """Use investor-facing asset names in the narrative, never ticker codes."""
    raw = str(value or "").strip()
    return _ASSET_NAMES.get(raw.upper(), raw or "belirtilmeyen varlık")


def _candidate_strength(row: Mapping[str, Any]) -> float:
    """Normalize bullish/bearish scores to one investor-facing strength."""
    try:
        explicit = row.get("directional_strength")
        if explicit is not None:
            return max(0.0, min(100.0, float(explicit)))
        raw = max(0.0, min(100.0, float(row.get("score") or 0.0)))
    except (TypeError, ValueError):
        return 0.0
    direction = str(row.get("direction") or "").casefold()
    return 100.0 - raw if direction in {"bearish", "down", "short"} else raw


def _directional_threshold() -> float:
    try:
        from packages.data.registry.loader import load_thresholds

        return float((load_thresholds().get("consensus") or {}).get("bullish_min", 55))
    except (TypeError, ValueError, AttributeError):
        return 55.0


def _operational_summary(
    *,
    agent_brief: Mapping[str, Any] | None,
    decision_matrix: Mapping[str, Any] | None,
    news_consensus: Mapping[str, Any] | None,
) -> str:
    """Turn the canonical decision read model into a CFO decision paragraph.

    This is presentation-only.  It never changes an action, threshold, order,
    or RiskGate result; it simply tells the owner why the same cycle did or did
    not produce a paper position.
    """
    brief = dict(agent_brief or {})
    positions = int(brief.get("open_paper_positions") or 0)
    auto_open = dict(brief.get("auto_open") or {})
    ready = [
        row for row in (brief.get("top_candidates") or [])
        if bool(row.get("execution_ready") or row.get("actionable"))
    ]
    # A matrix-ready row is not an opened paper position when the worker's
    # final news-confluence gate is enabled.  Use the canonical gate summary so
    # the CFO text cannot announce an order that the ledger never contains.
    if auto_open.get("enabled") and auto_open.get("available"):
        if int(auto_open.get("ready_count") or 0) == 0:
            ready = []
        elif int(auto_open.get("ready_count") or 0) < len(ready):
            ready_keys = {
                (item.get("symbol"), item.get("timeframe"), item.get("side"))
                for item in (auto_open.get("ready") or [])
            }
            ready = [
                row
                for row in ready
                if (
                    row.get("symbol"),
                    row.get("timeframe"),
                    "long" if str(row.get("direction")).casefold() in {"bullish", "up", "long"} else "short",
                ) in ready_keys
            ]
    raw_blockers = [str(item) for item in (brief.get("top_blockers") or []) if item]
    labels: list[str] = []
    for raw in raw_blockers:
        label = _BLOCKER_LABELS.get(raw)
        if label is None:
            # Prefixes preserve meaning while avoiding internal identifiers in
            # the user-facing CFO report.
            label = next(
                (name for key, name in _BLOCKER_LABELS.items() if raw.startswith(key)),
                None,
            )
        if label and label not in labels:
            labels.append(label)
    if not labels and brief.get("main_blocker", {}).get("label"):
        labels.append(str(brief["main_blocker"]["label"]))
    if auto_open.get("blocked_count") and "haber–teknik teyit" not in labels:
        labels.insert(0, "haber–teknik teyit")
    if labels:
        blocker_text = ", ".join(labels[:4])
    else:
        blocker_text = "aktif bir işlem engeli yok"

    if ready:
        candidate = ready[0]
        direction = "yukarı" if str(candidate.get("direction")).casefold() in {"bullish", "up", "long"} else "aşağı"
        opportunity = (
            f"En yakın aday {_asset_name(candidate.get('symbol'))} için {direction} yönlü; "
            "son güvenlik doğrulaması bekleniyor."
        )
    else:
        candidates = [row for row in (brief.get("top_candidates") or []) if row.get("symbol")]
        if candidates:
            candidate = candidates[0]
            direction = "yukarı" if str(candidate.get("direction")).casefold() in {"bullish", "up", "long"} else "aşağı"
            strength = _candidate_strength(candidate)
            threshold = _directional_threshold()
            if strength >= threshold and auto_open.get("blocked_count"):
                status_text = (
                    f"sinyal gücü {strength:.0f}/100 ile işlem eşiğini geçti, "
                    "ancak son haber-teknik kapıda bekliyor"
                )
            elif strength >= threshold:
                status_text = f"sinyal gücü {strength:.0f}/100 ile işlem eşiğini geçti"
            else:
                status_text = (
                    f"sinyal gücü {strength:.0f}/100; işlem eşiğine "
                    f"{threshold - strength:.1f} puan eksik"
                )
            opportunity = (
                f"En yakın aday {_asset_name(candidate.get('symbol'))} için {direction} yönlü; "
                f"{status_text}."
            )
        else:
            opportunity = "Bu çevrimde işlem adayı oluşmadı; yeni haber ve taze fiyat teyidi bekleniyor."

    board = _row(news_consensus).get("idea_board") or {}
    idea_count = board.get("ideas")
    if idea_count is not None:
        if int(idea_count or 0) == 0:
            discovery_text = "Yeni varlık adayı yok; son taramada yeterli fırsat oluşmadı."
        else:
            discovery_text = f"{int(idea_count)} yeni varlık adayı izleniyor; bunlar henüz işlem emri değildir."
    else:
        discovery_text = "Asset keşfi ayrı döngüde izleniyor; bu rapora aday teyidi gelmedi."

    if positions:
        portfolio_text = f"Portföyde {positions} açık simülasyon pozisyonu var."
    elif ready:
        portfolio_text = "Portföy boş; uygun aday için son doğrulama bekleniyor."
    else:
        portfolio_text = "Portföy boş; bu çevrimde güvenli açılış koşulu oluşmadı."
    if ready:
        decision_text = "İşlem adayı var"
    elif auto_open.get("blocked_count"):
        decision_text = "Sinyal var ama işlem açılmadı"
    else:
        decision_text = "Şu anda işlem açmıyorum"
    return (
        f"{decision_text}. {portfolio_text} "
        f"{opportunity} Bu kararın nedeni: {blocker_text}. {discovery_text}"
    )


def _cfo_report(
    *,
    headlines: Iterable[Any] | None,
    world_brief: Mapping[str, Any],
    consensus: str,
    conclusion: str,
    conflicts: list[str],
    assets: list[str],
    watch: list[str],
    agent_brief: Mapping[str, Any] | None = None,
    decision_matrix: Mapping[str, Any] | None = None,
    news_consensus: Mapping[str, Any] | None = None,
) -> str:
    """One readable executive report; the UI intentionally renders this whole."""
    timeline_summary = _compact_text(
        world_brief.get("timeline_summary")
        or world_brief.get("summary")
        or "Piyasa haber akışı izleniyor.",
        430,
    )
    developments = _latest_developments(headlines=headlines, world_brief=world_brief)
    article_digest = _article_digest(headlines)
    shock = _shock_explanation(headlines=headlines, world_brief=world_brief)
    actors = _actor_updates(headlines=headlines, world_brief=world_brief)
    market_moves = _market_move_text()
    evidence = _evidence_sentence(world_brief, assets)
    # A stale/orthogonal world-summary sentence must not displace the
    # headline-backed market-shock explanation.  Keep only evidence that is
    # semantically related to the current risk chain.
    if evidence and shock and not any(
        term in evidence.casefold()
        for term in ("jeopolit", "iran", "hormuz", "enerji", "savaş", "enflasyon", "petrol", "yapay zekâ")
    ):
        evidence = None
    market = _market_effect_text(
        consensus=consensus,
        assets=assets,
        conflicts=conflicts,
    )
    watch_text = ", ".join(_clean_watch_items(watch))
    opening = shock or timeline_summary
    paragraphs = [
        f"CFO kararı: {_operational_summary(agent_brief=agent_brief, decision_matrix=decision_matrix, news_consensus=news_consensus)}",
        f"Piyasa görünümü: {opening}",
        *([f"Kanıt tabanı: {evidence}"] if evidence else []),
        f"Güncel gelişmeler: {developments}.",
        *([f"Makale değerlendirmesi: {article_digest}."] if article_digest else []),
        *([f"Fiyat tepkisi: {market_moves}"] if market_moves else []),
        *([f"Aktörler: {actors}."] if actors else []),
        f"Piyasa etkisi: {market}",
        f"Yönetim kararı: {_compact_text(conclusion, 360)}",
    ]
    if watch_text:
        paragraphs.append(f"Takip edilecekler: {_compact_text(watch_text, 260)}.")
    return "\n\n".join(paragraphs)[:2100]


def _deterministic_report(
    *,
    world_brief: Mapping[str, Any],
    changed: bool,
    significant_rows: list[dict[str, Any]],
) -> tuple[str, str, list[str]]:
    timeline_summary = str(world_brief.get("timeline_summary") or "").strip()
    # The executive text contains live decision signals, position counts and
    # internal labels.  Premium brief is a source synthesis, so it must not
    # repeat that separate operational message as its headline.
    narrative = str(world_brief.get("summary") or "").strip()
    if not narrative:
        narrative = "Yeni doğrulanmış haber etkisi yok; mevcut kanıtlar izleniyor."
    report = f"Haber özeti: {_compact_text(timeline_summary or narrative, 480)}"
    if timeline_summary and narrative and timeline_summary not in narrative:
        report += f" Kanıt: {_compact_text(narrative, 260)}"
    if not changed:
        mode = "STEADY"
    elif significant_rows:
        mode = "ALERT"
    else:
        mode = "DELTA"
    assets = [str(item) for item in (world_brief.get("affected_assets") or ()) if item]
    watch = [
        "Yeni bağımsız kaynak ve resmi açıklama teyidi",
        "İlgili varlığın fiyat/volatilite tepkisi",
    ]
    if assets:
        watch.insert(1, f"İzlenen varlıklar: {', '.join(_asset_name(item) for item in assets[:6])}")
    return mode, report[:1800], watch[:3]


def _run_ai(
    *,
    headlines: tuple[Any, ...],
    world_state: Any,
    causal_shadow: Any,
    portfolio_risk: Any,
    risk_gate: Mapping[str, Any] | None,
    dqs: Mapping[str, Any] | None,
) -> dict[str, Any]:
    # Reuse the canonical world-report prompt and cache.  This is the only
    # model call in this module and is never executed on the HTTP thread.
    result: list[dict[str, Any] | None] = [None]

    def call() -> None:
        result[0] = build_world_brief(
            headlines=headlines,
            world_state=world_state,
            causal_shadow=causal_shadow,
            portfolio_risk=portfolio_risk,
            risk_gate=risk_gate,
            dqs=dqs,
            allow_llm=True,
        )

    worker = threading.Thread(target=call, name="premium-world-report", daemon=True)
    worker.start()
    # The local Qwen model may need ~15–30 s on a cold GPU load.  This wait is
    # inside a daemon worker, never the HTTP request, and is long enough to let
    # the configured local model produce the premium rewrite in normal use.
    worker.join(45.0)
    if result[0] is not None:
        return result[0]
    # A provider that exceeds the narrative budget must not leave the premium
    # status stuck at UPDATING forever.  The canonical deterministic report is
    # still returned, and the timed-out daemon may populate the normal cache
    # later without affecting decisions.
    return build_world_brief(
        headlines=headlines,
        world_state=world_state,
        causal_shadow=causal_shadow,
        portfolio_risk=portfolio_risk,
        risk_gate=risk_gate,
        dqs=dqs,
        allow_llm=False,
    )


def _submit_ai(*, digest: str, kwargs: dict[str, Any]) -> Future[dict[str, Any]]:
    """Start one daemon worker so CLI/tests never wait for model shutdown."""
    future: Future[dict[str, Any]] = Future()

    def run() -> None:
        try:
            future.set_result(_run_ai(**kwargs))
        except Exception as exc:  # pragma: no cover - provider-specific
            future.set_exception(exc)

    threading.Thread(
        target=run,
        name=f"premium-brief-llm-{digest}",
        daemon=True,
    ).start()
    return future


def build_premium_brief(
    *,
    headlines: Iterable[Any] | None,
    world_brief: Mapping[str, Any],
    news_consensus: Mapping[str, Any] | None = None,
    world_state: Any = None,
    causal_shadow: Any = None,
    portfolio_risk: Any = None,
    risk_gate: Mapping[str, Any] | None = None,
    dqs: Mapping[str, Any] | None = None,
    agent_brief: Mapping[str, Any] | None = None,
    decision_matrix: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a concise delta report and schedule an AI rewrite if needed."""
    global _AI_FUTURE, _AI_FUTURE_DIGEST, _LAST_AI_DIGEST, _LAST_AI_RESULT, _LAST_DIGEST, _LAST_SIGNIFICANT_KEYS
    headline_rows = _enrich_headline_rows(headlines)
    digest = _digest(
        headlines=headline_rows,
        world_brief=world_brief,
        news_consensus=news_consensus,
    )
    with _LOCK:
        if _AI_FUTURE is not None and _AI_FUTURE.done():
            completed_digest = _AI_FUTURE_DIGEST
            try:
                result = _AI_FUTURE.result()
                if isinstance(result, Mapping):
                    _LAST_AI_RESULT = dict(result)
            except Exception:
                # The deterministic report remains the safe source of truth.
                pass
            # Remember a failed attempt too; otherwise a provider outage would
            # cause a model retry on every ten-second cockpit poll.
            _LAST_AI_DIGEST = completed_digest
            _AI_FUTURE = None
            _AI_FUTURE_DIGEST = None

        initial = _LAST_DIGEST is None
        changed = digest != _LAST_DIGEST
        all_significant = _significant_rows(world_brief)
        significant_keys = {_significant_key(row) for row in all_significant}
        new_significant = [
            row for row in all_significant if _significant_key(row) not in _LAST_SIGNIFICANT_KEYS
        ] if not initial else []
        # Never overlap model calls.  If evidence changes while the previous
        # rewrite is running, the next cockpit poll schedules the newest
        # digest after that worker completes.
        if _AI_FUTURE is None and _LAST_AI_DIGEST != digest:
            _AI_FUTURE_DIGEST = digest
            _AI_FUTURE = _submit_ai(
                digest=digest,
                kwargs={
                    "headlines": headline_rows,
                    "world_state": world_state,
                    "causal_shadow": causal_shadow,
                    "portfolio_risk": portfolio_risk,
                    "risk_gate": risk_gate,
                    "dqs": dqs,
                },
            )
        _LAST_DIGEST = digest
        _LAST_SIGNIFICANT_KEYS = significant_keys
        ai_result = dict(_LAST_AI_RESULT) if _LAST_AI_DIGEST == digest and _LAST_AI_RESULT else None
        ai_pending = _AI_FUTURE is not None and _AI_FUTURE_DIGEST == digest

    mode, _fallback_report, watch = _deterministic_report(
        world_brief=world_brief,
        changed=changed,
        significant_rows=new_significant,
    )
    alert = None
    if changed and new_significant:
        row = new_significant[0]
        title = _compact_text(localize_headline(
            SimpleNamespace(title=str(row.get("title") or "başlık yok")),
            use_model=True,
        ), 420)
        alert = (
            "Son dakika açıklama geldi, dikkat: "
            f"{row.get('source') or 'kaynak'} — {title}"
        )[:600]
    # The public report is always the same source-aware CFO narrative.  The
    # optional model rewrite remains cached metadata; letting a short model
    # response replace the narrative would hide the latest headlines and make
    # the panel look different on every poll.
    report_source = "deterministic"
    ai_status = "UPDATING" if ai_pending else "FALLBACK"
    if ai_result:
        report_source = str(ai_result.get("source") or "fallback")
        ai_status = "READY" if report_source == "llm" else "FALLBACK"
        watch = _clean_watch_items(ai_result.get("what_to_watch") or watch)
    else:
        watch = _clean_watch_items(watch)
    consensus, source_note, conflicts = _consensus_view(news_consensus)
    conclusion = _conclusion(
        world_brief=world_brief,
        consensus=consensus,
        conflicts=conflicts,
    )
    assets = [str(item) for item in (world_brief.get("affected_assets") or ()) if item][:12]
    market_effect = _market_effect_text(
        consensus=consensus,
        assets=assets,
        conflicts=conflicts,
    )
    report = _cfo_report(
        headlines=headline_rows,
        world_brief=world_brief,
        consensus=consensus,
        conclusion=conclusion,
        conflicts=conflicts,
        assets=assets,
        watch=watch,
        agent_brief=agent_brief,
        decision_matrix=decision_matrix,
        news_consensus=news_consensus,
    )
    # Backward-compatible empty-feed behavior: when there is no snapshot or
    # consensus payload at all, a ready model summary is the only available
    # narrative.  A normal cockpit cycle has both and always uses the full CFO
    # report above so no headline is hidden by a short rewrite.
    if ai_result and report_source == "llm" and not headline_rows and not _row(news_consensus).get("assets"):
        report = _compact_text(ai_result.get("summary") or report, 720)
    return {
        "status": "OK",
        "mode": mode,
        "changed": changed,
        "alert": alert,
        "main_idea": report,
        "conclusion": conclusion,
        "market_effect": market_effect,
        "consensus": consensus,
        "source_note": source_note,
        "conflicts": conflicts,
        "report": report,
        "watch": watch,
        "affected_assets": assets,
        "evidence_digest": digest,
        "evidence_count": len(headline_rows) + len(world_brief.get("event_timeline") or ()),
        "headline_count": len(headline_rows),
        "story_count": _row(news_consensus).get("story_count"),
        "independent_source_families": _row(news_consensus).get("independent_source_families"),
        "source_count": len(
            {
                str(_row(item).get("source") or "")
                for item in (*headline_rows, *(world_brief.get("event_timeline") or ()))
                if _row(item).get("source")
            }
        ),
        "updated_at": datetime.now(UTC).isoformat(),
        "ai": {
            "status": ai_status,
            "source": report_source,
            "cached": bool(ai_result),
        },
        "execution": "NO_EXECUTION",
    }


__all__ = ["build_premium_brief"]
