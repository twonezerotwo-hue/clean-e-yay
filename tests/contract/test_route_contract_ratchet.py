"""Sözleşme-önce ratchet'i (B1): kodda tanımlı her route openapi.yaml'da olmalı.

Mevcut borç `contractless_routes.txt` içinde dondurulmuştur ve yalnız küçülebilir:
- Yeni bir route sözleşmeye eklenmeden kodda belirirse test kırılır.
- Listedeki bir route sözleşmeye eklenir ya da silinirse, listeden de çıkarılmalı
  (bayat giriş de test'i kırar — borç gerçekten kapandığında kayıt düşer).
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
ALLOWLIST = Path(__file__).with_name("contractless_routes.txt")
_METHODS = {"get", "post", "put", "patch", "delete"}


def _contract_routes() -> set[tuple[str, str]]:
    spec = yaml.safe_load((REPO / "contracts" / "openapi.yaml").read_text(encoding="utf-8"))
    return {
        (m.upper(), p) for p, ops in spec["paths"].items() for m in ops if m in _METHODS
    }


def _code_routes() -> set[tuple[str, str]]:
    from apps.api.main import create_app

    schema = create_app().openapi()
    return {(m.upper(), p) for p, ops in schema["paths"].items() for m in ops if m in _METHODS}


def _allowlist() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for line in ALLOWLIST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            method, path = line.split(maxsplit=1)
            out.add((method, path))
    return out


def test_no_new_contractless_routes() -> None:
    debt = _code_routes() - _contract_routes()
    new = sorted(debt - _allowlist())
    assert not new, (
        "Sözleşmede olmayan YENİ route(lar): önce contracts/openapi.yaml'a ekle + make codegen.\n"
        + "\n".join(f"{m} {p}" for m, p in new)
    )


def test_allowlist_has_no_stale_entries() -> None:
    debt = _code_routes() - _contract_routes()
    stale = sorted(_allowlist() - debt)
    assert not stale, (
        "Borç kapanmış route'lar listede kalmış; contractless_routes.txt'den çıkar:\n"
        + "\n".join(f"{m} {p}" for m, p in stale)
    )
