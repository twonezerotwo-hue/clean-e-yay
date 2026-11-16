"""Günlük "neden kaçırdım" incelemesi — dünün büyük hareketleri ve sistemin onlara karşı ne yaptığı.

Salt gözlemci: karar vermez; kapıya, ağırlığa, pozisyona dokunmaz. Her UTC günü için bir kez
(ertesi gün 00:15 UTC'den sonraki ilk öğrenme koşusunda; bilgisayar uyuyorsa ilk uyanışta)
`data/runtime/daily_review/YYYY-MM-DD.json` yazar ve owner'a özet bildirimi gönderir.

Büyük hareket: sembolün gün içi getirisi, kendi 1h oynaklığına göre (önceki 168 bar σ · √(gündeki bar
sayısı)) |z| ≥ 1,5; en fazla 5 sembol, |z| büyükten küçüğe. Her biri için:
  YAKALANDI — gün içinde hareket yönünde açılmış/tutulmuş paper pozisyon var;
  TERS      — yalnız ters yönde pozisyon var;
  KAÇIRILDI — hiç pozisyon yok.
Kaçırılan/ters hareketlerde: karar kaydından (checkpoint + delta yeniden kurulumu) o yönde aday kaç
saat vardı ve saatlerce hangi kapı durdurdu; aday hiç yoksa sistemin o gün ne gördüğü. Ayrıca o
sembole bağlanan başlık sayısı ve ortanca gecikmesi, sistemin gün içinde kapalı kaldığı süre
(karar kaydında 45 dakikadan uzun boşluk; uyanıkken en uzun boşluk ~24 dk ölçüldü).
"""
from __future__ import annotations

import json
import math
import os
import statistics
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

from packages.notifications import Notification, make_id
from packages.ops.store import write_text_atomic

Z_MIN = 1.5
MAX_MOVERS = 5
SIGMA_BARS = 168
MIN_SIGMA_BARS = 48
DOWNTIME_GAP_SEC = 45 * 60
DUE_AFTER = timedelta(minutes=15)
TFS = ("1h", "15m", "4h", "1d")  # görüş önceliği; 1w yalnız yön bilgisi (paper açmaz)
REDUCERS = {"entry_quality_v2:reduce", "kelly_cap", "sizing_layers"}
BLOCKER_TR = {
    "ev_gate": "beklenen değer kapısı", "confidence_floor": "güven tabanı",
    "entry_quality_v2": "giriş kalitesi", "risk_gate": "risk kapısı",
    "concentration_guard": "yoğunlaşma sınırı", "market_closed": "piyasa kapalı",
    "stale_ohlcv": "veri bayat", "catalyst_risk": "olay riski", "volatility_risk": "oynaklık riski",
    "coverage_gate": "kanıt kapsamı", "correlation_veto": "korelasyon", "session_gate": "seans",
    "technical_confirmation": "teknik teyit", "1w_bias_conflict": "haftalık yön çatışması",
    "self_conflict_guard": "kendi çelişkisi", "paper_exploration": "keşif yolu",
}


@dataclass
class Mover:
    symbol: str
    pct: float
    z: float
    status: str = ""                 # YAKALANDI | TERS | KAÇIRILDI
    pnl: float = 0.0                 # gün içinde bu sembolde kapanan işlemlerin toplamı ($)
    candidate_hours: int = 0         # hareket yönünde aday görülen saat sayısı
    opposite_hours: int = 0          # ters yönde aday görülen saat sayısı
    blockers: list[tuple[str, int]] = field(default_factory=list)  # (kapı, saat)
    headlines: int = 0
    with_move: int = 0               # hareket yönünde etiketli başlık
    median_lag_min: float | None = None


