"""Open-book structural audit — açık pozisyon kitabındaki yapısal mantık
hatalarını KAPANIŞ BEKLEMEDEN tespit eder.

Bağlam: [[mistake_memory]] yalnızca KAPALI trade fingerprint'lerinden (win_rate,
streak) öğrenir → açık kitabın yapısal hataları (aynı sembolde zıt yön, tek
varlıkta aşırı yoğunlaşma, aynı sinyalin TF'lere kopyalanması, tek-yön kitap)
bir trade kapanana kadar HİÇ yakalanmaz. Bu modül o boşluğu kapatır: canlı
kitabı tarar, kullanıcı-odaklı "ders" (Lesson) listesi üretir.

İki kullanım:
- **Observe** (varsayılan): `summary_viewmodel()` → Conscious "Kitap Denetimi"
  paneli. Karar zincirine dokunmaz.
- **Active guard** (shadow-first, flag default OFF): `self_conflict_symbols()`
  yardımcısı, engine'in aynı sembolde zıt-yön açılışı engellemesi için kullanılır
  (bkz. packages/decision/engine.py · self_conflict_guard.enabled).

DATA_POLICY: yapısal denetim fiyat/quote'a değil, açık pozisyon meta'sına
(symbol/side/timeframe/size_usd) bakar → mock/fallback riski yoktur.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from packages.data.registry.loader import load_thresholds
from packages.risk import correlation

Severity = str  # CRITICAL | WARNING | INFO


@dataclass
class Lesson:
    code: str            # SELF_CONFLICT | CONCENTRATION | MULTI_TF_STACK | CORRELATION_CLUSTER | ONE_WAY_BOOK
    severity: Severity
    title: str           # kısa, kullanıcı-odaklı başlık (TR)
    detail: str          # 1-2 cümle düz açıklama
    symbols: list[str]
    evidence: list[str] = field(default_factory=list)
    suggested_action: str = ""


# Varsayılan eşikler — config (thresholds.book_audit) override eder.
_DEFAULTS = {
    "concentration_pct_of_book": 0.30,   # tek sembol kitabın %30'unu aşarsa
    "concentration_min_positions": 3,    # < bu kadar pozisyonda yoğunlaşma anlamsız (kaçınılmaz pay)
    "one_way_pct": 0.80,                 # tek yön kitabın %80'ini aşarsa
    "stack_min_timeframes": 2,           # aynı sembol+yön ≥2 TF → kopya yığını
}


def _cfg() -> dict:
    cfg = dict(_DEFAULTS)
    cfg.update(load_thresholds().get("book_audit") or {})
    return cfg


def _fmt_usd(value: float) -> str:
    return f"${value:,.0f}"


def _by_symbol(positions) -> dict[str, list]:
    out: dict[str, list] = {}
    for p in positions:
        out.setdefault(p.symbol, []).append(p)
    return dict(sorted(out.items()))


# ── Detektörler ──────────────────────────────────────────────────────────────

def detect_self_conflict(positions) -> list[Lesson]:
    """Aynı sembolde aynı anda LONG ve SHORT → en net mantık hatası."""
    lessons: list[Lesson] = []
    for sym, ps in _by_symbol(positions).items():
        longs = [p for p in ps if p.side == "long"]
        shorts = [p for p in ps if p.side == "short"]
        if longs and shorts:
            lessons.append(
                Lesson(
                    code="SELF_CONFLICT",
                    severity="CRITICAL",
                    title=f"{sym}: aynı anda LONG ve SHORT açık",
                    detail=(
                        f"{sym} üzerinde {len(longs)} LONG ve {len(shorts)} SHORT pozisyon "
                        "birlikte duruyor. En az biri kesin yanlış yönde; ikisi birbirini "
                        "hedge edip net kazancı eritirken iki ayrı komisyon/yönetim yükü taşır."
                    ),
                    symbols=[sym],
                    evidence=[
                        "LONG: " + ", ".join(f"{p.timeframe} {_fmt_usd(p.size_usd)}" for p in longs),
                        "SHORT: " + ", ".join(f"{p.timeframe} {_fmt_usd(p.size_usd)}" for p in shorts),
                    ],
                    suggested_action="Zayıf/küçük bacağı kapat, tek yönde net pozisyon tut.",
                )
            )
    return lessons


def detect_concentration(positions, cfg: dict) -> list[Lesson]:
    """Tek sembol kitabın çok büyük payını tutuyorsa yoğunlaşma uyarısı."""
    book_total = sum(p.size_usd for p in positions)
    if book_total <= 0 or len(positions) < int(cfg["concentration_min_positions"]):
        return []
    threshold = float(cfg["concentration_pct_of_book"])
    lessons: list[Lesson] = []
    for sym, ps in _by_symbol(positions).items():
        total = sum(p.size_usd for p in ps)
        pct = total / book_total
        if pct >= threshold:
            severity = "CRITICAL" if pct >= threshold * 1.3 else "WARNING"
            lessons.append(
                Lesson(
                    code="CONCENTRATION",
                    severity=severity,
                    title=f"{sym}: kitabın %{pct * 100:.0f}'i tek varlıkta",
                    detail=(
                        f"{sym} toplam {_fmt_usd(total)} ile tüm kitabın %{pct * 100:.0f}'ini "
                        f"oluşturuyor (eşik %{threshold * 100:.0f}). Tek varlık ters giderse "
                        "kayıp orantısız büyür — özellikle en oynak varlığa en büyük boyut riskli."
                    ),
                    symbols=[sym],
                    evidence=[
                        f"{len(ps)} pozisyon: "
                        + ", ".join(f"{p.timeframe} {p.side} {_fmt_usd(p.size_usd)}" for p in ps),
                    ],
                    suggested_action="Boyutu düşür ya da varlığı çeşitlendir; en oynak varlığa en büyük boyutu verme.",
                )
            )
    return lessons


def detect_multi_tf_stack(positions, cfg: dict) -> list[Lesson]:
    """Aynı sembol+yön birden çok TF'e bölünmüşse: bağımsız edge değil, kopya."""
    min_tf = int(cfg["stack_min_timeframes"])
    lessons: list[Lesson] = []
    for sym, ps in _by_symbol(positions).items():
        by_side: dict[str, list] = {}
        for p in ps:
            by_side.setdefault(p.side, []).append(p)
        for side, group in sorted(by_side.items()):
            tfs = {p.timeframe for p in group}
            if len(tfs) >= min_tf and len(group) >= min_tf:
                entries = {round(float(p.entry_price), 6) for p in group}
                duplicated = len(entries) < len(group)
                total = sum(p.size_usd for p in group)
                detail = (
                    f"{sym} {side.upper()} aynı yönde {len(group)} ayrı TF'e bölünmüş "
                    f"({', '.join(sorted(tfs))}) — toplam {_fmt_usd(total)}. "
                )
                detail += (
                    "Bacaklar aynı giriş fiyatından açılmış: bu tek sinyalin kopyası, "
                    "bağımsız fırsat değil — exposure ve korelasyonu şişirir."
                    if duplicated
                    else "Aynı yöndeki TF'ler exposure'u üst üste bindirir; bağımsızlık teyit edilmeli."
                )
                lessons.append(
                    Lesson(
                        code="MULTI_TF_STACK",
                        severity="WARNING",
                        title=f"{sym} {side.upper()}: aynı sinyal {len(group)} TF'e kopyalanmış",
                        detail=detail,
                        symbols=[sym],
                        evidence=[
                            ", ".join(f"{p.timeframe} {_fmt_usd(p.size_usd)}" for p in group),
                        ],
                        suggested_action="Tek bir ana TF'te konsolide et; kalanları bağımsız edge yoksa kapat.",
                    )
                )
    return lessons


