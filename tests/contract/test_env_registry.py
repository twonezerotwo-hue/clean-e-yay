"""B9 — kodun okuduğu her env adı packages/ops/env_registry.py'de kayıtlı olmalı."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from packages.learning import monitoring_coverage
from packages.ops.env_registry import KINDS, REGISTRY

REPO = Path(__file__).resolve().parents[2]
_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")


def _is_environ(n: ast.AST) -> bool:
    return (isinstance(n, ast.Attribute) and n.attr == "environ"
            and isinstance(n.value, ast.Name) and n.value.id == "os")


def _scan() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    files = list((REPO / "packages").rglob("*.py")) + list((REPO / "apps").rglob("*.py"))
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        consts = {}
        for st in tree.body:
            if isinstance(st, ast.Assign) and isinstance(st.value, ast.Constant) \
                    and isinstance(st.value.value, str):
                for t in st.targets:
                    if isinstance(t, ast.Name):
                        consts[t.id] = st.value.value

        def lit(a, consts=consts):
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                return a.value
            if isinstance(a, ast.Name):
                return consts.get(a.id)
            return None

        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Call) and node.args and lit(node.args[0]):
                fn, arg = node.func, lit(node.args[0])
                if isinstance(fn, ast.Attribute) and fn.attr in ("get", "setdefault", "pop") \
                        and _is_environ(fn.value):
                    name = arg
                elif isinstance(fn, ast.Attribute) and fn.attr == "getenv" \
                        and isinstance(fn.value, ast.Name) and fn.value.id == "os":
                    name = arg
                else:
                    fname = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                    if re.search(r"env|flag", fname, re.I) and _NAME.match(arg):
                        name = arg
            elif isinstance(node, ast.Subscript) and _is_environ(node.value) and lit(node.slice):
                name = lit(node.slice)
            if name and _NAME.match(name):
                found.setdefault(name, set()).add(f.relative_to(REPO).as_posix())
    return found


def test_every_env_read_is_registered():
    found = _scan()
    missing = sorted(set(found) - set(REGISTRY))
    assert not missing, (
        "Kayıtsız env okuması — packages/ops/env_registry.py'ye ekle: "
        + ", ".join(f"{n} ({sorted(found[n])[0]})" for n in missing)
    )


def test_registry_has_no_stale_entries():
    stale = sorted(set(REGISTRY) - set(_scan()))
    assert not stale, f"Artık okunmayan kayıtlar (sil): {stale}"


def test_kinds_are_known():
    assert set(REGISTRY.values()) <= set(KINDS)


def test_monitoring_coverage_uses_registered_names():
    """İzleme defterindeki (monitoring_coverage) env adları kodda gerçekten okunuyor olmalı."""
    unknown = sorted(n for n in monitoring_coverage.COVERAGE if _NAME.match(n) and n not in REGISTRY)
    assert not unknown, f"monitoring_coverage'daki adlar kodda okunmuyor: {unknown}"
