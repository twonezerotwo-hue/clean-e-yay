"""Calibration jump ledger — observe-only.

"Hangi sinyali aldı da bu kadar büyüttü?" sorusunun veri tabanı. Her paper
açılışında, Platt kalibrasyonunun ham consensus güvenini ne kadar şişirdiğini
(raw → fitted) ve bunu sürükleyen faktörleri (score, dominant modül, regime,
confluence, sonuç kademe + boyut, Platt a/b) JSONL'e yazar.

Kurallar:
- SADECE KAYIT — hiçbir karar/sizing davranışını DEĞİŞTİRMEZ (gözlem katmanı).
  Otomatik kısma calibration_store.apply_inflation_guardrail (owner-flag) işidir.
- I/O hatası asla tick'i düşürmez (best-effort append, exception yutulur).
- Outcome ile sonradan join edilebilsin diye position_id + fingerprint taşır.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from packages.data.registry.loader import REPO_ROOT
from packages.learning import calibration_store

_DEFAULT_KEEP = 500  # ledger'da tutulan son N satır (sınırsız büyümeyi önler)


def _path() -> Path:
    p = Path(os.environ.get("CALIBRATION_AUDIT_PATH", "data/runtime/calibration_jumps.jsonl"))
    return p if p.is_absolute() else REPO_ROOT / p


def _coerce_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return round(float(value), 4)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def build_row(decision: object, position: object, *, regime: str | None = None) -> dict:
    """TradeDecision + açılan Position'dan ledger satırı kurar (saf, yan etkisiz)."""
    cons = getattr(decision, "consensus", None)
    raw = _coerce_float(getattr(decision, "raw_confidence", None))
    fitted = _coerce_float(getattr(position, "predicted_confidence", None))
    if fitted is None:
        fitted = _coerce_float(getattr(decision, "confidence", None))
    delta = (
        calibration_store.inflation_delta(raw, fitted)
        if raw is not None and fitted is not None
        else None
    )
    params = calibration_store.load()
    return {
        "ts": _now_iso(),
        "position_id": getattr(position, "id", None),
        "symbol": getattr(position, "symbol", None) or getattr(decision, "symbol", None),
        "timeframe": getattr(position, "timeframe", None) or getattr(decision, "timeframe", None),
        "side": getattr(position, "side", None),
        "raw_confidence": raw,
        "fitted_confidence": fitted,
        "inflation_delta": delta,
        "confidence_source": getattr(decision, "confidence_source", None),
        "platt_a": _coerce_float(params.a),
        "platt_b": _coerce_float(params.b),
        "platt_status": params.status,
        "platt_samples": params.samples,
        "score": _coerce_float(getattr(cons, "score", None)),
        "dominant_module": getattr(cons, "dominant_module", None),
        "direction": getattr(cons, "direction", None),
        "confluence_aligned": getattr(cons, "confluence_aligned", None),
        "regime": regime,
        "tier": getattr(position, "tier", None),
        "size_usd": _coerce_float(getattr(position, "size_usd", None)),
        "fingerprint": getattr(decision, "fingerprint", None),
    }


def record_open(decision: object, position: object, *, regime: str | None = None) -> dict | None:
    """Açılan pozisyon için kalibrasyon sıçraması satırını ledger'a ekler.

    Best-effort: herhangi bir hata yutulur (tick devam eder). Yazılan satırı döner
    (test/inspeksiyon için), yazamazsa None.
    """
    try:
        row = build_row(decision, position, regime=regime)
        _append(row)
        return row
    except Exception:  # noqa: BLE001 — gözlem katmanı asla tick'i düşürmez
        return None


def _append(row: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    _trim(path)


def _trim(path: Path, keep: int = _DEFAULT_KEEP) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > keep:
            path.write_text("\n".join(lines[-keep:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def read_recent(limit: int = 50) -> list[dict]:
    """Son N ledger satırı (en yeni önce)."""
    path = _path()
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    rows.reverse()
    return rows[: max(0, int(limit))]


def summary_viewmodel(limit: int = 200) -> dict:
    """Son `limit` satırdan özet: sıçrama dağılımı + en büyük şişmeler + kademe.

    Frontend hesap yapmaz; bu özet backend'de türetilir (single source).
    """
    rows = read_recent(limit)
    deltas = [r.get("inflation_delta") for r in rows if isinstance(r.get("inflation_delta"), (int, float))]
    fitted_count = sum(1 for r in rows if r.get("confidence_source") == "fitted")
    capped_count = sum(1 for r in rows if r.get("confidence_source") == "fitted_capped")
    by_tier: dict[str, int] = {}
    by_dominant: dict[str, int] = {}
    for r in rows:
        tier = str(r.get("tier") or "?")
        by_tier[tier] = by_tier.get(tier, 0) + 1
        dom = str(r.get("dominant_module") or "?")
        by_dominant[dom] = by_dominant.get(dom, 0) + 1
    top_jumps = sorted(
        (r for r in rows if isinstance(r.get("inflation_delta"), (int, float))),
        key=lambda r: r.get("inflation_delta") or 0.0,
        reverse=True,
    )[:5]
    return {
        "count": len(rows),
        "fitted_count": fitted_count,
        "capped_count": capped_count,
        "avg_inflation_delta": round(sum(deltas) / len(deltas), 4) if deltas else None,
        "max_inflation_delta": round(max(deltas), 4) if deltas else None,
        "by_tier": by_tier,
        "by_dominant_module": by_dominant,
        "top_jumps": top_jumps,
        "recent": rows[:20],
    }


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
