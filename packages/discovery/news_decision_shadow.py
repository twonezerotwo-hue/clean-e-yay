"""Haber öngörüsü → karar matrisi GÖLGE girdisi (owner kararı 2026-10-05, üçüncü tur).

Canlı karar motorunun (decide_matrix) aday işlemleri ile haber öngörüsü (YZ haber zinciri
dahil; `news_forecast`) karşılaştırılır: öngörü adayı TEYİT mi ediyor, ÇELİŞİYOR mu?
Her ilişki fiyatıyla deftere yazılır ve 4 sa / 1 g sonra çözülür: adayın yönü tuttu mu?
Karne "haber çelişen adaylar ile teyit edilenler ne kadar tutuyor" sorusunu cevaplar —
haber girdisinin karara bağlanması (CP5) için kanıt budur.

ETKİSİZ (gölge): hiçbir karar, boyut, RiskGate ya da paper durumu değişmez;
`affect_decision` her zaman false raporlanır. Bağlanması ayrı iş ve owner onayı ister.
Canlı matriste haber modülü zaten `analytics_only` (karara girmiyor).
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from packages.ops.store import write_text_atomic

ENTRY_SIDE = {"open_long": "long", "open_short": "short"}
_MAX_ROWS = 5000


def _path() -> Path:
    return Path(os.environ.get("NEWS_DECISION_SHADOW_PATH", "data/runtime/news_decision_shadow.jsonl"))


def _iso(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat()


def _parse(ts: Any) -> datetime | None:
    try:
        out = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return out if out.tzinfo else out.replace(tzinfo=UTC)


def config(discovery_cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if discovery_cfg is None:
        from packages.discovery.scanner import load_config

        discovery_cfg = load_config()
    raw = dict(discovery_cfg.get("news_decision_shadow") or {})
    return {
        "enabled": bool(raw.get("enabled", True)),
        "min_strength": int(raw.get("min_strength", 20)),
        "horizons_hours": [int(h) for h in raw.get("horizons_hours", [4, 24])],
        "dedupe_hours": float(raw.get("dedupe_hours", 4)),
        "flat_pct": float(raw.get("flat_pct", 0.1)),
        "affect_decision": False,  # gölge: owner onayı olmadan karara bağlanmaz (CP5)
    }


def relation(side: str, direction: str) -> str:
    return "confirm" if (side == "long") == (direction == "up") else "conflict"


def checks(cells: Iterable[Mapping[str, Any]], forecasts: Mapping[str, Mapping[str, Any]],
           min_strength: int = 20) -> list[dict]:
    """Canlı aday işlemler × haber öngörüsü: teyit / çelişki (çelişkiler ve güçlüler önce)."""
    out = []
    for c in cells:
        side = ENTRY_SIDE.get(str(c.get("candidate_action") or ""))
        f = forecasts.get(str(c.get("symbol") or "")) or {}
        if side is None or f.get("direction") not in ("up", "down") or int(f.get("strength") or 0) < min_strength:
            continue
        ev = (f.get("evidence") or [{}])[0]
        out.append({
            "symbol": c["symbol"], "timeframe": c.get("timeframe"), "side": side,
            "final_action": c.get("action"), "live_score": c.get("score"),
            "forecast": f["direction"], "strength": int(f["strength"]),
            "relation": relation(side, f["direction"]), "evidence": ev.get("title"),
        })
    out.sort(key=lambda r: (r["relation"] != "conflict", -r["strength"], r["symbol"], str(r["timeframe"])))
    return out


def _read() -> list[dict]:
    try:
        lines = _path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue  # bozuk satır atlanır
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _write(rows: list[dict]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows[-_MAX_ROWS:]))


def _prices(snapshot_doc: Mapping[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for q in (snapshot_doc.get("data_snapshot") or {}).get("prices") or []:
        try:
            if q.get("price"):
                out[str(q["symbol"])] = float(q["price"])
        except (TypeError, ValueError):
            continue
    return out


def run(now: datetime | None = None, *, forecasts: Mapping[str, Mapping[str, Any]] | None = None,
        snapshot_doc: Mapping[str, Any] | None = None, discovery_cfg: Mapping[str, Any] | None = None) -> dict:
    """Learning worker adımı: eski satırları çöz, son snapshot'ın adaylarını damgala."""
    now = now or datetime.now(UTC)
    cfg = config(discovery_cfg)
    if not cfg["enabled"]:
        return {"status": "DISABLED"}
    if forecasts is None:
        from packages.discovery import news_forecast

        forecasts = news_forecast.load_forecasts()
    if snapshot_doc is None:
        from packages.data import snapshot_store

        docs = snapshot_store.recent(1)
        snapshot_doc = docs[0] if docs else {}
    prices = _prices(snapshot_doc)
    rows = _read()

    resolved = 0
    for r in rows:
        ts = _parse(r.get("ts"))
        price = prices.get(str(r.get("symbol")))
        if ts is None or not price or not r.get("price"):
            continue
        for h in cfg["horizons_hours"]:
            key = f"{h}h"
            if key in r.setdefault("resolved", {}) or now - ts < timedelta(hours=h):
                continue
            ret = (price / float(r["price"]) - 1.0) * 100.0
            outcome = ("flat" if abs(ret) < cfg["flat_pct"]
                       else "hit" if (ret > 0) == (r.get("side") == "long") else "miss")
            r["resolved"][key] = {"ret_pct": round(ret, 3), "outcome": outcome, "at": _iso(now)}
            resolved += 1

    created = 0
    cells = (snapshot_doc.get("decision_matrix") or {}).get("cells") or []
    window = timedelta(hours=cfg["dedupe_hours"])
    recent = {(r.get("symbol"), r.get("timeframe"), r.get("side"), r.get("relation")): _parse(r.get("ts"))
              for r in rows if _parse(r.get("ts")) and now - _parse(r.get("ts")) < window}
    for chk in checks(cells, forecasts, cfg["min_strength"]):
        key = (chk["symbol"], chk["timeframe"], chk["side"], chk["relation"])
        price = prices.get(chk["symbol"])
        if key in recent or not price:
            continue
        rows.append({**chk, "ts": _iso(now), "price": price, "snapshot_id": snapshot_doc.get("snapshot_id"),
                     "resolved": {}})
        recent[key] = now
        created += 1
    if created or resolved:
        _write(rows)
    return {"status": "OK", "created": created, "resolved": resolved, "rows": len(rows)}


