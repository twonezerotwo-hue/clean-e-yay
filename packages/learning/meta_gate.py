"""Y-5 — Meta-label kapısı (mlfinlab meta-labeling deseni), SHADOW-ONLY.

Fikir: yön sinyalini TAHMİN ETME; mevcut sinyale "GİR / GİRME" diyen ikinci bir
değerlendirici kur. Kanıt (2026-07-07 modül karnesi): touche canlıda kazananı
kaybedenden AYIRAMIYOR (katkı 24.3/25.5) — eksik olan yön değil SEÇİCİLİK.

Bu dilim KIRMIZI ÇİZGİ protokolüne göre SALT-GÖLGE: motor her açılış adayına
kapının hükmünü damgalar, karar/boyut DEĞİŞMEZ. Uygulama flag'i BU DİLİMDE YOK
(ölü flag bırakmamak için — kural 3); aktivasyon, gölge karnesi (scorecard)
seçicilik kanıtı gösterince AYRI dilim + owner kararıdır.

Girdiler (hepsi MEVCUT kanıt yüzeyleri — yeni sinyal üretilmez):
- expected_value (R-katı EV, motor zaten hesaplıyor)
- p_win_empirical (F4-2 ampirik isabet; None = kanıt yok → nötr)
- mistake_memory hükmü (AVOID/BOOST)
- bariyer-kalite tarihçesi (Y-2 barrier_label; dominant_module×timeframe kovası,
  off-tick `compute()` ile öğrenilir — hakiki kazanç vs korunamayan kâr oranı)
- rejim risk freni kanıtı (Y-1; çift-negatif rejim → eksi bileşen)

Akış: `compute()` learning worker'da OFF-TICK bucket tablosunu yazar
(data/runtime/meta_gate.json). Sıcak yol `assess()` yalnız mtime-cache okur +
aritmetik. Gölge hükümleri fingerprint'le İZOLE deftere yazılır
(meta_gate_shadow.jsonl); `scorecard()` kapanan AUTO outcome'ları fingerprint
üzerinden hükümlerle birleştirir → "TAKE'ler gerçekten SKIP'lerden iyi mi?"
seçicilik kanıtı (aktivasyonun tek meşru dayanağı).
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import load_thresholds

# Gölge defteri şişme tavanı (S1-2 felsefesi; aşılırsa yeni satır yazılmaz —
# scorecard mevcut kanıtla çalışır, tik asla şişen dosyaya kilitlenmez).
_SHADOW_MAX_MB = 32
_MIN_BUCKET_N_DEFAULT = 8
_MIN_SCORE_DEFAULT = 0.0
_WEIGHTS_DEFAULT = {
    "ev": 1.0, "empirical": 1.0, "mistake": 1.0,
    "barrier_history": 1.0, "regime_brake": 0.5,
}


def _cfg() -> dict:
    try:
        return load_thresholds().get("meta_gate") or {}
    except (OSError, KeyError, ValueError, TypeError):
        return {}


def _table_path() -> Path:
    return Path(os.environ.get("META_GATE_PATH", "data/runtime/meta_gate.json"))


def _shadow_path() -> Path:
    return Path(os.environ.get("META_GATE_SHADOW_PATH", "data/runtime/meta_gate_shadow.jsonl"))


# ── off-tick: bariyer-kalite tarihçesi (Y-2 etiketi tek kaynak) ─────────────────

_GOOD_Q = {"clean_win"}
_BAD_Q = {"roundtrip_loss", "never_worked", "timeout_loss"}


def compute(outcomes=None, now: datetime | None = None) -> dict:
    """(dominant_module × timeframe) kovası başına bariyer-kalite tarihçesi.

    quality_score = (hakiki kazanç − kötü çıkış) / n ∈ [−1, +1]. Yalnız AUTO
    kohort (cohorts.classify); MANUAL/EXCLUDED tarihçeye sızmaz."""
    now = now or datetime.now(UTC)
    if outcomes is None:
        from packages.learning import outcomes as outcomes_mod
        # Veri hijyeni (2026-07-12): legacy kayıtlar kapı kovalarına girmez.
        outcomes = outcomes_mod.learning_grade(outcomes_mod.outcomes_from_state())
    from packages.learning import cohorts, exit_forensics

    buckets: dict[str, dict] = {}
    for o in outcomes:
        if cohorts.classify(o) != cohorts.AUTO:
            continue
        try:
            lbl = exit_forensics.barrier_label(o)
        except Exception:  # tek bozuk kayıt tabloyu düşürmesin
            continue
        key = f"{o.dominant_module or '?'}|{o.timeframe or '?'}"
        b = buckets.setdefault(key, {"n": 0, "good": 0, "bad": 0, "quality": {}})
        b["n"] += 1
        q = lbl["quality"]
        b["quality"][q] = b["quality"].get(q, 0) + 1
        if q in _GOOD_Q:
            b["good"] += 1
        elif q in _BAD_Q:
            b["bad"] += 1
    for b in buckets.values():
        b["quality_score"] = round((b["good"] - b["bad"]) / b["n"], 4) if b["n"] else 0.0

    table = {
        "generated_at": now.isoformat(),
        "engine": "meta_gate_v1",
        "buckets": dict(sorted(buckets.items())),
        "note": "SHADOW-ONLY: hukum karara/boyuta uygulanmaz (aktivasyon ayri dilim + owner)",
    }
    p = _table_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
    return table


# ── sıcak yol: saf skor (mtime-cache tablo + aritmetik; ağ/hesap yok) ───────────

_cache: dict = {"mtime": None, "data": None}


def _load_table() -> dict | None:
    try:
        p = _table_path()
        if not p.exists():
            return None
        mtime = p.stat().st_mtime
        if _cache["mtime"] != mtime:
            _cache["data"] = json.loads(p.read_text(encoding="utf-8"))
            _cache["mtime"] = mtime
        return _cache["data"]
    except (OSError, ValueError, TypeError):
        return None


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, v))


def assess(
    *,
    dominant_module: str | None,
    timeframe: str,
    regime_label: str | None,
    expected_value: float | None,
    p_win_empirical: float | None,
    mistake_action: str | None,
    regime_braked: bool,
) -> dict:
    """Karar bağlamı → gölge hüküm {verdict TAKE|SKIP, score, components}.

    Kanıtsız bileşen 0 (nötr) — kapı bilmediği şeyden ceza/ödül üretmez.
    Deterministik ve saf: aynı girdi + aynı tablo = aynı hüküm."""
    cfg = _cfg()
    weights = {**_WEIGHTS_DEFAULT, **(cfg.get("weights") or {})}
    min_score = float(cfg.get("min_score", _MIN_SCORE_DEFAULT))
    min_bucket_n = int(cfg.get("min_bucket_n", _MIN_BUCKET_N_DEFAULT))

    components: dict[str, float] = {
        "ev": _clamp(float(expected_value)) if expected_value is not None else 0.0,
        "empirical": (
            _clamp((float(p_win_empirical) - 0.5) * 4.0)
            if p_win_empirical is not None else 0.0
        ),
        "mistake": {"AVOID": -1.0, "BOOST": 1.0}.get(str(mistake_action or ""), 0.0),
        "regime_brake": -1.0 if regime_braked else 0.0,
    }
    bucket_key = f"{dominant_module or '?'}|{timeframe or '?'}"
    barrier_c = 0.0
    table = _load_table()
    bucket = ((table or {}).get("buckets") or {}).get(bucket_key)
    if bucket and int(bucket.get("n") or 0) >= min_bucket_n:
        barrier_c = _clamp(float(bucket.get("quality_score") or 0.0))
    components["barrier_history"] = barrier_c

    total_w = sum(weights.get(k, 0.0) for k in components) or 1.0
    score = sum(components[k] * weights.get(k, 0.0) for k in components) / total_w
    return {
        "verdict": "TAKE" if score >= min_score else "SKIP",
        "score": round(score, 4),
        "components": {k: round(v, 4) for k, v in components.items()},
        "bucket": bucket_key,
        "bucket_n": int(bucket.get("n")) if bucket else 0,
        "shadow": True,  # hüküm karara UYGULANMAZ — salt gözlem
    }


def record_shadow(fingerprint: str | None, report: dict, now: datetime | None = None) -> None:
    """Gölge hükmü İZOLE deftere yaz (fingerprint = scorecard join anahtarı).

    Sıcak yoldan çağrılır ama asla fırlatmaz; defter tavanı aşılırsa yazmayı
    keser (tik şişen dosyaya kilitlenmez)."""
    if not fingerprint:
        return
    try:
        p = _shadow_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.stat().st_size > _SHADOW_MAX_MB * 1024 * 1024:
            return
        row = {
            "ts": (now or datetime.now(UTC)).isoformat(),
            "fingerprint": fingerprint,
            "verdict": report.get("verdict"),
            "score": report.get("score"),
        }
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:  # gölge kaydı kararı asla düşürmez
        return


# ── scorecard: gölge hüküm ↔ gerçekleşen sonuç (seçicilik kanıtı) ───────────────

def _read_shadow(limit: int = 20000) -> dict[str, dict]:
    """fingerprint → İLK hüküm (aynı sinyalin tekrar tiklerinde ilk görüş)."""
    out: dict[str, dict] = {}
    try:
        p = _shadow_path()
        if not p.exists():
            return out
        for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            fp = row.get("fingerprint")
            if fp and fp not in out:
                out[fp] = row
    except OSError:
        return out
    return out


def scorecard(outcomes=None) -> dict:
    """Kapanan AUTO outcome'ları gölge hükümlerle fingerprint'ten birleştir.

    Aktivasyonun tek meşru dayanağı: TAKE kovası SKIP kovasından anlamlı iyiyse
    kapı seçici demektir. unmatched = hükümsüz kapanış (kapı o sinyali görmedi
    — dürüst sayım, tabloyu şişirmez)."""
    if outcomes is None:
        from packages.learning import outcomes as outcomes_mod
        # Veri hijyeni (2026-07-12): legacy kayıtlar kapı karnesine girmez.
        outcomes = outcomes_mod.learning_grade(outcomes_mod.outcomes_from_state())
    from packages.learning import cohorts

    shadow = _read_shadow()
    agg = {"TAKE": {"n": 0, "wins": 0, "pnl": 0.0},
           "SKIP": {"n": 0, "wins": 0, "pnl": 0.0}}
    unmatched = 0
    for o in outcomes:
        if cohorts.classify(o) != cohorts.AUTO:
            continue
        row = shadow.get(o.fingerprint or "")
        if not row or row.get("verdict") not in agg:
            unmatched += 1
            continue
        a = agg[row["verdict"]]
        a["n"] += 1
        a["wins"] += 1 if float(o.pnl or 0.0) > 0 else 0
        a["pnl"] += float(o.pnl or 0.0)
    for a in agg.values():
        a["win_rate"] = round(a["wins"] / a["n"], 3) if a["n"] else None
        a["pnl"] = round(a["pnl"], 2)
    take, skip = agg["TAKE"], agg["SKIP"]
    selective = (
        take["win_rate"] is not None and skip["win_rate"] is not None
        and take["win_rate"] > skip["win_rate"] and take["pnl"] > skip["pnl"]
    )
    return {"by_verdict": agg, "unmatched": unmatched,
            "selective": bool(selective),
            "note": "selective=true bile AKTIVASYON YAPMAZ — owner karari (kirmizi cizgi)"}


def viewmodel() -> dict:
    """GET /learning/meta-gate — tablo + gölge seçicilik karnesi (hesap yüzeyde)."""
    table = _load_table()
    return {
        "status": "OK" if table else "NO_TABLE",
        "generated_at": (table or {}).get("generated_at"),
        "buckets": (table or {}).get("buckets") or {},
        "config": {
            "min_score": float(_cfg().get("min_score", _MIN_SCORE_DEFAULT)),
            "min_bucket_n": int(_cfg().get("min_bucket_n", _MIN_BUCKET_N_DEFAULT)),
        },
        "scorecard": scorecard(),
        "shadow_only": True,
    }
