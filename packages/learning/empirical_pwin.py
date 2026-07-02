"""F4-2 — ampirik p(win) tablosu: TF+rejim hit-rate → EV/Kelly girdisi.

Denetim bulgusu 3.3: EV kapısı ve Kelly sizing p(win) olarak skor-türevi
kalibre güveni kullanıyor; oysa sistemin (timeframe, rejim) hücresi bazında
GERÇEKLEŞMİŞ isabet oranı birikiyor. Bu modül o tabloyu üretir/okur:

- Learning worker her cycle'da verified outcome'lardan tabloyu
  `data/runtime/empirical_pwin.json`'a yazar (`write_table`).
- Karar motoru `lookup(timeframe, regime)` ile okur (mtime-cache — 30sn
  tick'e dosya IO yükü binmez).
- Flag `empirical_pwin.enabled` DEFAULT OFF: kapalıyken EV/Kelly eskisi gibi
  kalibre güvenle hesaplanır (bayt-aynı); ampirik değerler TradeDecision'da
  SALT-GÖZLEM (`p_win_empirical` / `expected_value_empirical`).

Kurallar (DATA_POLICY/F1-2): yalnız verified outcome; başabaş (pnl==0)
paydaya girmez; hücre `min_samples` altındaysa lookup DÖNDÜRMEZ (sahte p
yok); hiyerarşi tf|rejim → tf (rejim hücresi yetersizse TF geneli).
PAPER_SAFE — yalnız gözlem/istatistik; RiskGate'i bypass etmez.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import REPO_ROOT, load_thresholds

DEFAULT_PATH = "data/runtime/empirical_pwin.json"
DEFAULT_MIN_SAMPLES = 20

_LOCK = threading.Lock()
# mtime-cache: (path, mtime) → parsed payload. Tek girdilik cache yeter.
_CACHE: dict[str, tuple[float, dict]] = {}


def _path() -> Path:
    p = Path(os.environ.get("EMPIRICAL_PWIN_PATH", DEFAULT_PATH))
    return p if p.is_absolute() else REPO_ROOT / p


def cfg() -> dict:
    """`empirical_pwin` config'i (enabled default False, min_samples default 20)."""
    try:
        raw = load_thresholds().get("empirical_pwin") or {}
        return {
            "enabled": bool(raw.get("enabled", False)),
            "min_samples": max(1, int(raw.get("min_samples", DEFAULT_MIN_SAMPLES))),
        }
    except (OSError, KeyError, ValueError, TypeError):
        return {"enabled": False, "min_samples": DEFAULT_MIN_SAMPLES}


def enabled() -> bool:
    return cfg()["enabled"]


@dataclass
class EmpiricalPwin:
    p_win: float
    wins: int
    losses: int
    n: int          # wins + losses (başabaş hariç — F1-2 standardı)
    source: str     # "tf_regime" | "tf"


def _cell_key(timeframe: str, regime: str) -> str:
    return f"{timeframe}|{regime}"


def build_table(outcomes) -> dict:
    """Verified outcome'lardan (tf|rejim) + tf hücre tablosu (pure)."""
    cells: dict[str, dict] = {}
    by_tf: dict[str, dict] = {}

    def _bump(bucket: dict, key: str, won: bool) -> None:
        c = bucket.setdefault(key, {"wins": 0, "losses": 0})
        c["wins" if won else "losses"] += 1

    for o in outcomes:
        if not o.data_verified:
            continue
        if o.pnl == 0:
            continue  # başabaş: ne kazanç ne kayıp (F1-2) — paydaya girmez
        won = o.pnl > 0
        tf = str(o.timeframe or "1d")
        regime = str(o.regime or "UNKNOWN")
        _bump(cells, _cell_key(tf, regime), won)
        _bump(by_tf, tf, won)

    def _finalize(bucket: dict) -> dict:
        out = {}
        for key, c in sorted(bucket.items()):
            n = c["wins"] + c["losses"]
            out[key] = {
                "wins": c["wins"],
                "losses": c["losses"],
                "n": n,
                "p_win": round(c["wins"] / n, 4) if n else 0.0,
            }
        return out

    fin_cells = _finalize(cells)
    fin_tf = _finalize(by_tf)
    min_samples = cfg()["min_samples"]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "min_samples": min_samples,
        "cells": fin_cells,
        "by_tf": fin_tf,
        "cell_count": len(fin_cells),
        "sufficient_count": sum(
            1 for c in fin_cells.values() if c["n"] >= min_samples
        ),
    }


def write_table(state=None) -> dict:
    """Tabloyu üret + atomik yaz (learning worker her cycle çağırır)."""
    from packages.learning import outcomes as outcomes_mod

    payload = build_table(outcomes_mod.outcomes_from_state(state))
    p = _path()
    with _LOCK:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f"{p.name}.tmp-{os.getpid()}")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, p)
        _CACHE.pop(str(p), None)
    return payload


def _load_cached() -> dict:
    """Artifact'ı mtime-cache ile oku; yok/bozuk → boş dict (crash yok)."""
    p = _path()
    key = str(p)
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return {}
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and hit[0] == mtime:
            return hit[1]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    with _LOCK:
        _CACHE[key] = (mtime, data)
    return data


def lookup(timeframe: str, regime: str) -> EmpiricalPwin | None:
    """(tf|rejim) hücresi; yetersizse tf geneli; o da yetersizse None.

    None = "ampirik kanıt yok" — çağıran kalibre güvene düşer (sahte p yok)."""
    data = _load_cached()
    if not data:
        return None
    min_samples = cfg()["min_samples"]
    for source, bucket, key in (
        ("tf_regime", data.get("cells") or {}, _cell_key(timeframe, regime)),
        ("tf", data.get("by_tf") or {}, timeframe),
    ):
        c = bucket.get(key)
        if not isinstance(c, dict):
            continue
        try:
            n = int(c.get("n", 0))
            if n < min_samples:
                continue
            return EmpiricalPwin(
                p_win=float(c["p_win"]),
                wins=int(c.get("wins", 0)),
                losses=int(c.get("losses", 0)),
                n=n,
                source=source,
            )
        except (TypeError, ValueError, KeyError):
            continue
    return None


__all__ = ["EmpiricalPwin", "build_table", "cfg", "enabled", "lookup", "write_table"]
