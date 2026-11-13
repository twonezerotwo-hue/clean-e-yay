"""Piyasa şoku bildirimi — sert hareket olunca owner'a "ne oluyor" özeti.

Salt gözlemci: karar vermez; kapıya, ağırlığa, pozisyona dokunmaz. Yalnız bildirim
üretir ve bildirim işlem önerisi değildir (karar ve risk kapıları aynen çalışır).

Ölçü: sembol başına σ = son 168 saatlik 1h log-getirilerin örneklem standart sapması
(en az 48). Son TAMAMLANMIŞ 1h barda h ∈ {1, 3, 6, 24} için z_h = getiri_h / (σ·√h);
sembolün skoru |z|'si en büyük ufuktur. Tetik, aynı bar zamanındaki semboller için:
  çapraz — ≥ 4 sembol |z| ≥ 2,5 ve ≥ 2 varlık sınıfı;
  tek    — bir sembol |z| ≥ 5.
Bildirilen sembol 6 saat boyunca yeniden bildirilmez (durum dosyası yeniden başlatmada korunur).
Eşikler 13 Kasım 2026'da son 60 günün 1h barlarında yalnız SIKLIK kuralıyla seçildi
(≤ 1 bildirim/gün → 0,89/gün); kazanç ölçütü değildir.

Bildirim tipi ``event_outcome``: olay → piyasa tepkisi ailesi (sözleşmedeki sabit listede
ayrı tip yok; arayüz tipleri ayrı göstermez).
"""
from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.notifications import Notification, make_id
from packages.ops.store import write_text_atomic

HORIZONS: tuple[int, ...] = (1, 3, 6, 24)
SIGMA_BARS = 168
MIN_SIGMA_BARS = 48
K_CROSS = 2.5
N_CROSS = 4
MIN_CLASSES = 2
K_SINGLE = 5.0
COOLDOWN_SEC = 6 * 3600
FRESH_SEC = 2 * 3600
BAR_SEC = 3600
HEADLINE_WINDOW_SEC = 3 * 3600

_CLASS_TR = {
    "crypto": "kripto", "precious_metal": "değerli metal", "energy": "enerji",
    "industrial_metals": "sanayi metali", "equity": "hisse/ETF", "risk": "hisse",
}
_BLOCKER_TR = {
    "ev_gate": "beklenen değer kapısı", "confidence_floor": "güven tabanı",
    "entry_quality_v2": "giriş kalitesi", "risk_gate": "risk kapısı",
    "concentration_guard": "yoğunlaşma sınırı", "market_closed": "piyasa kapalı",
    "catalyst_risk": "olay riski", "volatility_risk": "oynaklık riski",
    "coverage_gate": "kanıt kapsamı", "correlation_veto": "korelasyon", "session_gate": "seans",
}
_RISK_TR = {
    "ALLOW_NORMAL": "normal", "WATCH": "izleme", "NO_POSITION_INCREASE": "yeni giriş durdu",
    "RISK_REDUCE": "boyut azaltma", "KILL_SWITCH": "tüm girişler durdu",
}


@dataclass(frozen=True)
class Move:
    symbol: str
    asset_class: str
    bar_ts: float      # son tamamlanmış barın açılış zamanı (epoch sn)
    z: float           # oynaklığa göre ölçeklenmiş hareket (işaretli)
    hours: int         # z'nin geldiği ufuk
    pct: float         # o ufuktaki yüzde getiri


def score(closes: Sequence[float]) -> tuple[float, int, float] | None:
    """Son bar için (z, ufuk, yüzde). σ son barın getirisini içermez."""
    i = len(closes) - 1
    if i < MIN_SIGMA_BARS + 1 or any(c <= 0 for c in closes[max(0, i - SIGMA_BARS - max(HORIZONS) - 1):]):
        return None
    rets = [math.log(closes[k + 1] / closes[k]) for k in range(max(0, i - 1 - SIGMA_BARS), i - 1)]
    if len(rets) < MIN_SIGMA_BARS:
        return None
    mu = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mu) ** 2 for r in rets) / (len(rets) - 1))
    if sd <= 0:
        return None
    best: tuple[float, int, float] | None = None
    for h in HORIZONS:
        if i - h < 0:
            continue
        z = math.log(closes[i] / closes[i - h]) / (sd * math.sqrt(h))
        if best is None or abs(z) > abs(best[0]):
            best = (z, h, (closes[i] / closes[i - h] - 1) * 100)
    return best


