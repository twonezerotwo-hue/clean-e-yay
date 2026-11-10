"""Kapı karşı-olgu defteri (hedef mimari "Kaçan fırsat", ln_missed): kapıların bedeli.

Karar kaydındaki her aday hücre (open_long / open_short; 1w hariç) için sorulur:
bir sonraki barın açılışında girilseydi, karar anında yakalanan stop/hedef planıyla
(``decision.record._plan`` — açılış yolunun canonical_targets'ı) ne olurdu? Sonuç
karar gününe göre kalıcı yazılır: ``<karar kaydı klasörünün yanı>/gate_counterfactual/
YYYY-MM-DD.jsonl``; saklama karar kaydıyla aynıdır.

Kural (eski kaçan-fırsat kuralıyla aynı, temkinli): yalnız kapanmış barlar; ilk değen
seviye kazanır, aynı barda ikisi değerse stop sayılır; açılış stopun ötesinde gap'lerse
açılış fiyatından çıkılır. Süre stopu dolarsa son kapanışla çıkılır. Trailing ve
kapanış-bazlı stop taklit edilmez. Ayrıca karne ufkunda (15m 8, 1h 8, 4h 6, 1d 1 bar)
yönlü getiri yazılır; plan taşımayan eski kayıtlarda (10 Kasım öncesi) yalnız o vardır.

Satırda kapı yolu: ``blocked_by`` (karar motoru kapıları yazıldığı sırayla; ağır kapılar
ilk engelde durur) + ``final_blocker`` (son kapının ilk düşen kapısı) + ``route``.
``opened`` o turda gerçekten açılan hücredir (kıyas tabanı).

Salt ölçüm: karar, kapı ve defter değişmez; yalnız diskten okur (ağ yok). Kayıt
kaldığı yerden okunur (``state.json``: imleç + çözülmeyi bekleyen adaylar).
"""
from __future__ import annotations

import bisect
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from packages.data.registry.loader import load_thresholds
from packages.decision import record
from packages.learning import benchmark
from packages.ops.store import write_json_atomic

HORIZON_BARS = {"15m": 8, "1h": 8, "4h": 6, "1d": 1}
_TF = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1), "4h": timedelta(hours=4), "1d": timedelta(days=1)}
_SIDES = {"open_long": "long", "open_short": "short"}
_MAX_PENDING = timedelta(days=31)  # en uzun süre stopu (1d, 28 gün) + pay; bar gelmezse bırakılır


def _dir() -> Path:
    return record._dir().parent / "gate_counterfactual"


def _ts(value: Any) -> datetime:
    out = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return out if out.tzinfo else out.replace(tzinfo=UTC)


def _cost_pct(symbol: str) -> float:
    table = (load_thresholds().get("ev_gate") or {}).get("round_trip_cost_pct") or {}
    return float(table.get(symbol, table.get("default", 0.0)))


def _sample(ts: str, cell: dict) -> dict | None:
    side, tf = _SIDES.get(cell.get("candidate")), cell.get("timeframe")
    if side is None or tf not in HORIZON_BARS:
        return None
    return {
        "ts": ts, "decision_id": cell.get("decision_id"), "symbol": cell.get("symbol"), "timeframe": tf,
        "side": side, "action": cell.get("action"), "route": cell.get("route"),
        "final_blocker": cell.get("gate_blocker"), "blocked_by": list(cell.get("blocked_by") or ()),
        "opened": bool(cell.get("opened")), "score": cell.get("score"), "confidence": cell.get("confidence"),
        "ev": cell.get("ev"), "plan": cell.get("plan"),
    }


