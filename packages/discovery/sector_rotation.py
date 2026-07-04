"""Sektör rotasyon motoru (K-0b, owner kararı 2026-07-04).

Keşif motorunun sektör katmanı: 12 sektör ETF'sinin S&P 500'e GÖRELİ gücünü
günlük barlardan ölçer. Likidite rotasyonunun (rotation/engine — sınıf-ARASI:
para altında mı hissede mi?) sınıf-İÇİ alt katmanıdır; ona EKLENMEZ ve canlı
konsensüse/RiskGate'e/tik'e dokunmaz — yalnız keşif tarayıcısını (K-1) ve
paneli besleyecek. Veri yetersizse sektör UNAVAILABLE; mock skor üretilmez
(DATA_POLICY). Yalnız verified barlar sayılır.

Karne (scorecard): her RISING/FALLING hükmü günde bir damgalanır; çözüm
ufkundan sonra gerçekleşen göreli getiriyle kıyaslanır (RISING doğru ⇔
sektör endeksi geçti). NEUTRAL puanlanmaz (F1-2 başabaş ilkesi). Hiçbir
karar bu motora karnesi görülmeden bağlanmaz.

Artifact: data/runtime/sector_rotation.json {generated_at, sectors, scorecard}
— API/panel (K-3) ve tarayıcı (K-1) buradan okur; env `SECTOR_ROTATION_PATH`
ile yönlendirilebilir (conftest suite izolasyonu deseni).
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from packages.data.providers import ohlcv
from packages.data.registry.loader import CONFIG_DIR
from packages.data.types import OHLCVBar

# Pencereler işlem günü cinsinden — ETF'ler + S&P aynı ABD takviminde işlem
# görür, bar dizileri hizalıdır (kripto karışmaz).
_WIN_1W = 5
_WIN_1M = 21
_WIN_3M = 63
_MOM_WIN = 30
_MIN_BARS = _WIN_3M + 1
# Bileşik skor ağırlıkları: orta vade (1m) baskın, 3m teyit, 1w tazelik.
_W_1W, _W_1M, _W_3M = 0.2, 0.5, 0.3
_RESOLVED_CAP = 500  # karne geçmişi tavanı (artifact şişmesin)

BarsFn = Callable[[str, str], list[OHLCVBar]]


def _out_path() -> Path:
    return Path(os.environ.get("SECTOR_ROTATION_PATH", "data/runtime/sector_rotation.json"))


def load_config() -> dict:
    """config/discovery.yaml → sector_rotation bloğu (yoksa boş dict)."""
    path = CONFIG_DIR / "discovery.yaml"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError:
        return {}
    return dict(raw.get("sector_rotation") or {})


@dataclass
class SectorVerdict:
    sector: str
    label: str
    status: str  # "OK" | "UNAVAILABLE"
    rel_1w_pct: float | None
    rel_1m_pct: float | None
    rel_3m_pct: float | None
    momentum_30d_pct: float | None
    score: float | None
    verdict: str  # "RISING" | "NEUTRAL" | "FALLING" | "UNAVAILABLE"
    rank: int | None
    last_close: float | None  # karne damgası gerçekleşen-kıyas çıpası


def _verified_closes(bars: list[OHLCVBar]) -> list[float]:
    return [b.close for b in bars if b.verified]


def _pct_return(closes: list[float], window: int) -> float | None:
    if len(closes) <= window:
        return None
    base = closes[-1 - window]
    if base <= 0:
        return None
    return (closes[-1] / base - 1.0) * 100.0


def evaluate(cfg: dict | None = None, get_bars: BarsFn | None = None) -> dict:
    """Sektör başına göreli güç + hüküm. Ağ maliyeti: 13 sembolün 1d barı
    (OHLCV cache arkasında). Benchmark verisi yoksa TÜM sektörler UNAVAILABLE."""
    cfg = cfg if cfg is not None else load_config()
    fetch = get_bars or ohlcv.get_bars
    bench_sym = str(cfg.get("benchmark", "SP500"))
    thr = float(cfg.get("verdict_threshold_pct", 1.0))
    sectors_cfg = dict(cfg.get("sectors") or {})

    bench_closes = _verified_closes(fetch(bench_sym, "1d"))
    bench_ok = len(bench_closes) >= _MIN_BARS

    verdicts: list[SectorVerdict] = []
    for sym, meta in sectors_cfg.items():
        label = str((meta or {}).get("label", sym))
        closes = _verified_closes(fetch(sym, "1d")) if bench_ok else []
        rel: dict[str, float | None] = {"1w": None, "1m": None, "3m": None}
        if bench_ok and len(closes) >= _MIN_BARS:
            for key, win in (("1w", _WIN_1W), ("1m", _WIN_1M), ("3m", _WIN_3M)):
                s, b = _pct_return(closes, win), _pct_return(bench_closes, win)
                rel[key] = round(s - b, 4) if s is not None and b is not None else None
        if any(v is None for v in rel.values()):
            verdicts.append(SectorVerdict(
                sector=sym, label=label, status="UNAVAILABLE",
                rel_1w_pct=None, rel_1m_pct=None, rel_3m_pct=None,
                momentum_30d_pct=None, score=None, verdict="UNAVAILABLE",
                rank=None, last_close=None,
            ))
            continue
        mom = _pct_return(closes, _MOM_WIN)
        score = round(_W_1W * rel["1w"] + _W_1M * rel["1m"] + _W_3M * rel["3m"], 4)
        verdict = "RISING" if score >= thr else ("FALLING" if score <= -thr else "NEUTRAL")
        verdicts.append(SectorVerdict(
            sector=sym, label=label, status="OK",
            rel_1w_pct=rel["1w"], rel_1m_pct=rel["1m"], rel_3m_pct=rel["3m"],
            momentum_30d_pct=round(mom, 4) if mom is not None else None,
            score=score, verdict=verdict, rank=None, last_close=closes[-1],
        ))

    # Sıralama: ölçülebilenler skora göre (1 = en güçlü).
    for i, v in enumerate(
        sorted((v for v in verdicts if v.score is not None), key=lambda x: -(x.score or 0)),
        start=1,
    ):
        v.rank = i

    return {
        "benchmark": bench_sym,
        "benchmark_ok": bench_ok,
        "benchmark_last_close": bench_closes[-1] if bench_ok else None,
        "threshold_pct": thr,
        "sectors": [asdict(v) for v in verdicts],
    }


# ---------------------------------------------------------------------------
# Karne — damga + gerçekleşenle çözüm
# ---------------------------------------------------------------------------

def _resolve_pending(
    pending: list[dict],
    ev: dict,
    *,
    resolve_after_days: int,
    pending_max_age_days: int,
    now: datetime,
) -> tuple[list[dict], list[dict], int]:
    """(çözülenler, hâlâ bekleyenler, süresi dolup düşürülenler)."""
    bench_now = ev.get("benchmark_last_close")
    closes_now = {
        s["sector"]: s["last_close"] for s in ev.get("sectors", []) if s.get("last_close")
    }
    resolved: list[dict] = []
    still: list[dict] = []
    expired = 0
    for p in pending:
        try:
            age = (now.date() - date.fromisoformat(str(p["date"]))).days
        except (KeyError, ValueError):
            expired += 1  # bozuk kayıt — süresiz bekletme
            continue
        if age > pending_max_age_days:
            expired += 1
            continue
        sec_now = closes_now.get(str(p.get("sector")))
        if age < resolve_after_days or not sec_now or not bench_now:
            still.append(p)  # ufuk dolmadı ya da bugün veri yok → bekle
            continue
        try:
            rel = (sec_now / float(p["sector_close"]) - 1.0) - (
                bench_now / float(p["bench_close"]) - 1.0
            )
        except (KeyError, ValueError, ZeroDivisionError):
            expired += 1
            continue
        correct = rel > 0 if p.get("verdict") == "RISING" else rel < 0
        resolved.append({
            **p,
            "resolved_at": now.isoformat(),
            "realized_rel_pct": round(rel * 100.0, 4),
            "correct": bool(correct),
        })
    return resolved, still, expired


def _scorecard_summary(resolved: list[dict], pending: list[dict]) -> dict:
    by_sector: dict[str, dict] = {}
    for r in resolved:
        b = by_sector.setdefault(str(r.get("sector")), {"resolved_n": 0, "correct_n": 0})
        b["resolved_n"] += 1
        b["correct_n"] += int(bool(r.get("correct")))
    for b in by_sector.values():
        b["hit_rate"] = round(b["correct_n"] / b["resolved_n"], 4) if b["resolved_n"] else None
    total = len(resolved)
    correct = sum(1 for r in resolved if r.get("correct"))
    return {
        "overall": {
            "resolved_n": total,
            "correct_n": correct,
            "hit_rate": round(correct / total, 4) if total else None,
        },
        "by_sector": by_sector,
        "pending_n": len(pending),
    }


def _load_artifact() -> dict:
    path = _out_path()
    try:
        if path.exists():
            return dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return {}


def run_if_due(now: datetime | None = None, get_bars: BarsFn | None = None) -> dict:
    """Learning worker adımı: interval dolmadıysa CACHED (ağa çıkmaz); dolduysa
    değerlendir + günde bir damgala + bekleyenleri çözümle + artifact yaz."""
    now = now or datetime.now(UTC)
    cfg = load_config()
    interval = int(cfg.get("interval_sec", 3600))
    prev = _load_artifact()

    gen_raw = str(prev.get("generated_at") or "")
    if gen_raw:
        try:
            age = (now - datetime.fromisoformat(gen_raw)).total_seconds()
            if 0 <= age < interval:
                return {"status": "CACHED", "age_sec": int(age)}
        except ValueError:
            pass

    ev = evaluate(cfg, get_bars)

    prev_card = dict(prev.get("scorecard") or {})
    pending = list(prev_card.get("pending") or [])
    resolved = list(prev_card.get("resolved") or [])

    new_resolved, pending, expired = _resolve_pending(
        pending, ev,
        resolve_after_days=int(cfg.get("resolve_after_days", 7)),
        pending_max_age_days=int(cfg.get("pending_max_age_days", 30)),
        now=now,
    )
    resolved = (resolved + new_resolved)[-_RESOLVED_CAP:]

    # Damga: günde bir, yalnız RISING/FALLING (NEUTRAL/UNAVAILABLE puanlanmaz).
    today = now.date().isoformat()
    stamped = 0
    if str(prev.get("last_stamp_date")) != today and ev.get("benchmark_ok"):
        for s in ev["sectors"]:
            if s["verdict"] in ("RISING", "FALLING") and s.get("last_close"):
                pending.append({
                    "date": today,
                    "sector": s["sector"],
                    "verdict": s["verdict"],
                    "score": s["score"],
                    "sector_close": s["last_close"],
                    "bench_close": ev["benchmark_last_close"],
                })
                stamped += 1
        last_stamp_date = today
    else:
        last_stamp_date = prev.get("last_stamp_date")

    expired_total = int(prev_card.get("expired_total") or 0) + expired
    card = {
        "pending": pending,
        "resolved": resolved,
        "expired_total": expired_total,
        **_scorecard_summary(resolved, pending),
    }
    artifact = {
        "generated_at": now.isoformat(),
        "last_stamp_date": last_stamp_date,
        **ev,
        "scorecard": card,
    }
    path = _out_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")

    rising = [s["sector"] for s in ev["sectors"] if s["verdict"] == "RISING"]
    return {
        "status": "OK",
        "rising": rising,
        "unavailable_n": sum(1 for s in ev["sectors"] if s["status"] == "UNAVAILABLE"),
        "stamped": stamped,
        "resolved_new": len(new_resolved),
        "pending_n": len(pending),
    }
