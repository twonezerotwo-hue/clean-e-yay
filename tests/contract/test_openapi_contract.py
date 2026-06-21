"""OPS — OpenAPI ↔ runtime response sözleşme testleri.

`contracts/openapi.yaml` tek doğruluk kaynağıdır. Bu test, dokümante edilmiş
her **side-effect'siz GET** endpoint'ini FastAPI TestClient ile çağırır ve
gerçek response'u şemaya göre doğrular:

- `required` alanlar mevcut mu,
- `enum` üyeleri tutuyor mu,
- `$ref` / `oneOf` recursive çözülür.

Additive alanlara izin verilir (şemada olmayan ekstra alan hata DEĞİL — bkz.
ARCHITECTURE §15 additive kuralı). El-senkron TS tipleri + openapi.yaml
drift'i burada yakalanır. Live network yok (conftest `TEST_USE_MOCK=true`).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from apps.api.main import app

ROOT = Path(__file__).resolve().parents[2]
SPEC = yaml.safe_load((ROOT / "contracts" / "openapi.yaml").read_text(encoding="utf-8"))

client = TestClient(app)


def _resolve(ref: str, spec: dict) -> dict:
    node = spec
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def _validate(instance, schema, spec, path, errors) -> None:
    if schema is None:
        return
    if "$ref" in schema:
        schema = _resolve(schema["$ref"], spec)

    # oneOf / anyOf: en az bir dal geçerse OK.
    for key in ("oneOf", "anyOf"):
        if key in schema:
            for branch in schema[key]:
                sub: list[str] = []
                _validate(instance, branch, spec, path, sub)
                if not sub:
                    return
            errors.append(f"{path}: {instance!r} hiçbir {key} dalıyla eşleşmedi")
            return

    stype = schema.get("type")
    if stype == "null":
        if instance is not None:
            errors.append(f"{path}: null bekleniyordu, {type(instance).__name__} geldi")
        return

    # null değer: nullable veya opsiyonel — tolere et (required kontrolü key
    # varlığına bakar, değerine değil).
    if instance is None:
        return

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} enum {schema['enum']} içinde değil")

    if stype == "object" or "properties" in schema or "additionalProperties" in schema:
        if not isinstance(instance, dict):
            errors.append(f"{path}: object bekleniyordu, {type(instance).__name__} geldi")
            return
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path}: zorunlu alan '{req}' eksik")
        props = schema.get("properties", {})
        for k, sub_schema in props.items():
            if k in instance:
                _validate(instance[k], sub_schema, spec, f"{path}.{k}", errors)
        ap = schema.get("additionalProperties")
        if isinstance(ap, dict):
            for k, v in instance.items():
                if k not in props:
                    _validate(v, ap, spec, f"{path}.{k}", errors)
    elif stype == "array":
        if not isinstance(instance, list):
            errors.append(f"{path}: array bekleniyordu, {type(instance).__name__} geldi")
            return
        items = schema.get("items")
        for i, el in enumerate(instance):
            _validate(el, items, spec, f"{path}[{i}]", errors)
    # primitive (string/number/integer/boolean): tolerant — date-time vs string,
    # int vs number gibi nüanslar drift sinyali değil; required + enum yeterli.


def _documented_get_endpoints():
    out = []
    for p, item in SPEC["paths"].items():
        if "get" not in item or "{" in p:  # path-param'lı GET ayrı test edilir
            continue
        content = item["get"].get("responses", {}).get("200", {}).get("content", {})
        # SSE / streaming endpoint'leri request-response değil — blocking
        # client.get() ile test edilemez (akış kopana dek bekler). Conformance
        # dışında tutulur.
        if "text/event-stream" in content:
            continue
        schema = content.get("application/json", {}).get("schema")
        out.append((p, schema))
    return out


GET_ENDPOINTS = _documented_get_endpoints()


@pytest.mark.parametrize("path,schema", GET_ENDPOINTS, ids=[p for p, _ in GET_ENDPOINTS])
def test_get_endpoint_matches_contract(path, schema):
    """Her dokümante GET endpoint'i 200 döner ve şemaya uyar (drift → fail)."""
    r = client.get(path)
    assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"
    if schema is None:
        return
    errors: list[str] = []
    _validate(r.json(), schema, SPEC, path, errors)
    assert not errors, f"{path} sözleşme ihlali:\n" + "\n".join(errors)


def test_replay_snapshot_path_param_missing_returns_404():
    """R1 — store'da olmayan snapshot_id → 404 (sahte replay/refetch yok)."""
    r = client.get("/api/v1/replay/no-such-snapshot-id-xyz")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert detail["status"] == "not_found"
    assert detail["available"] is False


def test_replay_decision_trace_missing_returns_404():
    """R1 — olmayan snapshot için decision-trace → 404."""
    r = client.get("/api/v1/replay/no-such-snapshot-id-xyz/decision-trace")
    assert r.status_code == 404
    assert r.json()["detail"]["status"] == "not_found"


def test_all_documented_paths_have_router():
    """openapi.yaml'daki her path FastAPI uygulamasında kayıtlı (path drift guard).

    Kaynak olarak app'in KENDİ ürettiği OpenAPI path kümesini kullanıyoruz: included
    router'lar fastapi/starlette sürümüne göre `app.routes` içinde düz `Route` yerine
    bir `_IncludedRouter` sarmalayıcı olarak görünebilir (path'siz). `app.openapi()`
    ise sürümden bağımsız olarak gerçekten sunulan tüm endpoint path'lerini kapsar.
    """
    documented = set(SPEC["paths"].keys())
    registered = set(app.openapi()["paths"].keys())
    missing = sorted(documented - registered)
    assert not missing, f"openapi.yaml'da olup app'te olmayan path'ler: {missing}"
