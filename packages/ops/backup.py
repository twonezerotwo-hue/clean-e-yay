"""Kritik çalışma durumunun günlük yedeği ve geri yükleme denemesi.

Hedef mimari 1. aşama (op_backup). Yalnız okur: kaynak dosyalara hiç yazmaz.
Her yedek, kritik dosyaların sıkıştırılmış kopyasıdır; arşiv yazıldıktan hemen
sonra geçici bir klasöre açılır, her dosyanın özeti karşılaştırılır ve içerik
ayrıştırılır (paper defteri gerçek `PaperState` ile yüklenir). Geri yüklenemeyen
yedek ``FAILED`` olarak kaydedilir. Karar, boyut ve RiskGate'e etkisi yoktur.

Elle geri yükleme: supervisor durdurulur, ``restore(arşiv, hedef_klasör)`` ile
dosyalar ayrı bir klasöre açılır, kontrol edilip data/runtime'a kopyalanır.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from packages.ops.store import replace_with_retry, write_text_atomic

# (env değişkeni, varsayılan yol) — canlı kodla aynı çözümleme; testlerde
# conftest bu değişkenleri geçici klasöre yönlendirir.
FILE_SOURCES: tuple[tuple[str, str], ...] = (
    ("PAPER_STATE_PATH", "data/runtime/paper_state.json"),
    ("DECISION_LOG_PATH", "data/runtime/decision_log.jsonl"),
    ("PAPER_AUDIT_PATH", "data/runtime/paper_audit.jsonl"),
    ("RISK_HALT_PATH", "data/runtime/risk_halts.json"),
    ("WEIGHTS_MANIFEST_PATH", "data/runtime/weights_active.json"),
    ("AGENT_MODE_STORE_PATH", "data/runtime/agent_mode.json"),
    ("GOVERNOR_PROPOSALS_PATH", "data/runtime/governor_proposals.json"),
    ("REGIME_STATE_PATH", "data/runtime/regime_state.json"),
    ("TICKETS_PATH", "data/runtime/tickets.json"),
    ("PAPER_CANARY_PATH", "data/runtime/paper_canary.json"),
)
DIR_SOURCES: tuple[tuple[str, str], ...] = (
    ("WEIGHTS_OUTPUT_DIR", "data/runtime/weights"),
)
# Karar kaydının yalnız son günleri yedeklenir (arşiv büyümesin).
RECORD_DAYS = 2
ARCHIVE_PREFIX = "eyay-runtime-"
INTERVAL = timedelta(hours=20)


def _backup_dir() -> Path:
    return Path(os.environ.get("BACKUP_DIR", "data/backups"))


def _status_path() -> Path:
    return Path(os.environ.get("BACKUP_STATUS_PATH", "data/runtime/backup_status.json"))


def _retention_days() -> int:
    try:
        return max(1, int(os.environ.get("BACKUP_RETENTION_DAYS", "14")))
    except ValueError:
        return 14


def _sources() -> list[tuple[str, Path]]:
    """Arşivdeki ad → kaynak yol. Yalnız var olan dosyalar döner."""
    out: list[tuple[str, Path]] = []
    for env, default in FILE_SOURCES:
        path = Path(os.environ.get(env) or default)
        out.append((path.name, path))
    for env, default in DIR_SOURCES:
        folder = Path(os.environ.get(env) or default)
        if folder.is_dir():
            out.extend((f"{folder.name}/{p.name}", p) for p in sorted(folder.iterdir()) if p.is_file())
    record_dir = Path(os.environ.get("DECISION_RECORD_DIR") or "data/runtime/decision_record")
    if record_dir.is_dir():
        days = sorted(record_dir.glob("????-??-??.jsonl"))[-RECORD_DAYS:]
        out.extend((f"decision_record/{p.name}", p) for p in days)
    return out


def _read_consistent(path: Path) -> bytes:
    """Dosyayı tutarlı bir anda okur; JSONL'de yarım kalmış son satırı dışarıda bırakır."""
    data = b""
    for attempt in range(3):
        try:
            data = path.read_bytes()
            break
        except PermissionError:  # Windows: os.replace sırasında kısa kilit
            if attempt == 2:
                raise
            time.sleep(0.2)
    if path.suffix == ".jsonl" and data and not data.endswith(b"\n"):
        cut = data.rfind(b"\n")
        data = data[: cut + 1] if cut >= 0 else b""
    return data