def _bucket(sample: dict) -> str:
    """Aynı karar barındaki tekrarlar tek aday sayılır (ilk kayıt kalır)."""
    step = _TF[sample["timeframe"]].total_seconds()
    start = int(_ts(sample["ts"]).timestamp() // step * step)
    return f"{sample['symbol']}|{sample['timeframe']}|{sample['side']}|{start}"


Bars = tuple[list[datetime], list[tuple[datetime, float, float, float, float]]]


def bar_rows(bars: list) -> Bars:
    """(açılış zamanları, (ts, open, high, low, close)) — sıralı; ikili arama için."""
    rows = sorted((_ts(b.ts.isoformat()), float(b.open), float(b.high), float(b.low), float(b.close)) for b in bars)
    return [r[0] for r in rows], rows


def _bars(symbol: str, tf: str, memo: dict) -> Bars:
    if (symbol, tf) not in memo:
        from packages.data.providers.ohlcv import cache, history

        try:
            live = cache.load(symbol, tf)
            memo[(symbol, tf)] = bar_rows(history.merged(history.load(symbol, tf), list(live.bars) if live else []))
        except Exception:
            memo[(symbol, tf)] = ([], [])
    return memo[(symbol, tf)]


def resolve(sample: dict, bars: Bars, now: datetime) -> dict | None:
    """Adayın sonucu; barlar henüz yetmiyorsa None (aday beklemede kalır)."""
    step = _TF[sample["timeframe"]]
    stamps, rows = bars
    closed = rows[bisect.bisect_right(stamps, _ts(sample["ts"])):bisect.bisect_right(stamps, now - step)]
    horizon = HORIZON_BARS[sample["timeframe"]]
    if len(closed) < horizon:
        return None
    first_ts, entry = closed[0][0], closed[0][1]
    sign = 1.0 if sample["side"] == "long" else -1.0
    ret = sign * (closed[horizon - 1][4] - entry) / entry * 100.0
    out = {**sample, "id": f"{sample['symbol']}|{sample['timeframe']}|{sample['side']}|{first_ts.isoformat()}",
           "entry_ts": first_ts.isoformat(), "entry": entry, "horizon_bars": horizon,
           "ret_pct": round(ret, 4), "net_ret_pct": round(ret - _cost_pct(sample["symbol"]), 4),
           "outcome": None, "exit_bar_ts": None, "r": None, "net_r": None}
    plan = sample.get("plan") or {}
    sl_pct, tp_pct = float(plan.get("sl_pct") or 0), float(plan.get("tp_pct") or 0)
    if sl_pct <= 0 or tp_pct <= 0:
        return out
    sl, tp = entry * (1 - sign * sl_pct), entry * (1 + sign * tp_pct)
    end = first_ts + timedelta(hours=float(plan.get("time_stop_h") or 0))
    exit_px = outcome = last = None
    for bar in closed:
        ts, op, hi, lo, _close = bar
        if ts >= end:
            break
        last = bar
        if (lo <= sl) if sign > 0 else (hi >= sl):
            outcome, exit_px = "sl", (min(op, sl) if sign > 0 else max(op, sl))
        elif (hi >= tp) if sign > 0 else (lo <= tp):
            outcome, exit_px = "tp", tp
        if outcome:
            break
    if outcome is None:
        if now < end or last is None:
            return None  # süre stopu henüz dolmadı (paper'daki gibi gerçek zaman)
        outcome, exit_px = "time", last[4]
    r = sign * (exit_px - entry) / (entry * sl_pct)
    cost_r = benchmark.trade_cost_r(SimpleNamespace(symbol=sample["symbol"], risk_pct=sl_pct))
    out.update(outcome=outcome, exit_bar_ts=last[0].isoformat(), r=round(r, 4), net_r=round(r - cost_r, 4))
    return out


def _load_state() -> dict:
    try:
        return json.loads((_dir() / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"day": None, "line": 0, "pending": {}}


def _save_state(state: dict) -> None:
    write_json_atomic(_dir() / "state.json", state, ensure_ascii=False)


def _read_new(state: dict) -> list[dict]:
    """İmleçten sonraki tam satırların adayları; imleç ilerletilir (yarım satır beklenir)."""
    folder, out = record._dir(), []
    days = sorted(p.stem for p in folder.glob("????-??-??.jsonl"))
    for day in (d for d in days if state["day"] is None or d >= state["day"]):
        lines = (folder / f"{day}.jsonl").read_text(encoding="utf-8").split("\n")[:-1]
        start = state["line"] if day == state["day"] else 0
        for line in lines[start:]:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            out.extend(s for s in (_sample(row.get("ts"), c) for c in row.get("cells") or ()) if s)
        state["day"], state["line"] = day, len(lines)
    return out


def run(now: datetime | None = None) -> dict[str, Any]:
    """Yeni adayları ekle, barı yetenleri çöz ve yaz; ne yapıldığını döner."""
    now = now or datetime.now(UTC)
    _dir().mkdir(parents=True, exist_ok=True)
    state = _load_state()
    pending: dict[str, dict] = state["pending"]
    new = 0
    for sample in _read_new(state):
        key = _bucket(sample)
        if key not in pending:
            pending[key], new = sample, new + 1
    memo: dict = {}
    written: dict[str, set[str]] = {}
    resolved = dropped = 0
    for key, sample in list(pending.items()):
        row = resolve(sample, _bars(sample["symbol"], sample["timeframe"], memo), now)
        if row is None:
            if now - _ts(sample["ts"]) > _MAX_PENDING:
                del pending[key]
                dropped += 1
            continue
        del pending[key]
        day = _ts(sample["ts"]).date().isoformat()
        path = _dir() / f"{day}.jsonl"
        if day not in written:
            written[day] = {json.loads(line).get("id") for line in path.read_text(encoding="utf-8").splitlines()
                            if line.strip()} if path.exists() else set()
        if row["id"] in written[day]:
            continue  # aynı giriş barı başka bir karar barından zaten yazıldı
        written[day].add(row["id"])
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        resolved += 1
    _save_state(state)
    record._prune(_dir(), now)
    return {"status": "OK", "new": new, "resolved": resolved, "pending": len(pending), "dropped": dropped}


def load_day(day: str) -> list[dict]:
    path = _dir() / f"{day}.jsonl"
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError):
        return []


__all__ = ["HORIZON_BARS", "bar_rows", "load_day", "resolve", "run"]
