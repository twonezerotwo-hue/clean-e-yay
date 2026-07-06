"""Bar arşivi — kanıt-büyütme katmanı (İZOLE, salt-veri; karar yok).

Neden: provider'lar TF başına sınırlı pencere döner (`_MAX_BARS`, örn. 15m'de
400 bar ≈ 4 gün) ve eski barlar ATILIR. Sinyal karnesi (subsignal_scorecard v2)
bu yüzden 15m/1h'de "INSUFFICIENT" kalıyor — kanıt fiziken büyüyemiyor. Bu
katman her taze çekilen KAPANMIŞ barı kalıcı JSONL arşivine ekler; karne,
arşiv + canlı barları birleştirip her hafta kendiliğinden daha uzun pencereyle
ölçer (10/10 kanıt hedefinin veri bacağı).

Sözleşme:
- Flag `BAR_HISTORY_ENABLED` (env, DEFAULT OFF). OFF → append VE load no-op;
  sistem bayt-aynı davranır (testler/baseline bozulmaz).
- ASLA raise etmez; arşiv hatası veri akışını/karneyi durduramaz.
- Yalnız KAPANMIŞ barlar arşivlenir (son bar oluşum hâlinde olabilir → hariç).
- Fixture barlar arşive GİREMEZ (çağıran `is_fixture_mode` bekçisiyle sarar).
- Çok-süreç dublikasyonu okumada çözülür: `load()` ts-bazlı tekilleştirir.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path

from packages.data.types import OHLCVBar

FLAG = "BAR_HISTORY_ENABLED"
_ENV_TRUE = frozenset({"1", "true", "yes", "on"})
# Test izolasyonu / esneklik: dizin env ile taşınabilir.
_DIR_ENV = "BAR_HISTORY_DIR"
_DEFAULT_DIR = "data/runtime/bar_history"

_LOCK = threading.Lock()
# (symbol, tf) -> arşivdeki en yeni bar ts'i (süreç içi hızlı yol)
_LAST_TS: dict[tuple[str, str], datetime | None] = {}


def enabled() -> bool:
    return os.environ.get(FLAG, "").strip().lower() in _ENV_TRUE


def _dir() -> Path:
    return Path(os.environ.get(_DIR_ENV, _DEFAULT_DIR))


def _path(symbol: str, timeframe: str) -> Path:
    safe = "".join(ch for ch in symbol if ch.isalnum() or ch in "-_") or "UNKNOWN"
    return _dir() / f"{safe}_{timeframe}.jsonl"


def _tail_ts(path: Path) -> datetime | None:
    """Dosyadaki son geçerli barın ts'i. Tek seferlik; sonrası _LAST_TS."""
    try:
        if not path.exists():
            return None
        last = ""
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last = line
        if not last:
            return None
        return OHLCVBar.model_validate(json.loads(last)).ts
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def append_new(symbol: str, timeframe: str, bars: list[OHLCVBar]) -> int:
    """Arşivden yeni olan KAPANMIŞ barları ekle; eklenen sayısını döndür.
    Flag OFF veya veri yok → 0 (no-op). Asla raise etmez."""
    if not enabled() or len(bars) < 2:
        return 0
    closed = bars[:-1]  # son bar hâlâ oluşuyor olabilir → arşive girmez
    key = (symbol, timeframe)
    try:
        with _LOCK:
            path = _path(symbol, timeframe)
            last = _LAST_TS.get(key)
            if last is None:
                last = _tail_ts(path)
            fresh = [b for b in closed if last is None or b.ts > last]
            if not fresh:
                _LAST_TS[key] = last
                return 0
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                for b in fresh:
                    fh.write(json.dumps(b.model_dump(mode="json")) + "\n")
            _LAST_TS[key] = fresh[-1].ts
            return len(fresh)
    except (OSError, ValueError, TypeError):
        return 0


def load(symbol: str, timeframe: str) -> list[OHLCVBar]:
    """Arşivlenmiş barlar (ts-tekil, sıralı). Flag OFF → [] (bayt-aynı baseline).
    Bozuk satır atlanır; asla raise etmez."""
    if not enabled():
        return []
    out: dict[datetime, OHLCVBar] = {}
    try:
        path = _path(symbol, timeframe)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    bar = OHLCVBar.model_validate(json.loads(line))
                    out[bar.ts] = bar
                except (json.JSONDecodeError, ValueError):
                    continue
    except OSError:
        return []
    return [out[k] for k in sorted(out)]


def merged(archive: list[OHLCVBar], live: list[OHLCVBar]) -> list[OHLCVBar]:
    """Arşiv + canlı barları ts-bazlı birleştir (canlı kazanır — en taze OHLC).
    Arşiv boşken canlıyı AYNEN döndürür (karne v2 davranışı değişmez)."""
    if not archive:
        return live
    by_ts = {b.ts: b for b in archive}
    by_ts.update({b.ts: b for b in live})
    return [by_ts[k] for k in sorted(by_ts)]


__all__ = ["FLAG", "append_new", "enabled", "load", "merged"]
