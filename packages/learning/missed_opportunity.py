"""Missed Opportunity motoru — açılmayan valid setup'ların sonucunu izler.

Amaç (learning yakıtı, Faz 4 conflict-gate genişletme kararı için): Yeni pipeline
`CANDIDATE_OPEN` (geçerli setup + RiskGate pass + trigger + SL/TP/RR valid) dediği
ama canlı sistemin AÇMADIĞI girişleri TTL boyunca takip et. Fiyat önce TP'ye mi
yoksa SL'e mi değdi?
  - TP önce  → "missed_win"   (kaçan kazanç — bu profili açmak lehte kanıt)
  - SL önce  → "avoided_loss" (iyi ki açmadık — kapalı tutmak lehte kanıt)
  - TTL doldu→ "expired"      (net sonuç yok)

PAPER_SAFE / NO_EXECUTION: Bu modül paper state'e ASLA dokunmaz, trade açmaz/
kapatmaz. Yalnızca zaten hesaplanmış shadow kaydını (target_comparison dahil)
okur ve cached OHLCV barlarından sonucu ölçer.

Depolama `learning/decision_log.py` / `decision.shadow`'u yansıtır: append-only
JSONL, best-effort yazım (asla raise etmez), bozuk satır okurken atlanır,
`MISSED_OPP_LOG_PATH` env override. Aktif izlemeler log replay'inden türetilir
(ayrı mutable state yok → crash-safe). enabled=false (varsayılan) → inert.
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from packages.data.providers import ohlcv
from packages.data.registry.loader import load_thresholds

_log = logging.getLogger(__name__)

DEFAULT_PATH = "data/runtime/missed_opportunity.jsonl"
DEFAULT_MAX_READ = 500

# TTL süresi dolmuş ama TP/SL'e değmemiş izleme → "expired".
_DEFAULT_TTL_HOURS: dict[str, float] = {
    "15m": 6.0,
    "1h": 24.0,
    "4h": 72.0,
    "1d": 240.0,   # 10 gün
    "1w": 0.0,     # 1w paper trade açmaz → izlenmez
}

# Canlı sistem aynı yönde açtıysa ("AGREE_ENTRY") bu bir kaçırma DEĞİL — atla.
_LIVE_TOOK_IT = "AGREE_ENTRY"
# Yalnızca yeni pipeline'ın gerçekten açılabilir dediği setuplar izlenir.
_CANDIDATE_OPEN = "CANDIDATE_OPEN"


@dataclass(frozen=True)
class MissedOppConfig:
    """`missed_opportunity:` config bloğu — gözlem amaçlı, varsayılan KAPALI."""

    enabled: bool = False
    min_rr: float = 1.0
    ttl_hours: dict[str, float] = None  # type: ignore[assignment]

    def ttl_for(self, timeframe: str) -> float:
        table = self.ttl_hours or _DEFAULT_TTL_HOURS
        return float(table.get(timeframe, _DEFAULT_TTL_HOURS.get(timeframe, 0.0)))


def load_config() -> MissedOppConfig:
    c = load_thresholds().get("missed_opportunity", {}) or {}
    ttl = {k: float(v) for k, v in (c.get("ttl_hours") or {}).items()}
    return MissedOppConfig(
        enabled=bool(c.get("enabled", False)),
        min_rr=float(c.get("min_rr", 1.0)),
        ttl_hours=ttl or dict(_DEFAULT_TTL_HOURS),
    )


def _path() -> Path:
    return Path(os.environ.get("MISSED_OPP_LOG_PATH", DEFAULT_PATH))


def _parse_ts(s: Any) -> datetime | None:
    if not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


# ----------------- candidate çıkarımı (shadow kaydından) -----------------

def _targets(target_comparison: dict) -> dict | None:
    """tf_aware tercih edilir, yoksa fixed; side+entry+sl+tp tam değilse None."""
    if not target_comparison:
        return None
    side = (target_comparison.get("side") or "").lower()
    entry = target_comparison.get("entry")
    if side not in ("long", "short") or not entry:
        return None
    for key in ("tf_aware", "fixed", "adaptive"):
        blk = target_comparison.get(key) or {}
        sl, tp = blk.get("sl"), blk.get("tp")
        if sl and tp:
            return {
                "side": side,
                "entry": float(entry),
                "sl": float(sl),
                "tp": float(tp),
                "rr": float(blk.get("rr") or 0.0),
                "basis": key,
            }
    return None


def _candidates(record: dict) -> list[dict]:
    """Shadow kaydından izlenecek 'açılmamış valid setup'ları çıkar.

    Kural: conflict_final_action == CANDIDATE_OPEN, canlı aynı yönde AÇMAMIŞ
    (agreement != AGREE_ENTRY) ve ölçülebilir hedefleri (side+entry+sl+tp) var.
    """
    out: list[dict] = []
    for row in record.get("symbols") or []:
        sc = row.get("setup_conflict") or {}
        if sc.get("conflict_final_action") != _CANDIDATE_OPEN:
            continue
        if row.get("agreement") == _LIVE_TOOK_IT:
            continue
        tgt = _targets(sc.get("target_comparison") or {})
        if tgt is None:
            continue
        shadow = row.get("shadow") or {}
        out.append(
            {
                "symbol": row.get("symbol"),
                "timeframe": shadow.get("entry_timeframe") or "1d",
                "setup_type": sc.get("setup_type"),
                "trade_profile": sc.get("trade_profile"),
                "agreement": row.get("agreement"),
                **tgt,
            }
        )
    return out


# ----------------- aktif set (log replay) -----------------

def _active_trackings(events: Sequence[dict]) -> dict[str, dict]:
    """track_open'ları topla, resolve edilmişleri çıkar → aktif izleme dict'i (id→event)."""
    active: dict[str, dict] = {}
    for ev in events:
        kind = ev.get("event")
        tid = ev.get("id")
        if not tid:
            continue
        if kind == "track_open":
            active[tid] = ev
        elif kind == "resolve":
            active.pop(tid, None)
    return active


def _tracking_id(snapshot_id: str | None, symbol: str | None, timeframe: str, side: str) -> str:
    return f"{snapshot_id}:{symbol}:{timeframe}:{side}"


def _has_active_for(active: dict[str, dict], symbol: str | None, timeframe: str, side: str) -> bool:
    """Aynı (symbol, tf, side) için zaten aktif izleme var mı? (her tick yeniden açma)."""
    return any(
        a.get("symbol") == symbol
        and a.get("timeframe") == timeframe
        and a.get("side") == side
        for a in active.values()
    )


# ----------------- çözümleme (bar high/low) -----------------

def _resolve_one(
    tracking: dict,
    *,
    now: datetime,
    cfg: MissedOppConfig,
    get_bars: Callable[[str, str], list[Any]],
) -> dict | None:
    """Bir izlemeyi cached barlarla çöz. Sonuç yoksa None (izleme açık kalır)."""
    symbol = tracking.get("symbol")
    tf = tracking.get("timeframe") or "1d"
    side = tracking.get("side")
    sl = float(tracking.get("sl"))
    tp = float(tracking.get("tp"))
    entry = float(tracking.get("entry"))
    opened = _parse_ts(tracking.get("opened_at"))
    if not symbol or side not in ("long", "short") or opened is None:
        return None

    r_unit = abs(entry - sl)
    bars = [b for b in (get_bars(symbol, tf) or []) if getattr(b, "ts", None) and b.ts > opened]
    # Kronolojik sırada ilk değen seviyeyi bul (aynı barda ikisi de değerse
    # temkinli davran: SL önce sayılır → kaçan kazancı şişirme).
    mfe_r = 0.0
    for b in bars:
        hi, lo = float(b.high), float(b.low)
        if side == "long":
            mfe_r = max(mfe_r, (hi - entry) / r_unit if r_unit else 0.0)
            hit_sl, hit_tp = lo <= sl, hi >= tp
        else:
            mfe_r = max(mfe_r, (entry - lo) / r_unit if r_unit else 0.0)
            hit_sl, hit_tp = hi >= sl, lo <= tp
        if hit_sl:
            return _resolve_event(tracking, "avoided_loss", now, mfe_r, len(bars))
        if hit_tp:
            return _resolve_event(tracking, "missed_win", now, mfe_r, len(bars))

    ttl_h = cfg.ttl_for(tf)
    if ttl_h > 0 and (now - opened) >= timedelta(hours=ttl_h):
        return _resolve_event(tracking, "expired", now, mfe_r, len(bars))
    return None


def _resolve_event(tracking: dict, outcome: str, now: datetime, mfe_r: float, bars_seen: int) -> dict:
    return {
        "event": "resolve",
        "id": tracking.get("id"),
        "symbol": tracking.get("symbol"),
        "timeframe": tracking.get("timeframe"),
        "side": tracking.get("side"),
        "trade_profile": tracking.get("trade_profile"),
        "setup_type": tracking.get("setup_type"),
        "outcome": outcome,
        # Bugfix 2026-07-02: SL girişe aşırı yakınken r_unit paydası patlıyordu
        # (canlıda 250R görüldü) — gösterge 20R'de kırpılır (win/loss sayımları
        # etkilenmez, yalnız görüntü dürüstlüğü).
        "mfe_r": round(min(mfe_r, 20.0), 3),
        "bars_seen": bars_seen,
        "opened_at": tracking.get("opened_at"),
        "resolved_at": now.isoformat(),
    }


# ----------------- ana giriş (tick loop) -----------------

def scan_and_track(
    record: dict,
    *,
    now: datetime | None = None,
    cfg: MissedOppConfig | None = None,
    get_bars: Callable[[str, str], list[Any]] | None = None,
) -> dict:
    """Bir tick için: (1) aktif izlemeleri çöz, (2) shadow kaydından yeni aday aç.

    Best-effort: hiçbir adım raise etmez (gözlem ASLA tick'i kesmez). Paper'a
    dokunmaz. enabled=false ise inert (boş özet). Çözüm/açılış event'lerini
    append-only loglar. Test için `get_bars` enjekte edilebilir.
    """
    cfg = cfg or load_config()
    summary = {"enabled": cfg.enabled, "resolved": 0, "tracked_new": 0, "active": 0}
    if not cfg.enabled:
        return summary
    now = now or datetime.now(UTC)
    fetch = get_bars or ohlcv.get_bars
    try:
        events = read_recent(limit=DEFAULT_MAX_READ)
        active = _active_trackings(events)

        # (1) Aktif izlemeleri çöz.
        for tid, tracking in list(active.items()):
            try:
                resolved = _resolve_one(tracking, now=now, cfg=cfg, get_bars=fetch)
            except Exception:
                _log.warning("missed_opp resolve failed for %s", tid, exc_info=True)
                resolved = None
            if resolved is not None:
                _append(resolved)
                active.pop(tid, None)
                summary["resolved"] += 1

        # (2) Yeni adayları aç (aynı symbol/tf/side için aktif yoksa).
        snapshot_id = record.get("snapshot_id")
        for cand in _candidates(record):
            if cand.get("rr") and cand["rr"] < cfg.min_rr:
                continue
            side = cand["side"]
            tf = cand["timeframe"]
            symbol = cand["symbol"]
            if cfg.ttl_for(tf) <= 0:
                continue  # izlenmeyen TF (örn. 1w)
            if _has_active_for(active, symbol, tf, side):
                continue
            tid = _tracking_id(snapshot_id, symbol, tf, side)
            open_ev = {
                "event": "track_open",
                "id": tid,
                "symbol": symbol,
                "timeframe": tf,
                "side": side,
                "entry": round(cand["entry"], 6),
                "sl": round(cand["sl"], 6),
                "tp": round(cand["tp"], 6),
                "rr": round(cand.get("rr", 0.0), 3),
                "r_unit": round(abs(cand["entry"] - cand["sl"]), 6),
                "basis": cand.get("basis"),
                "setup_type": cand.get("setup_type"),
                "trade_profile": cand.get("trade_profile"),
                "agreement": cand.get("agreement"),
                "snapshot_id": snapshot_id,
                "opened_at": now.isoformat(),
                "ttl_hours": cfg.ttl_for(tf),
            }
            _append(open_ev)
            active[tid] = open_ev
            summary["tracked_new"] += 1

        summary["active"] = len(active)
    except Exception:
        _log.exception("missed_opp scan_and_track failed (tick devam ediyor)")
    return summary


# ----------------- I/O -----------------

def _append(entry: dict) -> None:
    """Append-only event yazımı (best-effort; asla raise etmez)."""
    try:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def read_recent(limit: int = DEFAULT_MAX_READ) -> list[dict]:
    """Son `limit` event (en yeni en sonda); bozuk satır atlanır."""
    p = _path()
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
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


def resolutions(limit: int = DEFAULT_MAX_READ) -> list[dict]:
    """F5-1 — çözülmüş counterfactual'lar (yalnız `resolve` event'leri).

    Kanıt tüketicileri (empirical_pwin cf-kanalı, edge raporu) için public
    okuyucu; her satır outcome (missed_win/avoided_loss/expired) + tf + side
    + mfe_r taşır. Dosya yok/bozuk → boş liste (crash yok)."""
    return [e for e in read_recent(limit=limit) if e.get("event") == "resolve"]


# ----------------- viewmodel (panel/endpoint) -----------------

def summary_viewmodel(limit: int = DEFAULT_MAX_READ) -> dict:
    """Render-only özet: çözülmüş sonuç sayıları + aktif izlemeler + son olaylar.

    Frontend hesap yapmaz; tüm sayım burada. Veri yoksa available=false kabuk.
    """
    enabled = load_config().enabled
    events = read_recent(limit=limit)
    if not events:
        return {
            "available": False,
            "enabled": enabled,
            "outcomes": {"missed_win": 0, "avoided_loss": 0, "expired": 0},
            "by_profile": {},
            "by_timeframe": {},
            "active": [],
            "recent": [],
        }
    active = _active_trackings(events)
    outcomes = {"missed_win": 0, "avoided_loss": 0, "expired": 0}
    by_profile: dict[str, dict[str, int]] = {}
    for ev in events:
        if ev.get("event") != "resolve":
            continue
        oc = ev.get("outcome")
        if oc in outcomes:
            outcomes[oc] += 1
        prof = ev.get("trade_profile") or "?"
        bp = by_profile.setdefault(prof, {"missed_win": 0, "avoided_loss": 0, "expired": 0})
        if oc in bp:
            bp[oc] += 1
    resolves = [e for e in events if e.get("event") == "resolve"]
    # F5-1 — TF bazlı counterfactual isabet kanıtı: "açsaydık kazanır mıydık?"
    # cf_win_rate = missed_win / (missed_win + avoided_loss); expired paydaya
    # girmez (net sonuç yok). empirical_pwin cf-kanalıyla aynı sayım kuralı.
    by_timeframe: dict[str, dict] = {}
    for ev in resolves:
        tf = str(ev.get("timeframe") or "?")
        bt = by_timeframe.setdefault(
            tf, {"missed_win": 0, "avoided_loss": 0, "expired": 0}
        )
        oc = ev.get("outcome")
        if oc in bt:
            bt[oc] += 1
    for bt in by_timeframe.values():
        n = bt["missed_win"] + bt["avoided_loss"]
        bt["n"] = n
        bt["cf_win_rate"] = round(bt["missed_win"] / n, 4) if n else None
    return {
        "available": True,
        "enabled": enabled,
        "outcomes": outcomes,
        "by_profile": by_profile,
        "by_timeframe": by_timeframe,
        "active": [
            {
                "symbol": a.get("symbol"),
                "timeframe": a.get("timeframe"),
                "side": a.get("side"),
                "trade_profile": a.get("trade_profile"),
                "setup_type": a.get("setup_type"),
                "entry": a.get("entry"),
                "sl": a.get("sl"),
                "tp": a.get("tp"),
                "opened_at": a.get("opened_at"),
            }
            for a in active.values()
        ],
        "recent": list(reversed(resolves[-20:])),
    }
