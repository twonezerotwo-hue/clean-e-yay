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
    """`empirical_pwin` config'i (enabled default False, min_samples default 20).

    F5-1 — blend_counterfactual (default False): AÇIKKEN gerçek outcome'u
    yetersiz TF'lerde missed-opportunity counterfactual sayımları SON ÇARE
    fallback olarak harmanlanır (gerçek kanıt her zaman önceliklidir)."""
    try:
        raw = load_thresholds().get("empirical_pwin") or {}
        return {
            "enabled": bool(raw.get("enabled", False)),
            "min_samples": max(1, int(raw.get("min_samples", DEFAULT_MIN_SAMPLES))),
            "blend_counterfactual": bool(raw.get("blend_counterfactual", False)),
        }
    except (OSError, KeyError, ValueError, TypeError):
        return {
            "enabled": False,
            "min_samples": DEFAULT_MIN_SAMPLES,
            "blend_counterfactual": False,
        }


def enabled() -> bool:
    return cfg()["enabled"]


@dataclass
class EmpiricalPwin:
    p_win: float
    wins: int
    losses: int
    n: int          # wins + losses (başabaş hariç — F1-2 standardı)
    source: str     # "tf_regime" | "tf" | "tf_blend_cf"
    # F5-3 — ödül-ağırlıklı EV girdisi: GERÇEKLEŞEN ortalama kazanç-R ve kayıp-R
    # (r_multiple = getiri% / açılış risk mesafesi). Sabit hedef-RR yerine bunlar
    # kullanılınca "adet kazanıyor ama trailing/time-stop erken çıkıyor → kazanç
    # hedeften küçük" gerçeği EV'ye girer. r_multiple taşımayan (legacy/SL'siz)
    # outcome'lar R istatistiğine girmez; hiç R yoksa None (uydurma yok).
    avg_win_r: float | None = None   # kazananların ortalama +R (pozitif büyüklük)
    avg_loss_r: float | None = None  # kaybedenlerin ortalama R (pozitif büyüklük)
    win_r_n: int = 0
    loss_r_n: int = 0


def _cell_key(timeframe: str, regime: str) -> str:
    return f"{timeframe}|{regime}"


def build_table(outcomes, counterfactuals: list[dict] | None = None) -> dict:
    """Verified outcome'lardan (tf|rejim) + tf hücre tablosu (pure).

    F5-1 — `counterfactuals` (missed_opportunity çözümleri) AYRI kanala
    yazılır (`cf_by_tf`): win=missed_win, loss=avoided_loss, expired paydaya
    girmez. Gerçek ölçüm hücreleri counterfactual ile KİRLETİLMEZ — harman
    yalnız lookup'ta, flag'le ve son-çare fallback olarak yapılır."""
    cells: dict[str, dict] = {}
    by_tf: dict[str, dict] = {}
    cf_by_tf: dict[str, dict] = {}

    def _bump(bucket: dict, key: str, won: bool, r_mult: float | None = None) -> None:
        c = bucket.setdefault(
            key,
            {"wins": 0, "losses": 0, "win_r_sum": 0.0, "win_r_n": 0,
             "loss_r_sum": 0.0, "loss_r_n": 0},
        )
        c["wins" if won else "losses"] += 1
        # F5-3 — gerçekleşen R'yi ayrık topla (kazanç magnitüdü +, kayıp magnitüdü |·|).
        if r_mult is not None:
            if won:
                c["win_r_sum"] += float(r_mult)
                c["win_r_n"] += 1
            else:
                c["loss_r_sum"] += abs(float(r_mult))
                c["loss_r_n"] += 1

    for o in outcomes:
        if not o.data_verified:
            continue
        if o.pnl == 0:
            continue  # başabaş: ne kazanç ne kayıp (F1-2) — paydaya girmez
        won = o.pnl > 0
        tf = str(o.timeframe or "1d")
        regime = str(o.regime or "UNKNOWN")
        r_mult = getattr(o, "r_multiple", None)  # legacy/mock-güvenli
        _bump(cells, _cell_key(tf, regime), won, r_mult)
        _bump(by_tf, tf, won, r_mult)

    for r in counterfactuals or []:
        oc = r.get("outcome")
        if oc not in ("missed_win", "avoided_loss"):
            continue  # expired: net sonuç yok
        # Counterfactual'ların gerçekleşen R'si yok (paper açılmadı) → R istatistiği
        # yalnız gerçek outcome'lardan; cf sadece p_win harmanına girer.
        _bump(cf_by_tf, str(r.get("timeframe") or "1d"), oc == "missed_win")

    def _finalize(bucket: dict) -> dict:
        out = {}
        for key, c in sorted(bucket.items()):
            n = c["wins"] + c["losses"]
            win_r_n = c.get("win_r_n", 0)
            loss_r_n = c.get("loss_r_n", 0)
            out[key] = {
                "wins": c["wins"],
                "losses": c["losses"],
                "n": n,
                "p_win": round(c["wins"] / n, 4) if n else 0.0,
                # F5-3 — ayrık gerçekleşen R (yoksa None; uydurma yok)
                "avg_win_r": round(c["win_r_sum"] / win_r_n, 4) if win_r_n else None,
                "avg_loss_r": round(c["loss_r_sum"] / loss_r_n, 4) if loss_r_n else None,
                "win_r_n": win_r_n,
                "loss_r_n": loss_r_n,
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
        # F5-1 — counterfactual kanalı (ayrı; gerçek hücreleri kirletmez)
        "cf_by_tf": _finalize(cf_by_tf),
        "cell_count": len(fin_cells),
        "sufficient_count": sum(
            1 for c in fin_cells.values() if c["n"] >= min_samples
        ),
    }


