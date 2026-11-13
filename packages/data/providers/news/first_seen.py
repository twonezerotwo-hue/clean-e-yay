"""Haber başlığının sistemce İLK GÖRÜLDÜĞÜ an — gecikme ölçümü için ekleme-yalnız kayıt.

Salt gözlem: karara, oya, kapıya dokunmaz. RSS akışı her ayrıştırıldığında yeni başlık kimlikleri
`data/runtime/news_first_seen.jsonl`'a bir kez yazılır (yeniden başlatmada dosyadaki kimlikler
okunur, kopya yazılmaz). Bir akışın bu süreçteki İLK ayrıştırmasında görülen başlıklar ``boot``
işaretlidir: ne zaman geldikleri bilinmez, ölçümde sayılmaz.

Neden: 13 Kasım 2026 ölçümünde gecikme yalnız 15 dakikalık toplu kayıttan (news_event_ledger) okunabildi;
gerçek ilk görülme anı hiçbir yerde yoktu.
"""
from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from packages.ops.store import write_text_atomic

MAX_BYTES = 30 * 1024 * 1024
KEEP_DAYS = 30

_LOCK = threading.Lock()
_KNOWN: set[str] | None = None
_PARSED_FEEDS: set[str] = set()


def _path() -> Path:
    return Path(os.environ.get("NEWS_FIRST_SEEN_PATH", "data/runtime/news_first_seen.jsonl"))


def _load_known(path: Path) -> set[str]:
    known: set[str] = set()
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    hid = json.loads(line).get("id")
                except ValueError:
                    continue
                if hid:
                    known.add(str(hid))
    except OSError:
        pass
    return known


def _compact(path: Path, now: datetime) -> None:
    cutoff = (now - timedelta(days=KEEP_DAYS)).isoformat()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    kept = [ln for ln in lines if '"first_seen": "' in ln and ln.split('"first_seen": "', 1)[1][:32] >= cutoff]
    if len(kept) > len(lines) // 2:
        kept = kept[len(kept) // 2:]
    write_text_atomic(path, "\n".join(kept) + ("\n" if kept else ""))


def record(feed_url: str, headlines: Iterable[Any], *, group: str, now: datetime | None = None) -> int:
    """Akıştan ayrıştırılan başlıkların yenilerini yazar; yazılan satır sayısını döner. Asla hata fırlatmaz."""
    try:
        from packages.data.providers.news.provenance import (
            is_proxy_source,
            source_family,
            story_key,
        )

        now = now or datetime.now(UTC)
        path = _path()
        with _LOCK:
            global _KNOWN
            if _KNOWN is None:
                _KNOWN = _load_known(path)
            boot = feed_url not in _PARSED_FEEDS
            _PARSED_FEEDS.add(feed_url)
            rows = []
            for h in headlines:
                hid = str(getattr(h, "id", "") or "")
                if not hid or hid in _KNOWN:
                    continue
                _KNOWN.add(hid)
                ts = getattr(h, "ts", None)
                source = getattr(h, "source", None)
                title = str(getattr(h, "title", "") or "")
                rows.append(json.dumps({
                    "id": hid,
                    "source": source,
                    "family": source_family(source, title=title, url=getattr(h, "url", None)),
                    "proxy": is_proxy_source(source),
                    "group": group,
                    "region": getattr(h, "region", None),
                    "story": story_key(title),
                    "title": title[:200],
                    "ts": ts.isoformat() if hasattr(ts, "isoformat") else None,
                    "first_seen": now.isoformat(),
                    "boot": boot,
                }, ensure_ascii=False))
            if not rows:
                return 0
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(rows) + "\n")
            if path.stat().st_size > MAX_BYTES:
                _compact(path, now)
            return len(rows)
    except Exception:  # gözlem kaydı haber akışını asla düşürmez
        return 0


def reset() -> None:
    """Süreç içi durumu sıfırla (testler)."""
    global _KNOWN
    with _LOCK:
        _KNOWN = None
        _PARSED_FEEDS.clear()


__all__ = ["record", "reset"]
