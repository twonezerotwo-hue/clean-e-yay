"""Denetim ve uyum kaydı (hedef mimari st_audit) — kim, ne zaman, neyi istedi.

Her yazma komutu (aç, kapat, SL/TP düzenle, onayla/reddet, fren sıfırla, sıfırla,
bakım; yetkisiz denemeler dahil) API ara katmanından, öğrenmenin owner'sız yaptığı
otomatik terfi ve geri almalar (aktör "auto") kendi yerlerinden tek bir eklemeli
kayda düşer. Süreçler arası yazım defterle aynı OS dosya kilidi altında.
Her satır bir öncekinin özetini taşır (hash zinciri): sonradan değiştirilen ya da
silinen satır `verify` ile görünür. Kayıt yalnız tutulur; hiçbir kararı etkilemez
ve yazılamazsa isteği asla bozmaz.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from packages.paper.state import _flock_acquire, _flock_release

_GENESIS = "0" * 16
# Komut olmayan yazma uçları: sohbet/ses üretimi ve bildirim okundu işaretleri.
_EXCLUDED_PREFIXES = ("/api/v1/chat", "/api/v1/voice/", "/api/v1/notifications/")
DEFAULT_LIMIT = 100


def _path() -> Path:
    return Path(os.environ.get("COMPLIANCE_LOG_PATH", "data/runtime/compliance_log.jsonl"))


def is_command(method: str, path: str) -> bool:
    """Kayda girecek bir komut mu? (yazma metodu ve komut ucu)."""
    return method in {"POST", "PUT", "PATCH", "DELETE"} and not path.startswith(_EXCLUDED_PREFIXES)


def _digest(prev: str, body: dict) -> str:
    raw = prev + json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _last_hash(path: Path) -> str:
    if not path.exists() or path.stat().st_size == 0:
        return _GENESIS
    with path.open("rb") as fh:
        fh.seek(max(0, path.stat().st_size - 4096))
        tail = fh.read().decode("utf-8", errors="ignore").strip().splitlines()
    try:
        return str(json.loads(tail[-1])["hash"])
    except (IndexError, KeyError, ValueError):
        return _GENESIS


def _append(body: dict) -> None:
    """Zincire ekler (kilit altında son özet okunur). Hata çağıranı bozmaz."""
    try:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        lock = open(p.with_name(p.name + ".lock"), "a+b")  # _flock_release kapatır
        _flock_acquire(lock)
        try:
            prev = _last_hash(p)
            line = {**body, "prev": prev, "hash": _digest(prev, body)}
            with p.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        finally:
            _flock_release(lock)
    except OSError:
        return


def record(*, actor: str, method: str, path: str, query: str, status: int) -> None:
    """Bir API komutunu zincire ekler (kayıt yan etkisizdir)."""
    _append({
        "at": datetime.now(UTC).isoformat(),
        "actor": actor,
        "method": method,
        "path": path,
        "query": query,
        "status": int(status),
        "outcome": "denied" if status in (401, 403) else ("ok" if status < 400 else "failed"),
    })


def record_event(*, action: str, detail: dict, actor: str = "auto") -> None:
    """API dışı değişiklik (otomatik terfi/geri alma) — `detail` küçük ve JSON."""
    _append({"at": datetime.now(UTC).isoformat(), "actor": actor, "action": action,
             "detail": detail, "outcome": "ok"})


def _read_all() -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    rows: list[dict] = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    rows.append({"_corrupt": True})
    return rows


def verify(rows: list[dict] | None = None) -> dict:
    """Zinciri baştan doğrular: ilk kırık satırın sırası (yoksa None)."""
    rows = _read_all() if rows is None else rows
    prev = _GENESIS
    for i, row in enumerate(rows):
        body = {k: v for k, v in row.items() if k not in ("prev", "hash")}
        if row.get("_corrupt") or row.get("prev") != prev or row.get("hash") != _digest(prev, body):
            return {"chain_ok": False, "broken_at": i}
        prev = str(row["hash"])
    return {"chain_ok": True, "broken_at": None}


def report(limit: int = DEFAULT_LIMIT) -> dict:
    """Son komutlar (en yeni önce) + zincir doğrulaması + sonuç sayaçları."""
    rows = _read_all()
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("outcome", "?"))
        counts[key] = counts.get(key, 0) + 1
    return {
        "total": len(rows),
        **verify(rows),
        "outcomes": counts,
        "entries": list(reversed(rows[-max(1, int(limit)):])),
    }


__all__ = ["is_command", "record", "record_event", "report", "verify"]
