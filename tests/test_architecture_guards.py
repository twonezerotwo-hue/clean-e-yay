"""Architecture guards — structural invariants that keep the clean backbone clean.

These are *structural* tests (they read source files), not behaviour tests. Behaviour
of the RiskGate itself is covered by tests/unit/test_event_risk.py and test_halt.py.

Phase 1 lands four guards (system rules 2, 6, 7):
  - API stays a thin HTTP layer: no background/tick loop inside apps/api.
  - One canonical RiskGate: RiskDecision/RiskAction defined only in packages/risk/engine.py.
  - Contract-first: generated TS types are in sync with contracts/openapi.yaml.
  - No frontend type drift: structural friendly types map to an OpenAPI schema.

Phase 6 extends this file (no-mock-in-prod, no AUTO_FULL, AI no-boost, no frontend
decision math).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
API_DIR = REPO / "apps" / "api"
RISK_ENGINE = REPO / "packages" / "risk" / "engine.py"
OPENAPI = REPO / "contracts" / "openapi.yaml"
WEB_SCHEMA_TS = REPO / "apps" / "web" / "types" / "generated" / "schema.ts"
WEB_API_TS = REPO / "apps" / "web" / "types" / "generated" / "api.ts"
CODEGEN = REPO / "scripts" / "codegen.py"


def _py_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


# ── Rule 7: API must stay thin — no background/tick loop in apps/api ──────────

# Patterns that indicate the HTTP layer is owning a long-running/scheduled loop.
_BG_LOOP_PATTERNS = [
    r"\bwhile\s+True\b",
    r"asyncio\.create_task",
    r"\bcreate_task\s*\(",
    r"BackgroundScheduler",
    r"AsyncIOScheduler",
    r"\.add_job\s*\(",
    r"@repeat_every",
    r"ensure_future\s*\(",
]


def test_api_has_no_background_loop() -> None:
    offenders: list[str] = []
    compiled = [re.compile(p) for p in _BG_LOOP_PATTERNS]
    for path in _py_files(API_DIR):
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            for rx in compiled:
                if rx.search(line):
                    rel = path.relative_to(REPO)
                    offenders.append(f"{rel}:{i}: {line.strip()}")
    assert not offenders, (
        "apps/api must be a thin HTTP layer (no tick/background loop). "
        "Move loops to apps/tick_worker. Offenders:\n" + "\n".join(offenders)
    )


# ── Rule 2: exactly one canonical RiskGate ───────────────────────────────────


def _files_defining(pattern: str, roots: list[Path]) -> list[Path]:
    rx = re.compile(pattern, re.M)
    hits: list[Path] = []
    for root in roots:
        for path in _py_files(root):
            if rx.search(path.read_text(encoding="utf-8")):
                hits.append(path)
    return hits


def test_single_riskgate_decision_class() -> None:
    roots = [REPO / "packages", REPO / "apps"]
    hits = _files_defining(r"^class RiskDecision\b", roots)
    rels = sorted(str(p.relative_to(REPO)) for p in hits)
    assert rels == ["packages/risk/engine.py"], (
        "RiskDecision must be defined once (the canonical gate). Found in: " + ", ".join(rels)
    )


def test_single_riskgate_action_enum() -> None:
    roots = [REPO / "packages", REPO / "apps"]
    hits = _files_defining(r"^RiskAction\s*=\s*Literal\[", roots)
    rels = sorted(str(p.relative_to(REPO)) for p in hits)
    assert rels == ["packages/risk/engine.py"], (
        "The canonical RiskAction enum must live only in packages/risk/engine.py. "
        "Found in: " + ", ".join(rels)
    )


# ── Rule 6: contract-first — generated TS in sync, no friendly type drift ─────


def _node_available() -> bool:
    bin_ts = REPO / "apps" / "web" / "node_modules" / ".bin" / "openapi-typescript"
    if not bin_ts.exists():
        return False
    if shutil.which("node"):
        return True
    return (Path.home() / ".local" / "node" / "bin" / "node").exists()


@pytest.mark.skipif(not _node_available(), reason="node/openapi-typescript not installed")
def test_openapi_schema_ts_in_sync() -> None:
    """Generated schema.ts must match what `make codegen` produces from openapi.yaml."""
    res = subprocess.run(
        [sys.executable, str(CODEGEN), "--check"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, (
        "Generated TS types are stale. Run `make codegen` and commit.\n"
        + (res.stdout + res.stderr)
    )


def _iter_export_types(ts: str):
    """Yield (name, rhs) for each `export type Name = ... ;` (multiline-aware)."""
    for m in re.finditer(r"^export type (\w+)\s*=\s*(.*?);", ts, re.S | re.M):
        yield m.group(1), " ".join(m.group(2).split())


# Allow an optional leading `|` (TS multiline union style).
_LITERAL_UNION = re.compile(r'^\|?\s*"[^"]*"(\s*\|\s*"[^"]*")*$')

# Pre-existing frontend-only object types with no OpenAPI schema yet (contract debt
# inherited from clean's hand-written friendly layer). Phase 3 promotes each of these
# to a named schema in contracts/openapi.yaml as its panel is wired to a ViewModel.
# This guard is a *ratchet*: it allows these known orphans but fails on any NEW one.
KNOWN_UNCONTRACTED = {
    "AgentBriefCandidate",
    "ClusterPosition",
    "LearningWorkerRun",
    "OutcomeBucket",
    "SnapshotMode",
    "TechnicalTf",
}


def test_friendly_types_map_to_contract() -> None:
    """Every *structural* friendly type in api.ts must correspond to an OpenAPI schema.

    Pure string-literal unions (inline enums) need no named schema. The
    KNOWN_UNCONTRACTED set baselines pre-existing debt; any *new* structural type
    without a schema fails the guard, enforcing contract-first going forward.
    """
    schemas = set(yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))["components"]["schemas"])
    ts = WEB_API_TS.read_text(encoding="utf-8")
    stale: list[str] = []
    for name, rhs in _iter_export_types(ts):
        if _LITERAL_UNION.match(rhs):
            continue  # inline enum — no named schema required
        if name in KNOWN_UNCONTRACTED:
            continue  # baselined debt — tracked in MIGRATION_MAP, fixed in Phase 3
        if name not in schemas:
            stale.append(name)
    assert not stale, (
        "NEW structural friendly type(s) in apps/web/types/generated/api.ts have no "
        "matching OpenAPI schema (contract drift). Add the schema to contracts/openapi.yaml "
        "first (contract-first), or add to KNOWN_UNCONTRACTED with justification: "
        + ", ".join(sorted(stale))
    )


def test_generated_schema_ts_is_marked_generated() -> None:
    assert WEB_SCHEMA_TS.exists(), "Run `make codegen` to generate schema.ts"
    head = WEB_SCHEMA_TS.read_text(encoding="utf-8")[:300]
    assert "auto-generated" in head.lower(), "schema.ts must carry a generated marker"


# ── No-AI-boost: AI/opinion/persona/learning size factors may only REDUCE ─────
# (Phase 2c invariant made structural — AI must never increase position size.)

PACKAGES = REPO / "packages"


def test_no_size_factor_constant_above_one() -> None:
    """SIZE_FACTOR_* constants must be restrictive-only (≤ 1.0) — blocks a boost
    constant (e.g. SIZE_FACTOR_BOOST = 1.2) from being reintroduced."""
    rx = re.compile(r"^\s*(SIZE_FACTOR_\w+)\s*=\s*([0-9]+(?:\.[0-9]+)?)", re.M)
    offenders: list[str] = []
    for path in _py_files(PACKAGES):
        for name, val in rx.findall(path.read_text(encoding="utf-8")):
            if float(val) > 1.0:
                offenders.append(f"{path.relative_to(REPO)}: {name}={val}")
    assert not offenders, (
        "AI/learning size factors may only reduce (≤ 1.0). Boost constant(s): "
        + ", ".join(offenders)
    )


def test_learning_size_factor_is_clamped_in_decision_engine() -> None:
    """The mistake-memory factor must be applied clamped so a BOOST can't grow size."""
    src = (PACKAGES / "decision" / "engine.py").read_text(encoding="utf-8")
    assert "min(1.0, verdict.size_factor)" in src, (
        "decision engine must clamp verdict.size_factor to ≤ 1.0"
    )
    assert re.search(r"size\s*\*=\s*verdict\.size_factor\b", src) is None, (
        "unclamped `size *= verdict.size_factor` reintroduced — AI/learning may not boost"
    )


# An AI/opinion/persona/LLM term being multiplied into a size. "conviction" is
# intentionally excluded — deterministic consensus conviction is allowed.
_AI_MULT_TERM = re.compile(r"\*\s*[\w.]*(?:opinion|persona|llm|ai_mult)[\w.]*", re.I)


def test_ai_opinion_multipliers_go_through_clamp() -> None:
    """Any AI/opinion/persona/LLM multiplier applied to a value must be clamped via
    clamp_ai_multiplier — there is no other sanctioned path for AI to affect size."""
    offenders: list[str] = []
    for path in _py_files(PACKAGES):
        if path.name == "sizing.py":
            continue  # defines clamp_ai_multiplier / apply_ai_opinion
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if _AI_MULT_TERM.search(line) and "clamp_ai_multiplier" not in line:
                offenders.append(f"{path.relative_to(REPO)}:{i}: {stripped}")
    assert not offenders, (
        "AI/opinion/persona multiplier applied without clamp_ai_multiplier:\n"
        + "\n".join(offenders)
    )
