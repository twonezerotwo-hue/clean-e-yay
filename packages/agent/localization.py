"""Kullanıcıya ve Piper'a giden kısa metinleri Türkçeleştiren sunum katmanı.

Bu modül karar üretmez ve karar state'ini değiştirmez. Haber başlıklarının
``title_tr`` alanı boş olduğunda önce yerel Ollama çevirisi denenir; model
ulaşılamıyorsa deterministik sözlük yedeği kullanılır. Böylece brief'in ekrana
ve sese giden metni İngilizce/Türkçe karışımına düşmez.
"""
from __future__ import annotations

import re
from functools import lru_cache

from packages.agent.llm import client as llm_client

_ENGLISH_MARKERS = re.compile(
    r"\b(?:the|and|of|to|in|on|for|as|amid|after|before|may|warns|"
    r"price|prices|market|markets|oil|gold|silver|news|today|latest|"
    r"turns|higher|lower|investors|outlook|war|attack|strike|report|"
    r"calls|without|talks|ticks|up|but|jitters|limit|upside|here|"
    r"what|happened|crypto)\b",
    re.IGNORECASE,
)

# Sık görülen piyasa/rapor etiketleri için LLM olmasa da anlaşılır çıktı.
_PHRASE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("Here’s what happened in crypto today", "Bugün kripto piyasasında yaşananlar"),
    ("Here's what happened in crypto today", "Bugün kripto piyasasında yaşananlar"),
    ("Big Tech", "büyük teknoloji şirketleri"),
    ("may leave", "riske atabilir"),
    ("crypto bots exposed", "kripto botlarını açıkta bırakabilir"),
    ("CertiK warns", "CertiK uyarıyor"),
    ("Gold turns higher as oil prices dip", "Petrol fiyatları düşerken altın yükseliyor"),
    ("investors eye Fed rate outlook", "yatırımcılar Fed'in faiz görünümünü izliyor"),
    ("Israel's election may change its leader, but not Iran war policy", "İsrail seçimleri liderini değiştirebilir, ancak İran savaş politikasını değil"),
    ("What Falling USDT Supply Means for Bitcoin’s Price Recovery", "Düşen USDT arzı Bitcoin'in fiyat toparlanması için ne anlama geliyor"),
    ("What Falling USDT Supply Means for Bitcoin's Price Recovery", "Düşen USDT arzı Bitcoin'in fiyat toparlanması için ne anlama geliyor"),
    ("Breaking News", "son dakika haberi"),
    ("Latest News and Videos", "son haberler ve videolar"),
    ("White House event", "Beyaz Saray etkinliği"),
    ("White House", "Beyaz Saray"),
    ("US Treasury", "ABD Hazinesi"),
)

_TOKEN_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\bbullish\b", "yukarı yönlü"),
    (r"\bbearish\b", "aşağı yönlü"),
    (r"\bneutral\b", "nötr"),
    (r"\bLONG\b", "alış"),
    (r"\bSHORT\b", "satış"),
    (r"\bWATCH\b", "izlemede"),
    (r"\bHOLD\b", "beklemede"),
    (r"\bNFP\b", "tarım dışı istihdam verisi"),
    (r"\bCPI\b", "enflasyon verisi"),
    (r"\bAI\b", "yapay zekâ"),
    (r"\bETF\b", "borsa yatırım fonu"),
    (r"\bDQS\b", "veri kalitesi"),
    (r"\bPnL\b", "kâr-zarar"),
    (r"\bpaper[_ -]?only\b", "yalnızca kâğıt üzerinde"),
    (r"\bno[_ -]?execution\b", "gerçek emir yok"),
)


def _looks_english(text: str) -> bool:
    if not text or not text.strip():
        return False
    if len(_ENGLISH_MARKERS.findall(text)) >= 1:
        return True
    # Bazı sağlayıcı başlıklarında yalnızca şirket/ETF adları ve İngilizce
    # fiiller bulunur; dar sözlük bunları kaçırmamalı. Türkçeye özgü harfler
    # yoksa dört veya daha fazla kelimelik başlık yerel çeviri adayıdır.
    folded = text.casefold()
    if re.search(r"[çğıöşüİ]", folded):
        return False
    words = re.findall(r"[a-z]{3,}", folded)
    return len(words) >= 4


