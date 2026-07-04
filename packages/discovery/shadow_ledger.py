"""Keşif gölge kanıt defteri (K-2) — "açılırdı" hükümlerinin karnesi.

Tarayıcının (K-1) WOULD_OPEN_LONG verdiktleri buraya damgalanır ve sonraki
koşularda OHLCV barlarıyla çözülür (missed_opportunity kuralının AYNISI):
  - TP önce  → "missed_win"   (hipotetik kazanç — aday lehine kanıt)
  - SL önce  → "avoided_loss" (hipotetik kayıp)
  - TTL doldu→ "expired"      (net sonuç yok; cf_win_rate paydasına girmez)
Aynı barda ikisi de değerse temkinli davranılır: SL önce sayılır (kaçan
kazancı şişirme — missed_opportunity._resolve_one ile aynı kural).

MEVCUT missed_opportunity ve shadow_decisions verisine KARIŞMAZ — ayrı dosya
(`data/runtime/discovery_shadow.jsonl`, env DISCOVERY_SHADOW_PATH): gerçek
ölçüm hücreleri (F5-1 cf_by_tf, empirical_pwin cf-kanalı) keşif adaylarının
hipotetik sinyalleriyle kirlenmez.

Depolama decision.shadow / missed_opportunity desenini yansıtır: append-only
JSONL + S1-2 rotasyonu (DISCOVERY_SHADOW_MAX_MB, default 64 → `.1` yan-dosya,
okuyucu gerekirse `.1`'e uzanır), best-effort yazım, bozuk satır atlanır.
Aktif izlemeler log replay'inden türetilir (ayrı mutable state yok).

API bütçesi: bar çekimi tarayıcının verdiği closure üzerinden — kripto ancak
o koşuda ZATEN taranan sembol için (sağlayıcı cache'i sıcak → sıfır ek çağrı),
ETF her zaman (ucuz, cache'li orkestratör), gerisi yalnız yaş-expiry.

PAPER_SAFE / NO_EXECUTION: bu modül işlem açmaz, paper state'e dokunmaz;
yalnız tarayıcı artifact'ındaki hükümleri kaydeder ve barlarla ölçer.
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

DEFAULT_PATH = "data/runtime/discovery_shadow.jsonl"
DEFAULT_MAX_READ = 1000
_MAX_MB_ENV = "DISCOVERY_SHADOW_MAX_MB"
_DEFAULT_MAX_MB = 64.0
_MFE_CAP_R = 20.0  # missed_opportunity ile aynı gösterge kırpması (2026-07-02)

# TTL süresi dolmuş ama TP/SL'e değmemiş izleme → "expired".
# missed_opportunity._DEFAULT_TTL_HOURS ile aynı tablo (15m/1w keşifte yok).
_DEFAULT_TTL_HOURS: dict[str, float] = {"1h": 24.0, "4h": 72.0, "1d": 240.0}

# bars_for(symbol, timeframe, kind) → verified barlar; None = bu koşuda bu
# sembol için bar çekilemez (bütçe) → yalnız yaş-expiry uygulanır.
BarsForFn = Callable[[str, str, str], Sequence[Any] | None]


def _path() -> Path:
    return Path(os.environ.get("DISCOVERY_SHADOW_PATH", DEFAULT_PATH))


def _parse_ts(s: Any) -> datetime | None:
    if not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def ttl_hours(cfg: dict, timeframe: str) -> float:
    table = {**_DEFAULT_TTL_HOURS, **{
        str(k): float(v) for k, v in (dict(cfg.get("ttl_hours") or {})).items()
    }}
    return float(table.get(timeframe, 0.0))


# ----------------- I/O (S1-2 rotasyon deseni) -----------------

def _max_bytes() -> int:
    try:
        mb = float(os.environ.get(_MAX_MB_ENV, _DEFAULT_MAX_MB))
    except ValueError:
        mb = _DEFAULT_MAX_MB
    return int(mb * 1024 * 1024)


def _append(entry: dict) -> None:
    """Append-only yazım; dosya limiti aşarsa `.1`'e devir (tek nesil arşiv)."""
    try:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            if p.exists() and p.stat().st_size >= _max_bytes():
                p.replace(p.with_suffix(p.suffix + ".1"))
        except OSError:
            pass
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def read_recent(limit: int = DEFAULT_MAX_READ) -> list[dict]:
    """Son `limit` event (eski→yeni); gerekirse `.1` arşivine uzanır."""
    p = _path()
    lines: list[str] = []
    for path in (p.with_suffix(p.suffix + ".1"), p):
        try:
            if path.exists():
                lines.extend(path.read_text(encoding="utf-8").splitlines())
        except OSError:
            continue
    out: list[dict] = []
    for line in lines[-max(1, limit):]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


