"""Bölge onay defteri — owner'ın kabul/ret hafızası (varsayılan: ONAYLI).

Owner kararı (2026-07-12): önerici bölgeleri owner İPTAL EDENE KADAR onaylı
sayılır. İptal edilen bölge canlı giriş/çıkış yerleşimine (zone_influence)
GİRMEZ; owner tekrar onaylayabilir. Her karar tarihçeye yazılır — bu tarihçe
kalibrasyonun ham verisidir (hangi kesişim türlerine güveniyor / güvenmiyor).

Bölge kimliği kırılgan olmasın diye eşleşme BANT ÖRTÜŞMESİYLE yapılır (id
değil): önerici her gün bölgeyi milim farkla yeniden üretse de owner'ın iptali
örtüşen banda uygulanır; zaman damgası en yeni karar kazanır.

Dosya: data/runtime/zone_verdicts.json (env ZONE_VERDICTS_PATH). Asla raise
etmez; okunamayan defter = boş defter (varsayılan onaylı davranış sürer).
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

ACTIONS = ("iptal", "onay")
# Bant örtüşme toleransı (oransal): kenarlar bu kadar yakınsa aynı bölge sayılır.
_TOL = 0.005


def _path() -> Path:
    return Path(os.environ.get("ZONE_VERDICTS_PATH", "data/runtime/zone_verdicts.json"))


def _load() -> list[dict]:
    try:
        p = _path()
        if not p.exists():
            return []
        raw = json.loads(p.read_text(encoding="utf-8"))
        return list(raw) if isinstance(raw, list) else []
    except (OSError, json.JSONDecodeError, ValueError):
        return []


def _save(records: list[dict]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def _overlaps(a_low: float, a_high: float, b_low: float, b_high: float) -> bool:
    pad_a = a_high * _TOL
    pad_b = b_high * _TOL
    return not (a_high + pad_a < b_low or b_high + pad_b < a_low)


def record(symbol: str, low: float, high: float, action: str, note: str = "") -> dict:
    """Owner kararını deftere yaz. Geçersiz girdi ValueError."""
    action = str(action).strip().lower()
    if action not in ACTIONS:
        raise ValueError(f"action {ACTIONS} içinden olmalı, geldi: {action!r}")
    low, high = sorted((float(low), float(high)))
    if low <= 0:
        raise ValueError("bölge kenarları pozitif olmalı")
    rec = {
        "symbol": str(symbol).upper(),
        "low": round(low, 6),
        "high": round(high, 6),
        "action": action,
        "note": str(note or ""),
        "ts": datetime.now(UTC).isoformat(),
    }
    records = _load()
    records.append(rec)
    _save(records)
    return rec


def verdict_for(symbol: str, low: float, high: float) -> str:
    """Bölgenin efektif durumu: 'onayli' (varsayılan) | 'iptal'.

    Örtüşen kararlardan zaman damgası EN YENİ olan kazanır."""
    sym = str(symbol).upper()
    latest: dict | None = None
    for r in _load():
        try:
            if r.get("symbol") != sym:
                continue
            if not _overlaps(float(r["low"]), float(r["high"]), float(low), float(high)):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        if latest is None or str(r.get("ts", "")) > str(latest.get("ts", "")):
            latest = r
    if latest is None:
        return "onayli"  # owner kararı: iptal edilmedikçe onaylı
    return "iptal" if latest.get("action") == "iptal" else "onayli"


def history(symbol: str | None = None) -> list[dict]:
    """Karar tarihçesi (kalibrasyon verisi). En yeni sonda."""
    recs = _load()
    if symbol is not None:
        sym = str(symbol).upper()
        recs = [r for r in recs if r.get("symbol") == sym]
    return sorted(recs, key=lambda r: str(r.get("ts", "")))


__all__ = ["ACTIONS", "history", "record", "verdict_for"]