def _ep(s: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _blocker(blocked_by: Iterable[Any] | None) -> str:
    for b in blocked_by or []:
        b = str(b)
        if b in REDUCERS:
            continue
        return b.split(":")[0]
    return ""


# ---------------------------------------------------------------------------
# Saf hesaplar
# ---------------------------------------------------------------------------

def day_move(bars: Sequence[tuple[float, float]], day_start: float, day_end: float) -> tuple[float, float] | None:
    """(ts, kapanış) sıralı tamamlanmış barlar → (yüzde, z). Gün içinde bar yoksa None."""
    before = [c for t, c in bars if t < day_start]
    inside = [c for t, c in bars if day_start <= t < day_end]
    if not before or not inside or len(before) < MIN_SIGMA_BARS + 1:
        return None
    hist = before[-(SIGMA_BARS + 1):]
    if any(c <= 0 for c in hist) or inside[-1] <= 0:
        return None
    rets = [math.log(hist[k + 1] / hist[k]) for k in range(len(hist) - 1)]
    sd = statistics.stdev(rets) if len(rets) >= MIN_SIGMA_BARS else 0.0
    if sd <= 0:
        return None
    r = math.log(inside[-1] / before[-1])
    return (inside[-1] / before[-1] - 1) * 100, r / (sd * math.sqrt(len(inside)))


def exposure(symbol: str, up: bool, trades: Iterable[dict[str, Any]], open_positions: Iterable[dict[str, Any]],
             day_start: float, day_end: float) -> tuple[str, float]:
    """Gün içinde bu sembolde hangi yönde paper pozisyon açıktı; günün kapanan pnl'i.

    trades: kapanmış işlemler {symbol, side, opened_at, closed_at, pnl} (kanonik sonuç defteri).
    Günden önce açılıp sonra kapanan işlem de o gün açıktır. Denetim kaydı kullanılmaz: orada
    kapanış satırı olmayan binlerce eski açılış var (sıfırlama/onarım/risk kapatmaları)."""
    want = "long" if up else "short"
    sides: set[str] = set()
    pnl = 0.0
    for tr in trades:
        if tr.get("symbol") != symbol:
            continue
        opened, closed = _ep(tr.get("opened_at")), _ep(tr.get("closed_at"))
        if opened is None or closed is None:
            continue
        if opened < day_end and closed >= day_start:
            sides.add(str(tr.get("side")))
        if day_start <= closed < day_end:
            try:
                pnl += float(tr.get("pnl") or 0.0)
            except (TypeError, ValueError):
                pass
    for p in open_positions:
        t = _ep(p.get("opened_at"))
        if p.get("symbol") == symbol and t is not None and t < day_end:
            sides.add(str(p.get("side")))
    if want in sides:
        return "YAKALANDI", pnl
    if sides:
        return "TERS", pnl
    return "KAÇIRILDI", pnl


def hourly_view(seed_cells: Iterable[dict[str, Any]], rows: Iterable[dict[str, Any]],
                day_start: float, day_end: float) -> dict[str, dict[tuple[str, str], str]]:
    """Karar kaydını checkpoint + delta sırasıyla yeniden kurar; her saat için o saatin son hâlinde
    (sembol, yön) → ilk engel ("açıldı" ya da kapı adı). Yalnız aday olan hücreler."""
    state: dict[tuple[Any, Any], dict[str, Any]] = {(c.get("symbol"), c.get("timeframe")): c for c in seed_cells}
    out: dict[str, dict[tuple[str, str], str]] = {}

    def summarize() -> dict[tuple[str, str], str]:
        best: dict[tuple[str, str], tuple[int, str]] = {}
        for (sym, tf), c in state.items():
            if tf not in TFS:
                continue
            cand = str(c.get("candidate") or "")
            if cand not in ("open_long", "open_short"):
                continue
            side = "long" if cand == "open_long" else "short"
            label = "açıldı" if c.get("action") == cand else (_blocker(c.get("blocked_by")) or "diğer")
            rank = TFS.index(tf)
            if (sym, side) not in best or rank < best[(sym, side)][0]:
                best[(str(sym), side)] = (rank, label)
        return {k: v[1] for k, v in best.items()}

    current_hour = None
    for row in rows:
        t = _ep(row.get("ts"))
        if t is None or t >= day_end:
            continue
        if t >= day_start:
            hour = datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%dT%H")
            if current_hour is not None and hour != current_hour:
                out[current_hour] = summarize()
            current_hour = hour
        if row.get("kind") == "checkpoint":
            state = {}
        for c in row.get("cells") or []:
            if isinstance(c, dict):
                state[(c.get("symbol"), c.get("timeframe"))] = c
    if current_hour is not None:
        out[current_hour] = summarize()
    return out


def downtime_hours(record_ts: Sequence[float], day_start: float, day_end: float) -> float:
    pts = sorted(t for t in record_ts if day_start <= t < day_end)
    if not pts:
        return (day_end - day_start) / 3600
    off = 0.0
    edges = [day_start, *pts, day_end]
    for a, b in pairwise(edges):
        if b - a > DOWNTIME_GAP_SEC:
            off += b - a
    return off / 3600


def news_stats(symbol: str, up: bool, headlines: Iterable[dict[str, Any]], day_start: float,
               day_end: float) -> tuple[int, int, float | None]:
    n = with_move = 0
    lags = []
    for h in headlines:
        tags = h.get("symbols") or {}
        if symbol not in tags:
            continue
        t = _ep(h.get("ts"))
        if t is None or not (day_start <= t < day_end):
            continue
        n += 1
        try:
            v = float(tags[symbol])
        except (TypeError, ValueError):
            v = 0.0
        with_move += (v > 0) == up and v != 0
        r = _ep(h.get("recorded_at"))
        if r is not None and r >= t:
            lags.append((r - t) / 60)
    return n, with_move, (statistics.median(lags) if lags else None)


def review(day: date, *, bars: dict[str, Sequence[tuple[float, float]]], trades: Sequence[dict[str, Any]],
           open_positions: Sequence[dict[str, Any]], seed_cells: Sequence[dict[str, Any]],
           record_rows: Sequence[dict[str, Any]], headlines: Sequence[dict[str, Any]]) -> dict[str, Any]:
    day_start = datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp()
    day_end = day_start + 86400
    movers: list[Mover] = []
    for sym, series in bars.items():
        mv = day_move(series, day_start, day_end)
        if mv and abs(mv[1]) >= Z_MIN:
            movers.append(Mover(sym, round(mv[0], 3), round(mv[1], 2)))
    movers = sorted(movers, key=lambda m: -abs(m.z))[:MAX_MOVERS]
    hours = hourly_view(seed_cells, record_rows, day_start, day_end)
    for m in movers:
        up = m.pct > 0
        side = "long" if up else "short"
        other = "short" if up else "long"
        m.status, pnl = exposure(m.symbol, up, trades, open_positions, day_start, day_end)
        m.pnl = round(pnl, 2)
        blk: Counter[str] = Counter()
        for view in hours.values():
            if (m.symbol, side) in view:
                m.candidate_hours += 1
                blk[view[(m.symbol, side)]] += 1
            if (m.symbol, other) in view:
                m.opposite_hours += 1
        m.blockers = blk.most_common(3)
        m.headlines, m.with_move, lag = news_stats(m.symbol, up, headlines, day_start, day_end)
        m.median_lag_min = None if lag is None else round(lag, 1)
    off = downtime_hours([t for t in (_ep(r.get("ts")) for r in record_rows) if t is not None], day_start, day_end)
    return {"day": day.isoformat(), "generated_at": datetime.now(UTC).isoformat(), "z_min": Z_MIN,
            "downtime_hours": round(off, 1), "movers": [asdict(m) for m in movers]}


def _pct(x: float) -> str:
    return f"{'+' if x >= 0 else '−'}%{abs(x):.1f}".replace(".", ",")


STATUS_TR = {"YAKALANDI": "yakalandı", "TERS": "ters yönde", "KAÇIRILDI": "kaçırıldı"}


def _mover_line(i: int, m: dict[str, Any]) -> str:
    head = f"{i}) {m['symbol']} {_pct(m['pct'])} (normalin {abs(m['z']):.1f} katı)".replace(".", ",")
    if m["status"] == "YAKALANDI":
        body = (f"YAKALANDI; günün kapanan sonucu {m['pnl']:+.2f} $".replace(".", ",") if m["pnl"]
                else "YAKALANDI; pozisyon açıktı, o gün kapanış yok")
    else:
        side = "long" if m["pct"] > 0 else "short"
        body = "KAÇIRILDI" if m["status"] == "KAÇIRILDI" else "TERS YÖNDE POZİSYON"
        if m["candidate_hours"]:
            blk = ", ".join(f"{BLOCKER_TR.get(b, b)} ({n} sa)" for b, n in m["blockers"])
            body += f" — {m['candidate_hours']} saat {side} adayı vardı; durduran: {blk}"
        else:
            body += " — sistem bu yönde aday görmedi" + (
                f" (ters yönde {m['opposite_hours']} saat aday vardı)" if m["opposite_hours"] else "")
    news = (f"haber {m['headlines']} başlık (hareket yönünde: {m['with_move']}), ortanca gecikme "
            f"{m['median_lag_min']:.0f} dk" if m["headlines"] and m["median_lag_min"] is not None
            else f"haber {m['headlines']} başlık")
    return f"{head}: {body}; {news}."


def notification(report: dict[str, Any], now: datetime) -> Notification:
    movers = report["movers"]
    d = datetime.fromisoformat(report["day"]).strftime("%d.%m")
    missed = [m for m in movers if m["status"] != "YAKALANDI"]
    if movers:
        title = f"Günlük inceleme {d}: {len(movers)} büyük hareket, {len(missed)} kaçırıldı/ters"
        short = " · ".join(f"{m['symbol']} {_pct(m['pct'])} {STATUS_TR.get(m['status'], m['status'])}" for m in movers[:3])
    else:
        title = f"Günlük inceleme {d}: büyük hareket yok"
        short = "Hiçbir sembol kendi oynaklığının 1,5 katını aşmadı."
    lines = [_mover_line(i, m) for i, m in enumerate(movers, 1)] or [short]
    off = report.get("downtime_hours") or 0.0
    if off >= 0.5:
        lines.append(f"Sistem günün {off:.1f} saatinde kapalıydı (karar kaydında 45 dk'dan uzun boşluk)."
                     .replace(".", ",", 1))
    lines.append("Bu rapor yalnız gözlemdir; karar kapıları, ağırlıklar ve pozisyonlar değişmedi.")
    return Notification(
        id=make_id("daily_review"), ts=now.isoformat(), type="review_recommendation",
        priority="medium", title=title, body_short=short, body_long=" ".join(lines),
    )


# ---------------------------------------------------------------------------
# Çalışma zamanı yapıştırıcısı (öğrenme döngüsü çağırır)
# ---------------------------------------------------------------------------

def _runtime() -> Path:
    return Path(os.environ.get("DECISION_RECORD_DIR", "data/runtime/decision_record")).parent


def _read_jsonl(path: Path, tail_bytes: int | None = None) -> list[dict[str, Any]]:
    try:
        with path.open("rb") as fh:
            if tail_bytes is not None:
                fh.seek(0, os.SEEK_END)
                fh.seek(max(0, fh.tell() - tail_bytes))
            lines = fh.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _closed_trades() -> list[dict[str, Any]]:
    from packages.learning import outcomes as outcomes_mod

    return [{"symbol": o.symbol, "side": o.direction, "opened_at": o.opened_at, "closed_at": o.closed_at,
             "pnl": o.pnl} for o in outcomes_mod.outcomes_from_state()]


def _seed(prev_file: Path) -> list[dict[str, Any]]:
    """Önceki günün son checkpoint'i + sonraki deltalar (günün ilk saatini doldurmak için)."""
    rows = _read_jsonl(prev_file, tail_bytes=3_000_000)
    start = max((i for i, r in enumerate(rows) if r.get("kind") == "checkpoint"), default=None)
    if start is None:
        return []
    state: dict[tuple[Any, Any], dict[str, Any]] = {}
    for r in rows[start:]:
        for c in r.get("cells") or []:
            if isinstance(c, dict):
                state[(c.get("symbol"), c.get("timeframe"))] = c
    return list(state.values())


def run_if_due(now: datetime | None = None) -> dict[str, Any] | None:
    """Dünün raporu yoksa ve 00:15 UTC geçtiyse üretir, yazar, bildirim ekler. Yalnız dün (geriye dolum yok)."""
    from packages.data.providers.ohlcv import cache
    from packages.data.registry import assets as asset_registry
    from packages.notifications import append

    now = now or datetime.now(UTC)
    today = now.astimezone(UTC).date()
    if now.astimezone(UTC) - datetime(today.year, today.month, today.day, tzinfo=UTC) < DUE_AFTER:
        return None
    day = today - timedelta(days=1)
    out_path = _runtime() / "daily_review" / f"{day.isoformat()}.json"
    if out_path.exists():
        return None
    rec_dir = Path(os.environ.get("DECISION_RECORD_DIR", "data/runtime/decision_record"))
    record_rows = _read_jsonl(rec_dir / f"{day.isoformat()}.jsonl")
    seed = _seed(rec_dir / f"{(day - timedelta(days=1)).isoformat()}.jsonl")
    bars: dict[str, list[tuple[float, float]]] = {}
    for sym in asset_registry.trade_symbols():
        cached = cache.load(sym, "1h")
        if cached is not None:
            bars[sym] = sorted({b.ts.timestamp(): float(b.close) for b in cached.bars
                                if b.ts.timestamp() + 3600 <= now.timestamp()}.items())
    trades = _closed_trades()
    try:
        state = json.loads(Path(os.environ.get("PAPER_STATE_PATH", "data/runtime/paper_state.json")).read_text(encoding="utf-8"))
        positions = [p for p in (state.get("open_positions") or []) if isinstance(p, dict)]
    except (OSError, ValueError, AttributeError):
        positions = []
    headlines = _read_jsonl(Path(os.environ.get("NEWS_EVENT_LEDGER_PATH", "data/runtime/news_event_ledger.jsonl")),
                            tail_bytes=6_000_000)
    report = review(day, bars=bars, trades=trades, open_positions=positions, seed_cells=seed,
                    record_rows=record_rows, headlines=headlines)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(out_path, json.dumps(report, ensure_ascii=False, indent=1))
    append(notification(report, now))
    return report


__all__ = ["Mover", "day_move", "downtime_hours", "exposure", "hourly_view", "news_stats", "notification",
           "review", "run_if_due"]