# ----------------- aktif set (log replay) -----------------

def _active_trackings(events: Sequence[dict]) -> dict[str, dict]:
    active: dict[str, dict] = {}
    for ev in events:
        tid = ev.get("id")
        if not tid:
            continue
        if ev.get("event") == "track_open":
            active[tid] = ev
        elif ev.get("event") == "resolve":
            active.pop(tid, None)
    return active


def _has_active_for(active: dict[str, dict], symbol: str, timeframe: str) -> bool:
    return any(
        a.get("symbol") == symbol and a.get("timeframe") == timeframe
        for a in active.values()
    )


# ----------------- çözümleme (bar high/low; missed_opp kuralı) -----------------

def _resolve_one(
    tracking: dict, *, now: datetime, ttl_h: float, bars: Sequence[Any] | None
) -> dict | None:
    """Bir izlemeyi çöz; sonuç yoksa None (izleme açık kalır).

    bars=None → bu koşuda bar yok (bütçe): yalnız TTL yaş-expiry bakılır.
    v1 LONG-only olsa da kural iki yön için yazıldı (kayıt side taşır).
    """
    entry = float(tracking.get("entry") or 0.0)
    sl = float(tracking.get("sl") or 0.0)
    tp = float(tracking.get("tp") or 0.0)
    side = str(tracking.get("side") or "long")
    opened = _parse_ts(tracking.get("opened_at"))
    if opened is None or not entry or not sl or not tp:
        return None

    r_unit = abs(entry - sl)
    mfe_r = 0.0
    seen = 0
    for b in bars or []:
        ts = getattr(b, "ts", None)
        if ts is None or ts <= opened:
            continue
        seen += 1
        hi, lo = float(b.high), float(b.low)
        if side == "long":
            mfe_r = max(mfe_r, (hi - entry) / r_unit if r_unit else 0.0)
            hit_sl, hit_tp = lo <= sl, hi >= tp
        else:
            mfe_r = max(mfe_r, (entry - lo) / r_unit if r_unit else 0.0)
            hit_sl, hit_tp = hi >= sl, lo <= tp
        if hit_sl:  # aynı barda ikisi de değdiyse temkinli: SL önce
            return _resolve_event(tracking, "avoided_loss", now, mfe_r, seen)
        if hit_tp:
            return _resolve_event(tracking, "missed_win", now, mfe_r, seen)

    if ttl_h > 0 and (now - opened) >= timedelta(hours=ttl_h):
        return _resolve_event(tracking, "expired", now, mfe_r, seen)
    return None


def _resolve_event(tracking: dict, outcome: str, now: datetime, mfe_r: float, bars_seen: int) -> dict:
    return {
        "event": "resolve",
        "id": tracking.get("id"),
        "symbol": tracking.get("symbol"),
        "kind": tracking.get("kind"),
        "timeframe": tracking.get("timeframe"),
        "side": tracking.get("side"),
        "outcome": outcome,
        "rr": tracking.get("rr"),
        "mfe_r": round(min(mfe_r, _MFE_CAP_R), 3),
        "bars_seen": bars_seen,
        "opened_at": tracking.get("opened_at"),
        "resolved_at": now.isoformat(),
    }


# ----------------- ana giriş (tarayıcı koşusu) -----------------

