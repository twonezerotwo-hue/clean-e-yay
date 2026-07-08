"""Yansıma / hafıza döngüsü — kapanan işlemlerden DERS çıkar (SALT-GÖZLEM).

TradingAgents (GitHub, 80k★) deseninden alınan tek gerçek fikir: her işlem
kapandıktan sonra gerçekleşen sonucu kısa bir "ders"e çevir ve bir sonraki
kararın önüne koy. Bu modül dersleri ÜRETİR (bağlam katmanı); karar-anına
enjeksiyon AYRI bir adım (owner planı — henüz karar hattına bağlı DEĞİL).

`mistake_memory`'den FARKI (kopya değil): mistake_memory fingerprint
istatistiğinden AVOID/BOOST/WARNING SAYISAL damgası üretir (zaten karara bağlı).
Bu modül son işlemlerin ANLATISAL dersini üretir — "ne oldu, kaça, hangi setup"
— akıl yürütmenin okuyacağı hafıza. İkisi tamamlayıcı.

KURALLAR:
- EVIDENCE only: dersler yalnız gerçekleşen outcome alanlarından (pnl_pct,
  r_multiple, dominant_module, regime...) türer; LLM/uydurma sayı YOK.
- Yalnız `data_verified` + kapanmış (pnl_pct dolu) outcome'lar derse girer.
- Karara/ağırlığa/paper'a SIFIR dokunuş; yalnız izlenebilir digest artifact'ı.
- Asla raise etmez (bozuk kayıt atlanır).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from packages.learning import outcomes as outcomes_mod

_ENGINE = "reflection_v1"
_DEFAULT_CROSS = 10   # çapraz-sembol son ders sayısı
_DEFAULT_PER_SYMBOL = 3


def _path() -> Path:
    return Path(os.environ.get("REFLECTION_PATH", "data/runtime/reflection_digest.json"))


@dataclass(frozen=True)
class Lesson:
    """Tek kapanmış işlemin dersi — hepsi gerçekleşen outcome'tan (fact)."""

    symbol: str
    timeframe: str
    regime: str
    direction: str
    won: bool
    pnl_pct: float | None
    r_multiple: float | None
    dominant_module: str
    close_reason: str | None
    closed_at: str | None
    text: str


def _fmt_pct(v: float | None) -> str:
    return f"{v:+.2f}%" if v is not None else "?%"


def _fmt_r(v: float | None) -> str:
    return f"{v:+.2f}R" if v is not None else "?R"


def _lesson_text(o) -> str:
    """Deterministik tek-cümle ders (uydurma yok — yalnız outcome alanları)."""
    sonuc = "KAZANDI" if o.pnl > 0 else ("başabaş" if o.pnl == 0 else "kaybetti")
    cikis = f", çıkış={o.close_reason}" if o.close_reason else ""
    return (
        f"{o.symbol} {o.direction} {o.timeframe}/{o.regime} → {sonuc} "
        f"{_fmt_pct(o.pnl_pct)} ({_fmt_r(o.r_multiple)}), "
        f"başat modül={o.dominant_module or '?'}{cikis}"
    )


def _to_lesson(o) -> Lesson | None:
    # Yalnız kapanmış + doğrulanmış + yön-yüzdesi olan outcome derse girer.
    if not getattr(o, "data_verified", False) or o.pnl_pct is None:
        return None
    return Lesson(
        symbol=o.symbol,
        timeframe=o.timeframe,
        regime=o.regime,
        direction=o.direction,
        won=o.pnl > 0,
        pnl_pct=o.pnl_pct,
        r_multiple=o.r_multiple,
        dominant_module=o.dominant_module,
        close_reason=o.close_reason,
        closed_at=o.closed_at,
        text=_lesson_text(o),
    )


def _sorted_lessons(outcomes) -> list[Lesson]:
    """En yeni kapanış önce (closed_at'e göre; eksikse sıra korunur)."""
    lessons = [ln for o in outcomes if (ln := _to_lesson(o)) is not None]
    lessons.sort(key=lambda x: x.closed_at or "", reverse=True)
    return lessons