def detect_correlation_cluster(positions, equity_usd: float) -> list[Lesson]:
    """Korelasyonlu aynı-yön küme exposure'u cap'i aşıyorsa (mevcut
    correlation.open_clusters üstüne kullanıcı-odaklı ders)."""
    if equity_usd <= 0:
        return []
    lessons: list[Lesson] = []
    for cluster in correlation.open_clusters(positions, equity_usd):
        symbols = cluster["symbols"]
        if len(symbols) < 2 or cluster["status"] == "OK":
            continue
        pct = cluster["cluster_pct"]
        severity = "CRITICAL" if cluster["status"] == "BREACH" else "WARNING"
        lessons.append(
            Lesson(
                code="CORRELATION_CLUSTER",
                severity=severity,
                title=f"{' + '.join(symbols)}: korelasyonlu küme equity'nin %{pct * 100:.0f}'i",
                detail=(
                    f"{', '.join(symbols)} aynı yönde, yüksek korelasyonlu bir küme oluşturuyor "
                    f"({_fmt_usd(cluster['total_usd'])}, equity'nin %{pct * 100:.0f}'i). Bu aslında "
                    "tek bir makro bahis; ayrı pozisyonlar gibi görünse de birlikte kazanır/kaybeder."
                ),
                symbols=list(symbols),
                evidence=[f"durum: {cluster['status']}", f"toplam: {_fmt_usd(cluster['total_usd'])}"],
                suggested_action="Küme exposure'unu cap altına indir; korelasyonsuz varlıkla dengeleyebilirsin.",
            )
        )
    return lessons