def scan(moves: Iterable[Move], last_alert: dict[str, float]) -> list[tuple[str, list[Move]]]:
    """Aynı bar zamanındaki semboller birlikte değerlendirilir; soğumadaki semboller sayılmaz."""
    groups: dict[float, list[Move]] = defaultdict(list)
    for m in moves:
        if m.bar_ts - last_alert.get(m.symbol, -1e18) >= COOLDOWN_SEC:
            groups[m.bar_ts].append(m)
    fired: list[tuple[str, list[Move]]] = []
    for _ts, group in sorted(groups.items()):
        big = [m for m in group if abs(m.z) >= K_CROSS]
        if len(big) >= N_CROSS and len({m.asset_class for m in big}) >= MIN_CLASSES:
            fired.append(("çapraz", sorted(big, key=lambda m: -abs(m.z))))
            continue
        single = [m for m in group if abs(m.z) >= K_SINGLE]
        if single:
            fired.append(("tek", sorted(single, key=lambda m: -abs(m.z))))
    return fired


def _pct(x: float) -> str:
    return f"{'+' if x >= 0 else '−'}%{abs(x):.1f}".replace(".", ",")


def _move_txt(m: Move) -> str:
    return f"{m.symbol} {_pct(m.pct)} ({m.hours} sa, normalin {abs(m.z):.1f} katı)".replace(".", ",")


def _blocker_txt(blocked_by: Any) -> str:
    for b in blocked_by or []:
        b = str(b)
        if b in ("entry_quality_v2:reduce", "kelly_cap", "sizing_layers"):
            continue
        return _BLOCKER_TR.get(b.split(":")[0], b.split(":")[0])
    return ""