def _deterministic_turkish(text: str) -> str:
    result = " ".join(str(text or "").split()).strip()
    for source, target in _PHRASE_REPLACEMENTS:
        result = result.replace(source, target)
    for pattern, target in _TOKEN_REPLACEMENTS:
        result = re.sub(pattern, target, result, flags=re.IGNORECASE)
    return result


def _translation_candidate(value: str) -> str:
    # Modeller bazen başlığın altına açıklama ekler; yalnızca ilk satır başlık
    # olarak alınır, böylece İngilizce/uzun ek metin rapora sızmaz.
    first_line = next((line.strip() for line in value.splitlines() if line.strip()), "")
    candidate = " ".join(first_line.replace('"', "").split()).strip().strip("`*_ ")
    # Bazı yerel modeller sistem yönergesini başlığa ekleyebiliyor. Bu artık
    # rapor/ses metnine taşınmamalı; yalnızca başlık kısmını koru.
    return re.sub(r"\s*/(?:no_stops?|no_stop)\b.*$", "", candidate, flags=re.IGNORECASE).strip()


def _valid_translation(value: str, original: str) -> bool:
    candidate = _translation_candidate(value)
    if not candidate or len(candidate) > max(260, len(original) * 3):
        return False
    # Modelin İngilizce cümleyi aynen geri döndürmesini kabul etme.
    folded_candidate = candidate.casefold()
    folded_original = original.casefold()
    if folded_candidate == folded_original or folded_original in folded_candidate:
        return False
    # Türkçe cümlede tek bir özel isim olabilir; iki veya daha fazla İngilizce
    # bağlaç/fiil kalıyorsa model başlığı çevirmemiş kabul edilir.
    if len(_ENGLISH_MARKERS.findall(candidate)) >= 2:
        return False
    return True


@lru_cache(maxsize=512)
def localize_news_title(title: str) -> str:
    """Bir haber başlığını Türkçe sunum metnine çevirir.

    Çeviri yalnızca başlık gösterimi/seslendirmesi içindir; karar motorunun ham
    ``title`` alanı ve kanıt zinciri değişmez.
    """
    original = " ".join(str(title or "").split()).strip()
    if not original or not _looks_english(original):
        return original

    local = llm_client.get_local_client()
    if local is not None:
        completion = local.complete(
            "Yalnızca Türkçe tek satırlık haber başlığı üret; en fazla 18 kelime. Açıklama, tırnak ve İngilizce cümle ekleme.",
            f"Başlığı Türkçeye çevir:\n{original}",
            max_tokens=80,
            temperature=0.1,
        )
        if completion is not None and _valid_translation(completion.text, original):
            return _deterministic_turkish(_translation_candidate(completion.text))
    return _deterministic_turkish(original)


def localize_headline(item: object, *, use_model: bool = True) -> str:
    """NewsHeadline benzeri nesneden Türkçe başlık seç."""
    title_tr = getattr(item, "title_tr", None)
    if isinstance(title_tr, str) and title_tr.strip():
        normalized = " ".join(title_tr.split()).strip()
        # Sağlayıcı bazı kayıtlarda title_tr alanına ham İngilizce başlığı
        # kopyalayabiliyor. Alan adı Türkçe olsa da sunumda onu olduğu gibi
        # gösterme; aynı yerel çeviri yolundan geçir.
        if _looks_english(normalized) and use_model:
            return localize_news_title(normalized)
        return _deterministic_turkish(normalized)
    title = str(getattr(item, "title", None) or getattr(item, "headline", ""))
    if use_model:
        return localize_news_title(title)
    return _deterministic_turkish(title)


def localize_text(text: object) -> str:
    """Kısa rapor parçalarındaki bilinen İngilizce etiketleri temizle."""
    result = _deterministic_turkish(str(text or ""))
    # Haber kanıtı ve takvim etiketleri serbest metin olabilir. Kısa ve
    # İngilizce görünen parçaları yerel modelle çevir; model yoksa üstteki
    # deterministik sözlük yine güvenli bir yedek olarak kalır.
    if _looks_english(result) and len(result) <= 320:
        return localize_news_title(result)
    return result


__all__ = ["localize_headline", "localize_news_title", "localize_text"]