def detect_one_way(positions, cfg: dict) -> list[Lesson]:
    """Kitabın çok büyük kısmı tek yöndeyse yön-çeşitliliği eksikliği."""
    book_total = sum(p.size_usd for p in positions)
    if book_total <= 0 or len(positions) < 3:
        return []
    threshold = float(cfg["one_way_pct"])
    short_total = sum(p.size_usd for p in positions if p.side == "short")
    long_total = book_total - short_total
    dominant_side, dominant_total = (
        ("SHORT", short_total) if short_total >= long_total else ("LONG", long_total)
    )
    pct = dominant_total / book_total
    if pct < threshold:
        return []
    count = sum(1 for p in positions if p.side == dominant_side.lower())
    return [
        Lesson(
            code="ONE_WAY_BOOK",
            severity="WARNING",
            title=f"Kitabın %{pct * 100:.0f}'i tek yön ({dominant_side})",
            detail=(
                f"{len(positions)} pozisyonun {count}'i {dominant_side} — kitabın %{pct * 100:.0f}'i "
                f"aynı yöne bahis. Tek bir makro sürpriz (risk-on/off) tüm kitabı aynı anda vurur; "
                "yön çeşitliliği yok."
            ),
            symbols=sorted({p.symbol for p in positions if p.side == dominant_side.lower()}),
            evidence=[f"{dominant_side} {_fmt_usd(dominant_total)} / toplam {_fmt_usd(book_total)}"],
            suggested_action="Karşıt yönde kaliteli bir setup veya korelasyonsuz varlıkla dengele.",
        )
    ]


_SEVERITY_RANK = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}


def audit(positions, equity_usd: float) -> list[Lesson]:
    """Tüm detektörleri koştur, önem sırasına göre sıralı Lesson listesi döndür."""
    cfg = _cfg()
    lessons: list[Lesson] = []
    lessons += detect_self_conflict(positions)
    lessons += detect_concentration(positions, cfg)
    lessons += detect_multi_tf_stack(positions, cfg)
    lessons += detect_correlation_cluster(positions, equity_usd)
    lessons += detect_one_way(positions, cfg)
    lessons.sort(key=lambda lesson: (_SEVERITY_RANK.get(lesson.severity, 9), lesson.code))
    return lessons


# ── Active guard yardımcısı (shadow-first) ───────────────────────────────────

def self_conflict_sides(positions) -> dict[str, set[str]]:
    """Sembol → açık taraflar kümesi. Engine self-conflict guard'ı, bir adayın
    aynı sembolde zaten açık ZIT yöne girip girmediğini bu haritayla kontrol eder.
    Salt-okunur; karar zincirine yan etkisi yoktur."""
    out: dict[str, set[str]] = {}
    for p in positions:
        out.setdefault(p.symbol, set()).add(p.side)
    return out


# ── Viewmodel ────────────────────────────────────────────────────────────────

def summary_viewmodel() -> dict:
    """Conscious 'Kitap Denetimi' paneli için observe-only özet."""
    from packages.paper import state as paper_state

    s = paper_state.load()
    positions = list(s.open_positions)
    lessons = audit(positions, s.equity_usd)
    counts = {"CRITICAL": 0, "WARNING": 0, "INFO": 0}
    for lesson in lessons:
        counts[lesson.severity] = counts.get(lesson.severity, 0) + 1
    book_total = sum(p.size_usd for p in positions)
    return {
        "open_positions": len(positions),
        "book_total_usd": round(book_total, 2),
        "counts": counts,
        "clean": not lessons,
        "lessons": [asdict(lesson) for lesson in lessons],
        "thresholds": _cfg(),
    }