def build(kind: str, chosen: Sequence[Move], now: datetime, *, headlines: Sequence[dict[str, Any]] = (),
          positions: Sequence[dict[str, Any]] = (), cells: Sequence[dict[str, Any]] = (),
          risk_action: str | None = None) -> Notification:
    syms = [m.symbol for m in chosen]
    up = sum(m.z > 0 for m in chosen)
    direction = "yukarı" if up == len(chosen) else "aşağı" if up == 0 else "karışık"
    classes = sorted({_CLASS_TR.get(m.asset_class, m.asset_class) for m in chosen})
    title = "Sert hareket: " + ", ".join(f"{m.symbol} {_pct(m.pct)}" for m in chosen[:3])

    lines = [f"Ne oldu ({'birden çok varlık' if kind == 'çapraz' else 'tek varlık'}, yön {direction}; "
             f"{', '.join(classes)}): " + "; ".join(_move_txt(m) for m in chosen[:6]) + "."]
    now_ts = now.timestamp()
    rel = []
    for h in headlines:
        tags = set((h.get("symbols") or {}).keys())
        try:
            age = now_ts - datetime.fromisoformat(str(h.get("ts")).replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            continue
        if tags & set(syms) and 0 <= age <= HEADLINE_WINDOW_SEC:
            rel.append((age, h))
    rel.sort(key=lambda x: x[0])
    if rel:
        lines.append("İlgili başlıklar: " + " | ".join(
            f"“{str(h.get('title', ''))[:110]}” ({h.get('source', '?')}, {int(age // 60)} dk önce)" for age, h in rel[:3]))
    else:
        lines.append("Bu sembollere bağlı başlık yok (son 3 saat); haberler ortalama ~30 dk gecikmeli gelir.")
    pos_txt = []
    for p in positions:
        m = next((x for x in chosen if x.symbol == p.get("symbol")), None)
        if m is None:
            continue
        good = (p.get("side") == "long") == (m.z > 0)
        pos_txt.append(f"{p.get('symbol')} {p.get('timeframe', '')} {p.get('side')} ({'lehte' if good else 'ALEYHTE'})")
    lines.append("Açık pozisyon: " + (", ".join(pos_txt) if pos_txt else "bu sembollerde yok") + ".")
    view = []
    for sym in syms[:6]:
        mine = {c.get("timeframe"): c for c in cells if c.get("symbol") == sym}
        for tf in ("1h", "15m", "4h", "1d"):
            c = mine.get(tf)
            if not c:
                continue
            cand = str(c.get("candidate") or "")
            if cand in ("open_long", "open_short"):
                side = "long" if cand == "open_long" else "short"
                if c.get("action") == cand:
                    view.append(f"{sym} {tf}: {side} açılıyor")
                else:
                    why = _blocker_txt(c.get("blocked_by"))
                    view.append(f"{sym} {tf}: {side} adayı" + (f", engel: {why}" if why else ""))
            else:
                view.append(f"{sym} {tf}: aday yok")
            break
    if view:
        lines.append("Sistemin görüşü: " + "; ".join(view) + ".")
    if risk_action:
        lines.append(f"Risk seviyesi: {_RISK_TR.get(risk_action, risk_action)}.")
    lines.append("Bu bildirim işlem önerisi değildir; karar kapıları ve pozisyonlar değişmedi.")
    adverse = any("ALEYHTE" in t for t in pos_txt)
    return Notification(
        id=make_id("market_shock"),
        ts=now.isoformat(),
        type="event_outcome",
        priority="critical" if adverse else "high",
        title=title,
        body_short="; ".join(_move_txt(m) for m in chosen[:3]),
        body_long=" ".join(lines),
    )


# ---------------------------------------------------------------------------
# Çalışma zamanı yapıştırıcısı (öğrenme döngüsü çağırır)
# ---------------------------------------------------------------------------

def _state_path() -> Path:
    return Path(os.environ.get("MARKET_SHOCK_STATE_PATH", "data/runtime/market_shock_state.json"))


def _load_state() -> dict[str, Any]:
    try:
        raw = json.loads(_state_path().read_text(encoding="utf-8"))
        return {"last_alert": {str(k): float(v) for k, v in (raw.get("last_alert") or {}).items()}}
    except (OSError, ValueError, TypeError, AttributeError):
        return {"last_alert": {}}


def _tail_jsonl(path: Path, max_lines: int) -> list[dict[str, Any]]:
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 400_000))
            data = fh.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in data[-max_lines:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _latest_record() -> dict[str, Any]:
    root = Path(os.environ.get("DECISION_RECORD_DIR", "data/runtime/decision_record"))
    try:
        files = sorted(root.glob("*.jsonl"))
    except OSError:
        return {}
    for f in reversed(files[-2:]):
        rows = _tail_jsonl(f, 5)
        if rows:
            return rows[-1]
    return {}


def _positions() -> list[dict[str, Any]]:
    path = Path(os.environ.get("PAPER_STATE_PATH", "data/runtime/paper_state.json"))
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [p for p in (raw.get("open_positions") or []) if isinstance(p, dict)]


def check(now: datetime | None = None) -> list[Notification]:
    """Son tamamlanmış 1h barları tarar; tetik varsa bildirim(ler) döner ve soğuma durumunu yazar."""
    from packages.data.providers.ohlcv import cache
    from packages.data.registry import assets as asset_registry

    now = now or datetime.now(UTC)
    now_ts = now.timestamp()
    moves: list[Move] = []
    for sym in asset_registry.trade_symbols():
        cached = cache.load(sym, "1h")
        if cached is None:
            continue
        by_ts = {b.ts.timestamp(): float(b.close) for b in cached.bars if b.ts.timestamp() + BAR_SEC <= now_ts}
        if not by_ts:
            continue
        ts = sorted(by_ts)
        if now_ts - (ts[-1] + BAR_SEC) > FRESH_SEC:
            continue  # piyasa kapalı / veri bayat: bu sembol bu turda yok sayılır
        s = score([by_ts[t] for t in ts])
        if s is None:
            continue
        asset = asset_registry.get(sym)
        moves.append(Move(sym, str(getattr(asset, "asset_class", "") or ""), ts[-1], *s))
    state = _load_state()
    fired = scan(moves, state["last_alert"])
    if not fired:
        return []
    record = _latest_record()
    headlines = _tail_jsonl(Path(os.environ.get("NEWS_EVENT_LEDGER_PATH", "data/runtime/news_event_ledger.jsonl")), 400)
    out = []
    for kind, chosen in fired:
        out.append(build(kind, chosen, now, headlines=headlines, positions=_positions(),
                         cells=record.get("cells") or [], risk_action=record.get("risk_action")))
        for m in chosen:
            state["last_alert"][m.symbol] = m.bar_ts
    write_text_atomic(_state_path(), json.dumps(state))
    return out


__all__ = ["Move", "build", "check", "scan", "score"]