def recent_lessons(outcomes, *, symbol: str | None = None, limit: int = 8) -> list[Lesson]:
    """En yeni kapanan dersler (opsiyonel sembol filtresi), yeni→eski."""
    lessons = _sorted_lessons(outcomes)
    if symbol is not None:
        lessons = [ln for ln in lessons if ln.symbol == symbol]
    return lessons[:limit]


def _aggregate(lessons: list[Lesson]) -> dict:
    """Ders kümesinin kısa karnesi (kaç, kaçı kazandı, ort R/%)."""
    n = len(lessons)
    if not n:
        return {"n": 0}
    wins = sum(1 for ln in lessons if ln.won)
    rs = [ln.r_multiple for ln in lessons if ln.r_multiple is not None]
    pcts = [ln.pnl_pct for ln in lessons if ln.pnl_pct is not None]
    return {
        "n": n,
        "wins": wins,
        "win_pct": round(wins / n * 100, 1),
        "avg_r": round(sum(rs) / len(rs), 3) if rs else None,
        "avg_pct": round(sum(pcts) / len(pcts), 3) if pcts else None,
    }


def symbol_memory(outcomes, symbol: str, *, limit: int = _DEFAULT_PER_SYMBOL) -> dict:
    """Bir sembolün son dersleri + kısa karnesi — karar-anına enjekte edilecek yüzey."""
    lessons = recent_lessons(outcomes, symbol=symbol, limit=limit)
    return {
        "symbol": symbol,
        "lessons": [ln.text for ln in lessons],
        "summary": _aggregate(lessons),
    }


def build_digest(outcomes=None, *, cross: int = _DEFAULT_CROSS,
                 per_symbol: int = _DEFAULT_PER_SYMBOL) -> dict:
    """Gözlemlenebilir + (ileride) enjekte edilebilir yansıma yüzeyi:
    çapraz-sembol son dersler + son görülen semboller için per-sembol hafıza."""
    if outcomes is None:
        try:
            outcomes = outcomes_mod.outcomes_from_state()
        except Exception:
            outcomes = []
    all_recent = _sorted_lessons(outcomes)
    cross_lessons = all_recent[:cross]
    seen: list[str] = []
    for ln in all_recent:
        if ln.symbol not in seen:
            seen.append(ln.symbol)
        if len(seen) >= 6:
            break
    per = {sym: symbol_memory(outcomes, sym, limit=per_symbol) for sym in seen}
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "engine": _ENGINE,
        "total_lessons": len(all_recent),
        "cross_lessons": [ln.text for ln in cross_lessons],
        "cross_summary": _aggregate(cross_lessons),
        "per_symbol": per,
        "note": (
            "SALT-GOZLEM: kapanan islemlerden ders. Karar hattina BAGLI DEGIL "
            "(enjeksiyon ayri owner adimi). Dersler yalniz gerceklesen outcome'tan."
        ),
    }


def write_digest() -> dict:
    """learning_worker adımı (ucuz — her cycle). Digest'i artifact'a yazar.
    Flag YOK (salt-gözlem). Asla raise etmez."""
    try:
        digest = build_digest()
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(digest, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)
        return {"status": "OK", "total_lessons": digest["total_lessons"]}
    except (OSError, ValueError, TypeError) as exc:
        return {"status": f"ERROR:{type(exc).__name__}"}


def viewmodel() -> dict:
    """GET /learning/reflection — yansıma digest'i (read-only, PAPER_SAFE)."""
    try:
        p = _path()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            data["status"] = "OK"
            data["shadow_only"] = True
            return data
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    # Artifact yoksa canlı hesap (ucuz) — yine de dürüst yüzey.
    live = build_digest()
    live["status"] = "OK"
    live["shadow_only"] = True
    return live


def lesson_to_dict(ln: Lesson) -> dict:
    return asdict(ln)


__all__ = [
    "Lesson",
    "build_digest",
    "lesson_to_dict",
    "recent_lessons",
    "symbol_memory",
    "viewmodel",
    "write_digest",
]
