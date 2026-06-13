"""R1 — disk snapshot store (gerçek replay temeli).

Karar/dashboard snapshot'larını disk'e **atomik** yazar; replay endpoint'leri
buradan okur. Sahte backtest YOK — yalnızca gerçekten kaydedilmiş state inspect
edilir.

PAPER_SAFE / NO_EXECUTION: store hiçbir emir üretmez, hiçbir karar hesaplamaz,
RiskGate'i çağırmaz, live provider'a gitmez. Yalnızca dict yazar/okur.

Kurallar:
- Atomik write (temp dosya + `os.replace`).
- Bozuk dosya → crash yok (okunurken atlanır).
- `latest()` en yeni okunabilir snapshot'ı döner; `get(id)` id ile okur.
- Dosya adı zaman-sıralı (`<ts>__<safe_id>.json`) → latest ucuz, id ile glob.
- Testte `SNAPSHOT_STORE_PATH` env'i temp dir'e ayarlanır; live data gerekmez.

ARCHITECTURE §3'te `packages/data/snapshot_store.py` olarak zaten tanımlıydı;
bu modül o sözleşmeyi dolduruyor (yeni mimari katman değil).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

SCHEMA_VERSION = 1
DEFAULT_DIR = "data/runtime/snapshots"
DEFAULT_MAX_SNAPSHOTS = 500

_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _dir() -> Path:
    return Path(os.environ.get("SNAPSHOT_STORE_PATH", DEFAULT_DIR))


def _max_snapshots() -> int:
    try:
        return max(1, int(os.environ.get("SNAPSHOT_STORE_MAX", DEFAULT_MAX_SNAPSHOTS)))
    except ValueError:
        return DEFAULT_MAX_SNAPSHOTS


def _safe_id(snapshot_id: str) -> str:
    """Path-traversal güvenli dosya parçası ('snap::abc' → 'snap__abc')."""
    return _SAFE.sub("_", snapshot_id or "unknown")[:80]


def _ts_key(generated_at: str) -> str:
    """Leksikografik sıralanabilir zaman anahtarı (bozuk girdiye toleranslı)."""
    return _SAFE.sub("", generated_at or "")[:32] or "00000000"


def _filename(generated_at: str, snapshot_id: str) -> str:
    return f"{_ts_key(generated_at)}__{_safe_id(snapshot_id)}.json"


def _files() -> list[Path]:
    d = _dir()
    if not d.exists():
        return []
    try:
        return sorted(p for p in d.glob("*.json") if p.is_file())
    except OSError:
        return []


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return None  # bozuk/okunamaz → atla (crash yok)
    return data if isinstance(data, dict) else None


def record(payload: dict) -> str | None:
    """Snapshot'ı atomik yazar; snapshot_id döner (başarısızsa None).

    Aynı snapshot_id zaten en güncel kayıtsa tekrar yazmaz (tick tekrarında
    dosya çoğalmasını önler). Store yazımı ASLA çağıranı patlatmaz.
    """
    if not isinstance(payload, dict):
        return None
    sid = str(payload.get("snapshot_id") or "")
    if not sid:
        return None

    last = _latest_path()
    if last is not None:
        existing = _read(last)
        if existing is not None and existing.get("snapshot_id") == sid:
            return sid  # zaten en güncel — duplicate yazma

    body = dict(payload)
    body.setdefault("schema_version", SCHEMA_VERSION)
    gen = str(body.get("generated_at") or "")
    d = _dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        final = d / _filename(gen, sid)
        tmp = final.with_name(f"{final.name}.tmp-{os.getpid()}")
        tmp.write_text(json.dumps(body, ensure_ascii=False, default=str), encoding="utf-8")
        os.replace(tmp, final)  # atomik: yarım dosya asla görünmez
    except OSError:
        return None
    _prune()
    return sid


def _prune() -> None:
    """Ring-buffer: en eski dosyaları MAX sınırının üstündeyse sil."""
    try:
        files = _files()
        excess = len(files) - _max_snapshots()
        for p in files[: max(0, excess)]:
            p.unlink(missing_ok=True)
    except OSError:
        pass


def _latest_path() -> Path | None:
    files = _files()
    return files[-1] if files else None


def latest() -> dict | None:
    """En yeni OKUNABİLİR snapshot (bozuk dosyalar atlanır)."""
    for p in reversed(_files()):
        data = _read(p)
        if data is not None:
            return data
    return None


def get(snapshot_id: str) -> dict | None:
    """Verilen snapshot_id için en yeni okunabilir kayıt; yoksa None."""
    safe = _safe_id(snapshot_id)
    suffix = f"__{safe}.json"
    matches = [p for p in _files() if p.name.endswith(suffix)]
    for p in reversed(matches):
        data = _read(p)
        if data is not None:
            return data
    return None


def count() -> int:
    """Diskteki snapshot dosyası sayısı (atomik write → yarım dosya yok)."""
    return len(_files())


def list_ids() -> list[str]:
    ids: list[str] = []
    for p in _files():
        data = _read(p)
        if data is not None and data.get("snapshot_id"):
            ids.append(str(data["snapshot_id"]))
    return ids


def status() -> dict:
    """Store özeti — replay endpoint/panel için (read-only)."""
    latest_doc = latest()
    return {
        "snapshot_count": count(),
        "latest_snapshot_id": (latest_doc or {}).get("snapshot_id"),
        "latest_generated_at": (latest_doc or {}).get("generated_at"),
        "schema_version": SCHEMA_VERSION,
        "store_dir": str(_dir()),
    }


__all__ = [
    "SCHEMA_VERSION",
    "count",
    "get",
    "latest",
    "list_ids",
    "record",
    "status",
]