def process_run(
    *,
    results: dict,
    scanned: Sequence[str],
    now: datetime,
    bars_for: BarsForFn,
    cfg: dict | None = None,
) -> dict:
    """Bir tarayıcı koşusu için: (1) aktif izlemeleri çöz, (2) bu koşuda taranan
    WOULD_OPEN_LONG verdiktlerini damgala.

    Best-effort: raise etmez (defter tarayıcıyı asla düşürmez). Damga yalnız
    BU koşuda taranan sembollerden (bayat artifact sonucu yeniden damgalanmaz);
    aynı (symbol, tf) için aktif izleme varsa yenisi açılmaz — çözülünce
    sinyal sürüyorsa sonraki taramada YENİ izleme açılır (kanıt birikir).
    """
    cfg = dict(cfg or {})
    summary = {"tracked_new": 0, "resolved": 0, "active": 0}
    try:
        events = read_recent()
        active = _active_trackings(events)

        # (1) Aktif izlemeleri çöz.
        for tid, tracking in list(active.items()):
            try:
                bars = bars_for(
                    str(tracking.get("symbol") or ""),
                    str(tracking.get("timeframe") or "1d"),
                    str(tracking.get("kind") or ""),
                )
                resolved = _resolve_one(
                    tracking, now=now, bars=bars,
                    ttl_h=ttl_hours(cfg, str(tracking.get("timeframe") or "")),
                )
            except Exception:
                _log.warning("discovery_shadow resolve failed for %s", tid, exc_info=True)
                resolved = None
            if resolved is not None:
                _append(resolved)
                active.pop(tid, None)
                summary["resolved"] += 1

        # (2) Bu koşunun taze sinyallerini damgala.
        for sym in scanned:
            res = results.get(sym) or {}
            if res.get("verdict") != "WOULD_OPEN_LONG":
                continue
            tf = str(res.get("entry_timeframe") or "")
            if ttl_hours(cfg, tf) <= 0:
                continue  # izlenmeyen TF
            if _has_active_for(active, sym, tf):
                continue
            open_ev = {
                "event": "track_open",
                "id": f"{now.isoformat()}:{sym}:{tf}:long",
                "symbol": sym,
                "kind": res.get("kind"),
                "timeframe": tf,
                "side": "long",
                "entry": res.get("entry"),
                "sl": res.get("sl"),
                "tp": res.get("tp"),
                "rr": res.get("rr"),
                "confidence": res.get("confidence"),
                "expected_value": res.get("expected_value"),
                "regime": res.get("regime"),
                "opened_at": now.isoformat(),
                "ttl_hours": ttl_hours(cfg, tf),
            }
            _append(open_ev)
            active[open_ev["id"]] = open_ev
            summary["tracked_new"] += 1

        summary["active"] = len(active)
    except Exception:
        _log.exception("discovery_shadow process_run failed (tarama devam ediyor)")
    return summary


# ----------------- aday özeti (artifact + K-3 API besini) -----------------

def candidate_summary(limit: int = DEFAULT_MAX_READ) -> dict:
    """Sembol başına gölge karne: n_signals, resolved, cf_win_rate, ort. R.

    cf_win_rate = missed_win / (missed_win + avoided_loss) — expired paydaya
    girmez (missed_opportunity/F5-1 ile aynı sayım kuralı). avg_r gerçekleşen
    hipotetik R: missed_win → +rr, avoided_loss → −1R. K-4 terfi kriterinin
    girdileri (≥20 çözüm, Wilson alt sınırı, ≥2 TF) bu sayılardan hesaplanacak.
    """
    events = read_recent(limit=limit)
    active = _active_trackings(events)
    per: dict[str, dict] = {}

    def _slot(sym: str) -> dict:
        return per.setdefault(sym, {
            "n_signals": 0, "resolved": 0,
            "missed_win": 0, "avoided_loss": 0, "expired": 0,
            "r_sum": 0.0, "timeframes": set(), "last_signal_at": None,
        })

    for ev in events:
        sym = str(ev.get("symbol") or "")
        if not sym:
            continue
        s = _slot(sym)
        if ev.get("event") == "track_open":
            s["n_signals"] += 1
            s["timeframes"].add(str(ev.get("timeframe") or "?"))
            s["last_signal_at"] = ev.get("opened_at")
        elif ev.get("event") == "resolve":
            oc = ev.get("outcome")
            if oc in ("missed_win", "avoided_loss", "expired"):
                s["resolved"] += 1
                s[oc] += 1
            if oc == "missed_win":
                s["r_sum"] += float(ev.get("rr") or 0.0)
            elif oc == "avoided_loss":
                s["r_sum"] -= 1.0

    out: dict[str, dict] = {}
    for sym, s in per.items():
        n = s["missed_win"] + s["avoided_loss"]
        out[sym] = {
            "n_signals": s["n_signals"],
            "resolved": s["resolved"],
            "missed_win": s["missed_win"],
            "avoided_loss": s["avoided_loss"],
            "expired": s["expired"],
            "cf_win_rate": round(s["missed_win"] / n, 4) if n else None,
            "avg_r": round(s["r_sum"] / n, 3) if n else None,
            "timeframes": sorted(s["timeframes"]),
            "last_signal_at": s["last_signal_at"],
        }
    return {"active_n": len(active), "candidates": out}
