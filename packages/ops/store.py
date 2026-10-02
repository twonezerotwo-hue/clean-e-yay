"""Tek atomik dosya yazma yardımcısı (temizlik B6).

Her runtime store'u eskiden kendi "tmp yaz + replace" kodunu taşıyordu; çoğu
sabit bir tmp adı kullanıyordu (`x.tmp`). Aynı dosyaya iki yazar (ör. API
thread'i ile tick thread'i) aynı anda yazarsa tmp'ler birbirine karışıyordu.

Burada:
- tmp adı her yazımda benzersiz (aynı klasörde, `.<ad>.<rastgele>.tmp`);
- Windows'ta okuyucu dosyayı tutarken `os.replace` kısa süre kilide takılabilir
  → artan beklemeyle yeniden dener;
- hata olursa tmp silinir, hedef dosyaya dokunulmaz (yarım dosya asla görünmez).

İçerik baytları `Path.write_text(text, encoding=...)` ile birebir aynıdır
(satır sonu çevirisi dahil), yani mevcut dosya biçimleri değişmez.
"""
from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

_REPLACE_RETRIES = 5
_RETRY_BASE_SLEEP_S = 0.05


def replace_with_retry(src: str | os.PathLike, dst: str | os.PathLike) -> None:
    """`os.replace`; geçici dosya kilidinde (PermissionError vb.) yeniden dener."""
    last: OSError | None = None
    for attempt in range(_REPLACE_RETRIES):
        try:
            os.replace(src, dst)
            return
        except OSError as exc:
            last = exc
            time.sleep(_RETRY_BASE_SLEEP_S * (attempt + 1))
    assert last is not None
    raise last


def write_text_atomic(path: str | os.PathLike, text: str, *, encoding: str = "utf-8") -> None:
    """`text`'i `path`'e atomik yaz (klasörü gerekirse oluşturur)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
        with contextlib.suppress(OSError):
            os.chmod(tmp, 0o644)  # mkstemp 0600 açar; düz write_text ile aynı izin
        replace_with_retry(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def write_json_atomic(path: str | os.PathLike, obj: Any, **dumps_kwargs: Any) -> None:
    """`json.dumps(obj, **dumps_kwargs)` çıktısını atomik yaz."""
    write_text_atomic(path, json.dumps(obj, **dumps_kwargs))


def read_tail_lines(path: str | os.PathLike, n: int, *, encoding: str = "utf-8",
                    chunk: int = 64 * 1024) -> list[str]:
    """Dosyanın son `n` satırı (B12). Dosyayı baştan okumaz: sondan blok blok geri
    gider. Append-only günlükler (paper_audit, decision_log ...) sınırsız büyür;
    "son N kayıt" okuması dosya boyundan bağımsız kalır. Satır sonları \n / \r\n."""
    n = max(1, int(n))
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        pos = fh.tell()
        buf = b""
        while pos > 0 and buf.count(b"\n") <= n:
            step = min(chunk, pos)
            pos -= step
            fh.seek(pos)
            buf = fh.read(step) + buf
    if pos > 0:  # ilk (yarım) satırı at — başı bloğun ortasına düşmüş olabilir
        buf = buf[buf.index(b"\n") + 1:]
    lines = buf.decode(encoding, errors="replace").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [ln.rstrip("\r") for ln in lines[-n:]]


def read_jsonl_tail(path: str | os.PathLike, limit: int) -> list[dict]:
    """Append-only JSONL'in son `limit` kaydı (en yeni en sonda). Dosya yok/okunamıyor
    → []; boş ve bozuk satırlar atlanır, asla raise etmez."""
    try:
        lines = read_tail_lines(path, limit)
    except OSError:
        return []
    out: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


__all__ = [
    "read_jsonl_tail",
    "read_tail_lines",
    "replace_with_retry",
    "write_json_atomic",
    "write_text_atomic",
]