def _check_content(name: str, data: bytes) -> str | None:
    """İçerik ayrıştırılamıyorsa hata metni döner."""
    try:
        if name.endswith(".jsonl"):
            for line in data.splitlines():
                if line.strip():
                    json.loads(line)
        elif name.endswith(".json"):
            payload = json.loads(data)
            if name == "paper_state.json":
                from packages.paper.state import PaperState

                # Yükleyici ileri uyum için hoşgörülü; yedek "boş ama açılıyor"
                # sayılmasın diye sermaye alanı ve pozisyon sayısı ayrıca denetlenir.
                if not isinstance(payload, dict) or "equity_usd" not in payload:
                    raise ValueError("equity_usd yok")
                raw_positions = payload.get("open_positions")
                state = PaperState.from_dict(payload)
                if not isinstance(raw_positions, list) or len(state.open_positions) != len(raw_positions):
                    raise ValueError("açık pozisyonlar eksik yüklendi")
    except Exception as exc:  # içerik hatası raporlanır, yükseltilmez
        return f"{type(exc).__name__}: {str(exc)[:120]}"
    return None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify(archive: Path) -> dict[str, Any]:
    """Arşivi geçici klasöre açar; özet ve içerik kontrolü yapar (geri yükleme denemesi)."""
    errors: list[str] = []
    checked = 0
    with tempfile.TemporaryDirectory(prefix="eyay-restore-") as tmp:
        with zipfile.ZipFile(archive) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            zf.extractall(tmp)
        for item in manifest.get("files", []):
            data = (Path(tmp) / item["name"]).read_bytes()
            if _sha(data) != item["sha256"]:
                errors.append(f"{item['name']}: özet uyuşmuyor")
                continue
            problem = _check_content(item["name"], data)
            if problem:
                errors.append(f"{item['name']}: {problem}")
            checked += 1
    return {"status": "OK" if not errors else "FAILED", "files_verified": checked, "errors": errors}


def restore(archive: Path, target_dir: Path) -> list[Path]:
    """Arşivi doğrulayıp ``target_dir`` altına açar. data/runtime'a kendisi yazmaz."""
    result = verify(archive)
    if result["status"] != "OK":
        raise ValueError(f"yedek doğrulanamadı: {result['errors']}")
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with zipfile.ZipFile(archive) as zf:
        for name in zf.namelist():
            if name == "manifest.json":
                continue
            out = target_dir / name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(zf.read(name))
            written.append(out)
    return written


def _prune(folder: Path, now: datetime, keep: Path) -> list[str]:
    """Saklama süresini aşan kendi arşivlerimizi siler; başka dosyaya dokunmaz."""
    cutoff = now - timedelta(days=_retention_days())
    removed: list[str] = []
    for path in folder.glob(f"{ARCHIVE_PREFIX}*.zip"):
        if path == keep:
            continue
        try:
            stamp = datetime.strptime(path.stem[len(ARCHIVE_PREFIX):], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        except ValueError:
            continue
        if stamp < cutoff:
            path.unlink(missing_ok=True)
            removed.append(path.name)
    return removed


def read_status() -> dict[str, Any]:
    try:
        return json.loads(_status_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def run(now: datetime | None = None) -> dict[str, Any]:
    """Bir yedek alır, doğrular, eski yedekleri temizler ve durumu yazar."""
    now = now or datetime.now(UTC)
    folder = _backup_dir()
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / f"{ARCHIVE_PREFIX}{now.strftime('%Y%m%dT%H%M%SZ')}.zip"
    files: list[dict[str, Any]] = []
    missing: list[str] = []
    unreadable: list[str] = []
    tmp_archive = archive.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp_archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, path in _sources():
            if not path.is_file():
                missing.append(name)
                continue
            try:
                data = _read_consistent(path)
            except OSError as exc:
                unreadable.append(f"{name}: {type(exc).__name__}")
                continue
            problem = _check_content(name, data)
            if problem:
                unreadable.append(f"{name}: {problem}")
            zf.writestr(name, data)
            files.append({"name": name, "bytes": len(data), "sha256": _sha(data)})
        zf.writestr("manifest.json", json.dumps({"created_at": now.isoformat(), "files": files}, ensure_ascii=False))
    replace_with_retry(tmp_archive, archive)
    check = verify(archive)
    previous = read_status()
    status = "FAILED" if check["status"] != "OK" or not files else ("DEGRADED" if unreadable else "OK")
    result: dict[str, Any] = {
        "status": status,
        "last_run_at": now.isoformat(),
        "last_ok_at": now.isoformat() if status == "OK" else previous.get("last_ok_at"),
        "archive": str(archive),
        "size_bytes": archive.stat().st_size,
        "files": files,
        "missing": missing,
        "unreadable": unreadable,
        "restore_check": {**check, "checked_at": now.isoformat()},
        "retention_days": _retention_days(),
        "pruned": _prune(folder, now, archive),
    }
    write_text_atomic(_status_path(), json.dumps(result, ensure_ascii=False, indent=2))
    return result


def run_if_due(now: datetime | None = None) -> dict[str, Any]:
    """Son denemeden bu yana ``INTERVAL`` geçtiyse yedek alır."""
    now = now or datetime.now(UTC)
    last = read_status().get("last_run_at")
    try:
        if last and now - datetime.fromisoformat(last) < INTERVAL:
            return {"ran": False, "last_run_at": last}
    except ValueError:
        pass
    return {"ran": True, **run(now)}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