def scorecard(discovery_cfg: Mapping[str, Any] | None = None) -> dict:
    """İlişki × ufuk: canlı aday yönünün isabeti (haber teyit ettiğinde / çeliştiğinde)."""
    cfg = config(discovery_cfg)
    by: dict[str, dict[str, dict]] = {}
    total = 0
    for r in _read():
        for h in cfg["horizons_hours"]:
            res = (r.get("resolved") or {}).get(f"{h}h")
            if not res:
                continue
            cell = by.setdefault(str(r.get("relation")), {}).setdefault(f"{h}h", {"n": 0, "hit": 0, "miss": 0,
                                                                                   "flat": 0})
            cell["n"] += 1
            cell[res["outcome"]] += 1
            total += 1
    for rel in by.values():
        for cell in rel.values():
            decisive = cell["hit"] + cell["miss"]
            cell["hit_rate"] = round(cell["hit"] / decisive, 3) if decisive else None
    return {"resolved_total": total, "by_relation": by, "affect_decision": False,
            "note": "Gölge: karar değişmez. Çelişen adayların isabeti teyit edilenlerden belirgin düşükse "
                    "haber girdisinin karara bağlanması owner onayına sunulur (CP5)."}


def compact(discovery_cfg: Mapping[str, Any] | None = None) -> dict:
    """YZ bağlamı için kısa karne: 1 günlük ufukta çelişki vs teyit isabeti."""
    sc = scorecard(discovery_cfg)
    day = {rel: (v.get("24h") or {}) for rel, v in sc["by_relation"].items()}
    return {"resolved_total": sc["resolved_total"], "affect_decision": False,
            "day": {rel: {"n": c.get("n", 0), "hit_rate": c.get("hit_rate")} for rel, c in day.items()}}


__all__ = ["checks", "compact", "config", "relation", "run", "scorecard"]