def write_table(state=None) -> dict:
    """Tabloyu üret + atomik yaz (learning worker her cycle çağırır)."""
    from packages.learning import missed_opportunity
    from packages.learning import outcomes as outcomes_mod

    try:
        cf = missed_opportunity.resolutions()
    except Exception:
        cf = []  # counterfactual kanalı best-effort — tabloyu düşürmez
    payload = build_table(outcomes_mod.outcomes_from_state(state), counterfactuals=cf)
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

    F5-1 — `blend_counterfactual` AÇIKSA son çare: gerçek tf sayımları +
    counterfactual tf sayımları HARMANLANIR (kaynak "tf_blend_cf"). Gerekçe:
    bir TF bloklanınca gerçek outcome ÜRETMEZ (geri-besleme kör noktası);
    counterfactual'lar o TF'i ölçmeye devam eder. Gerçek kanıt yeterliyse
    harman HİÇ devreye girmez. None = kanıt yok — çağıran kalibre güvene
    düşer (sahte p yok)."""
    data = _load_cached()
    if not data:
        return None
    c = cfg()
    min_samples = c["min_samples"]
    for source, bucket, key in (
        ("tf_regime", data.get("cells") or {}, _cell_key(timeframe, regime)),
        ("tf", data.get("by_tf") or {}, timeframe),
    ):
        cell = bucket.get(key)
        if not isinstance(cell, dict):
            continue
        try:
            n = int(cell.get("n", 0))
            if n < min_samples:
                continue
            awr = cell.get("avg_win_r")
            alr = cell.get("avg_loss_r")
            return EmpiricalPwin(
                p_win=float(cell["p_win"]),
                wins=int(cell.get("wins", 0)),
                losses=int(cell.get("losses", 0)),
                n=n,
                source=source,
                avg_win_r=float(awr) if awr is not None else None,
                avg_loss_r=float(alr) if alr is not None else None,
                win_r_n=int(cell.get("win_r_n", 0)),
                loss_r_n=int(cell.get("loss_r_n", 0)),
            )
        except (TypeError, ValueError, KeyError):
            continue
    if not c["blend_counterfactual"]:
        return None
    # Son çare harman: gerçek(tf) + counterfactual(tf) sayımları.
    try:
        actual = (data.get("by_tf") or {}).get(timeframe) or {}
        cf = (data.get("cf_by_tf") or {}).get(timeframe) or {}
        wins = int(actual.get("wins", 0)) + int(cf.get("wins", 0))
        losses = int(actual.get("losses", 0)) + int(cf.get("losses", 0))
        n = wins + losses
        if n < min_samples:
            return None
        return EmpiricalPwin(
            p_win=round(wins / n, 4), wins=wins, losses=losses, n=n,
            source="tf_blend_cf",
        )
    except (TypeError, ValueError):
        return None


__all__ = ["EmpiricalPwin", "build_table", "cfg", "enabled", "lookup", "write_table"]
