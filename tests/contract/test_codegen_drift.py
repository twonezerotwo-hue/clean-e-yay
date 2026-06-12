"""OPS — codegen drift guard.

`apps/web/types/generated/api.ts` `contracts/openapi.yaml`'dan **el ile**
türetiliyor (henüz `openapi-typescript` koşulmuyor). Bu test, manuel
senkronizasyonun kaçırdığı drifti CI'da yakalar:

1. Her OpenAPI component schema adının bir TS `export type` karşılığı var
   (isim farkları `ALIAS` ile tolere edilir).
2. Her OpenAPI enum üyesi TS dosyasında string-literal olarak mevcut —
   şemaya yeni enum değeri eklenip TS'e yansıtılmazsa fail.

Bu test koşuluyor olduğu sürece "manuel type divergence" sessizce kalamaz.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = yaml.safe_load((ROOT / "contracts" / "openapi.yaml").read_text(encoding="utf-8"))
TS = (ROOT / "apps" / "web" / "types" / "generated" / "api.ts").read_text(encoding="utf-8")

# OpenAPI schema adı → TS export adı (bilinçli isim farkları).
ALIAS = {
    "TechnicalSnapshotTF": "TechnicalTf",
}

TS_TYPES = set(re.findall(r"export type (\w+)", TS))
TS_LITERALS = set(re.findall(r'"([^"]*)"', TS))


def _schema_names() -> list[str]:
    return list(SPEC["components"]["schemas"].keys())


def test_every_schema_has_ts_type():
    missing = []
    for name in _schema_names():
        ts_name = ALIAS.get(name, name)
        if ts_name not in TS_TYPES:
            missing.append(f"{name} (→ {ts_name})")
    assert not missing, (
        "OpenAPI şemalarının TS karşılığı yok (api.ts güncellenmeli): "
        + ", ".join(missing)
    )


def _collect_enums(node, acc: list[list[str]]) -> None:
    if isinstance(node, dict):
        enum = node.get("enum")
        if isinstance(enum, list):
            acc.append([v for v in enum if isinstance(v, str)])
        for v in node.values():
            _collect_enums(v, acc)
    elif isinstance(node, list):
        for v in node:
            _collect_enums(v, acc)


def test_every_enum_member_present_in_ts():
    enums: list[list[str]] = []
    _collect_enums(SPEC["components"]["schemas"], enums)
    missing = set()
    for members in enums:
        for m in members:
            if m and m not in TS_LITERALS:
                missing.add(m)
    assert not missing, (
        "OpenAPI enum üyeleri TS'te string-literal olarak yok "
        "(api.ts union'ları güncellenmeli): " + ", ".join(sorted(missing))
    )
