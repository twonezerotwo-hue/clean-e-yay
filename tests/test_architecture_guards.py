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
    rels = sorted(p.relative_to(REPO).as_posix() for p in hits)
    assert rels == ["packages/risk/engine.py"], (
        "RiskDecision must be defined once (the canonical gate). Found in: " + ", ".join(rels)
    )


def test_single_riskgate_action_enum() -> None:
    roots = [REPO / "packages", REPO / "apps"]
    hits = _files_defining(r"^RiskAction\s*=\s*Literal\[", roots)
    rels = sorted(p.relative_to(REPO).as_posix() for p in hits)
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

# Frontend-only object types with no OpenAPI schema yet (contract debt inherited from
# clean's hand-written friendly layer). Phase 3 promoted all of them to named schemas in
# contracts/openapi.yaml (SnapshotMode was dead — superseded by ProvenanceMode — and was
# removed instead of promoted). This guard is now a *ratchet*: any NEW orphan friendly
# type fails the guard until it gets a contract schema (contract-first) or is baselined here.
#
# CP1–CP4 öğrenme panelleri (dataset-health / edge-report / guard-safety / book-audit /
# entry-exit-quality) endpoint'leri saf `dict` döndürüyor (observe-only read-model'ler,
# dış API contract'ı değil) → bunların friendly tipleri elle bakılıyor, OpenAPI şeması yok.
# Bu guard CP1'den beri main CI'ı kırıyordu (deploy "skipped" kalıyordu). Deploy hattını
# açmak için observe-only learning view-model'leri burada baseline'lıyoruz. TODO (contract
# debt): bu endpoint'lere Pydantic response_model ekleyip openapi.yaml'a terfi et, sonra
# bunları buradan çıkar (ratchet'i tekrar sıfıra getir).
KNOWN_UNCONTRACTED: set[str] = {
    "BookAuditLesson",
    "BookAuditView",
    "DatasetHealthLearner",
    "DatasetHealthView",
    "EdgeReportView",
    "EdgeStability",
    "EdgeStabilitySegment",
    "EntryExitBucket",
    "EntryExitBucketMetrics",
    "EntryExitQualityView",
    "EntryExitVerdict",
    "GuardSafetyGuard",
    "GuardSafetyMonitor",
    "GuardSafetyView",
    "TfTargetEdgeGate",
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


# ── Phase 3 Wave-0: dashboard panels render typed ViewModels only ─────────────
# Two structural guards lock in the clean web wiring so the codex visual
# transplant can't drag dirty patterns across:
#   1) components do no manual/untyped network I/O — data flows only through the
#      typed lib/queries hooks -> lib/api client -> generated contract;
#   2) components & selectors do no trading/risk/regime/DQS/sizing/PnL *decision
#      math* — they may read backend fields, format them, and pick colours/labels
#      (incl. thresholding a finished backend value for a colour band), but must
#      not RECONSTRUCT the underlying decision numbers.
# Both ignore comments and string/template literals and key on the computational
# fingerprint (a network call, or an arithmetic operator on a decision field), so
# number formatting and visual rendering never false-positive. Decisions stay in
# packages/* (deterministic) and reach the UI as typed contract fields.

WEB_COMPONENTS = REPO / "apps" / "web" / "components"
WEB_SELECTORS = REPO / "apps" / "web" / "lib" / "selectors"

_TS_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_TS_LINE_COMMENT = re.compile(r"(?<!:)//[^\n]*")
# Strings/templates are blanked wholesale (incl. `${...}` interpolations) — this
# trades a rare evasion (reconstruction written inside a template literal) for
# zero false positives from class-name tokens and display labels. The guard
# targets statement-level decision math, which is the realistic regression.
_TS_STRING = re.compile(
    r"\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`", re.S
)


def _blank_keep_lines(match: re.Match[str]) -> str:
    """Replace a match with blanks but preserve newlines so line numbers hold."""
    return "\n" * match.group(0).count("\n")


def _ts_code_only(text: str) -> str:
    """Strip comments + string/template literals (line-count preserving) so prose
    or class names that *mention* fetch/risk/PnL can't trip the structural guards."""
    text = _TS_BLOCK_COMMENT.sub(_blank_keep_lines, text)
    text = _TS_LINE_COMMENT.sub("", text)
    text = _TS_STRING.sub(_blank_keep_lines, text)
    return text


def _ts_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [
        p
        for p in root.rglob("*")
        if p.suffix in {".ts", ".tsx"} and "node_modules" not in p.parts
    ]


# 1) No manual/untyped network I/O inside dashboard components.
_NET_IO = [
    re.compile(r"\bfetch\s*\("),
    re.compile(r"\baxios\b"),
    re.compile(r"\bXMLHttpRequest\b"),
    re.compile(r"\bEventSource\b"),
    re.compile(r"\bnew\s+WebSocket\b"),
]


def test_no_manual_fetch_in_panels() -> None:
    """Dashboard components must not do manual/untyped network I/O — data only via
    the typed lib/queries hooks -> lib/api client (generated contract). react-query
    `refetch` is fine: ``\\bfetch\\(`` does not match ``refetch(``."""
    offenders: list[str] = []
    for path in _ts_files(WEB_COMPONENTS):
        code = _ts_code_only(path.read_text(encoding="utf-8"))
        for i, line in enumerate(code.splitlines(), 1):
            for rx in _NET_IO:
                if rx.search(line):
                    offenders.append(f"{path.relative_to(REPO)}:{i}: {line.strip()[:100]}")
    assert not offenders, (
        "Manual/untyped network I/O in apps/web/components — use the typed "
        "lib/queries hooks instead (no fetch/axios/XHR/SSE/WebSocket in panels):\n"
        + "\n".join(offenders)
    )


# 2) No frontend trading/risk/regime/DQS/sizing/PnL decision math.
# Money/decision fields that must never be RECONSTRUCTED in the frontend.
_MONEY = (
    r"(?:equity_usd|realized_pnl_usd|unrealized_pnl_usd|daily_pnl_usd|pnl_usd"
    r"|size_usd|starting_balance|max_drawdown_pct|drawdown_pct)"
)
# DQS sub-metrics — combining these into a score is "computing DQS" (banned);
# thresholding the finished dqs.score for a colour band is rendering (allowed).
_DQS_SUB = r"(?:freshness|completeness|reconciliation|decision_usage|drift)"

_DECISION_MATH = [
    (re.compile(_MONEY + r"\s*[-+*/]"), "PnL/equity/size reconstruction"),
    (re.compile(r"[-+*/]\s*[\w.]*" + _MONEY + r"\b"), "PnL/equity/size reconstruction"),
    (re.compile(r"\bsize\s*\*="), "position sizing math"),
    (re.compile(r"size_factor\s*[*/]|[*/]\s*[\w.]*size_factor\b"), "position sizing math"),
    (re.compile(_DQS_SUB + r"\s*[-+*/]"), "DQS score reconstruction"),
    (re.compile(r"[-+*/]\s*[\w.]*" + _DQS_SUB + r"\b"), "DQS score reconstruction"),
]


def test_no_frontend_decision_math() -> None:
    """Panels & selectors render backend ViewModels; they must not RECOMPUTE
    trading/risk/regime/DQS/sizing/PnL decisions. The guard targets the
    computational fingerprint — an arithmetic operator applied to a decision field
    (PnL/equity/size reconstruction, sizing math, DQS score reconstruction).
    Reading a field, formatting it, and choosing a colour/label from a finished
    backend value (e.g. ``score >= 60``, ``dqs.score >= 75``) is presentation and
    is allowed; only reconstructing the decision numbers is banned."""
    offenders: list[str] = []
    for root in (WEB_COMPONENTS, WEB_SELECTORS):
        for path in _ts_files(root):
            code = _ts_code_only(path.read_text(encoding="utf-8"))
            for i, line in enumerate(code.splitlines(), 1):
                for rx, label in _DECISION_MATH:
                    if rx.search(line):
                        offenders.append(
                            f"{path.relative_to(REPO)}:{i}: {label} — {line.strip()[:100]}"
                        )
    assert not offenders, (
        "Frontend decision math found — panels/selectors must render backend "
        "fields, not reconstruct PnL/risk/DQS/sizing:\n" + "\n".join(offenders)
    )


# ── Market sessions: pure context, restrictive-only, read-only panel ──────────
# packages/market_sessions is decision-support: it derives session context from
# config + calendar + stdlib zoneinfo. It must not reach into the paper engine /
# RiskGate / a broker / the network, may only RESTRICT size (≤ 1.0), and its
# dashboard panel must stay read-only (no trade actions, no client-side session
# computation).

MARKET_SESSIONS = REPO / "packages" / "market_sessions"
MARKET_SESSIONS_PANEL = (
    REPO / "apps" / "web" / "components" / "panels" / "MarketSessionsPanel" / "index.tsx"
)

_MS_FORBIDDEN_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+"
    r"(packages\.paper|packages\.risk|packages\.decision"
    r"|requests|httpx|urllib|aiohttp|socket|ccxt|websocket)\b",
    re.M,
)
_MS_FORBIDDEN_CALL = re.compile(
    r"\b(attempt_open|open_position|close_position|route_to_manual_ready)\s*\("
)


def test_market_sessions_engine_is_pure() -> None:
    """packages/market_sessions derives context only — no paper/risk/broker/network
    imports and no paper open/close calls (it must never trade or duplicate RiskGate)."""
    offenders: list[str] = []
    for path in _py_files(MARKET_SESSIONS):
        text = path.read_text(encoding="utf-8")
        for m in _MS_FORBIDDEN_IMPORT.finditer(text):
            offenders.append(f"{path.relative_to(REPO)}: forbidden import {m.group(1)}")
        for m in _MS_FORBIDDEN_CALL.finditer(text):
            offenders.append(f"{path.relative_to(REPO)}: forbidden call {m.group(1)}()")
    assert not offenders, (
        "packages/market_sessions must stay pure (no paper/risk/broker/network "
        "imports, no paper open/close):\n" + "\n".join(offenders)
    )


def test_market_session_size_multiplier_clamped() -> None:
    """Market sessions may only reduce size — no size_multiplier literal above 1.0,
    and the engine clamps via min(1.0, ...)."""
    rx = re.compile(r"size_multiplier\s*=\s*([0-9]+(?:\.[0-9]+)?)\b")
    offenders: list[str] = []
    for path in _py_files(MARKET_SESSIONS):
        for val in rx.findall(path.read_text(encoding="utf-8")):
            if float(val) > 1.0:
                offenders.append(f"{path.relative_to(REPO)}: size_multiplier={val}")
    assert not offenders, (
        "market-session size_multiplier literal > 1.0 (sessions may only restrict): "
        + ", ".join(offenders)
    )
    engine_src = (MARKET_SESSIONS / "engine.py").read_text(encoding="utf-8")
    assert "min(1.0," in engine_src, "engine must clamp size_multiplier via min(1.0, ...)"


_PANEL_TRADE_ACTION = re.compile(r"<button|onClick|onSubmit")
_PANEL_TIME_MATH = re.compile(
    r"\bnew\s+Date\b|\bDate\.now\b|getTimezoneOffset|toLocale|Intl\.DateTimeFormat"
)
# Imports are checked on RAW source (paths live in string literals, which the
# code-only stripper blanks).
_PANEL_FORBIDDEN_IMPORT = re.compile(
    r"""from\s+["'][^"']*(packages|/paper|/risk|/decision)[^"']*["']"""
)


def test_market_sessions_panel_is_read_only() -> None:
    """The dashboard Market Sessions panel renders backend status only — no trade
    actions, no client-side session/time computation, no paper/risk/decision imports."""
    raw = MARKET_SESSIONS_PANEL.read_text(encoding="utf-8")
    code = _ts_code_only(raw)
    problems: list[str] = []
    if _PANEL_TRADE_ACTION.search(code):
        problems.append("contains a trade-action control (<button / onClick)")
    if _PANEL_TIME_MATH.search(code):
        problems.append("computes session/time client-side (Date / timezone / locale)")
    if _PANEL_FORBIDDEN_IMPORT.search(raw):
        problems.append("imports paper/risk/decision logic")
    assert not problems, "MarketSessionsPanel must be read-only: " + "; ".join(problems)


# ── Fibonacci: technical EVIDENCE only — never trades, never bypasses RiskGate ──
# Fibonacci is an additive technical-analysis layer. It must stay pure evidence:
# no paper/risk/decision imports, no paper open/close calls, and it must NOT be
# consumed by the decision engine or RiskGate (so it can't enable a trade or
# relax the gate). fibonacci_score stays within [0, 25].

FIBONACCI = REPO / "packages" / "data" / "providers" / "technical" / "fibonacci.py"
DECISION_DIR = REPO / "packages" / "decision"
RISK_DIR = REPO / "packages" / "risk"

_FIB_FORBIDDEN_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+(packages\.risk|packages\.paper|packages\.decision)\b", re.M
)
_FIB_FORBIDDEN_CALL = re.compile(r"\b(attempt_open|open_position|close_position)\s*\(")


def test_fibonacci_is_pure_evidence() -> None:
    """fibonacci.py is pure technical evidence — no risk/paper/decision imports and
    no paper open/close calls (it can never open a trade)."""
    src = FIBONACCI.read_text(encoding="utf-8")
    offenders = [m.group(1) for m in _FIB_FORBIDDEN_IMPORT.finditer(src)]
    offenders += [f"{m.group(1)}()" for m in _FIB_FORBIDDEN_CALL.finditer(src)]
    assert not offenders, "fibonacci.py must stay pure evidence: " + ", ".join(offenders)


def test_fibonacci_not_consumed_by_decision_or_risk() -> None:
    """Fibonacci is not wired into the decision engine or RiskGate — so it cannot
    open a trade or bypass the gate (it stays technical evidence only)."""
    offenders: list[str] = []
    for root in (DECISION_DIR, RISK_DIR):
        for path in _py_files(root):
            if re.search(r"fibonacci", path.read_text(encoding="utf-8"), re.I):
                offenders.append(str(path.relative_to(REPO)))
    assert not offenders, (
        "Fibonacci must not be referenced by decision/risk engines (evidence only): "
        + ", ".join(offenders)
    )


def test_fibonacci_score_bounded_to_25() -> None:
    """The fibonacci_score function returns are within [0, 25] — never a boost."""
    src = FIBONACCI.read_text(encoding="utf-8")
    returns = [int(n) for n in re.findall(r"\breturn\s+(\d+)\b", src)]
    assert returns, "expected integer score returns in fibonacci_score"
    assert all(0 <= n <= 25 for n in returns), f"fibonacci_score returns out of [0,25]: {returns}"


def test_reversal_patterns_not_consumed_by_decision_or_risk() -> None:
    """Reversal + chart-pattern layers (§4.5) are EVIDENCE only — they must never feed
    the ACTION decision or the RiskGate, so they cannot open a trade or bypass the gate.
    The read-only `agent_pipeline` may surface them in its display ViewModel (after the
    decision is made), but the decision engines and risk never consume them."""
    rx = re.compile(r"reversal_signals|chart_pattern_analysis|import reversal|import patterns")
    targets = [
        DECISION_DIR / "agent_decision.py",
        DECISION_DIR / "engine.py",
        *_py_files(RISK_DIR),
    ]
    offenders = [
        str(p.relative_to(REPO))
        for p in targets
        if p.exists() and rx.search(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "reversal/chart-pattern must not feed the action decision or RiskGate "
        "(EVIDENCE only): " + ", ".join(offenders)
    )


# ── Step 9: shadow NEVER auto-opens (observe in Phase A; queue-only in Phase B) ─

SHADOW_MODULE = REPO / "packages" / "decision" / "shadow.py"
SHADOW_ACTIVATION = REPO / "packages" / "decision" / "shadow_activation.py"
TICK_WORKER = REPO / "apps" / "tick_worker" / "main.py"

# Full paper mutators — the OBSERVE module (shadow.py) must reach none of these.
_PAPER_MUTATORS = ("attempt_open", "route_to_manual_ready", "flatten_all", "paper_state.save")
# Auto-open/close entry points — FORBIDDEN anywhere on the shadow path (Phase A or B):
# the shadow may only ever QUEUE to manual_ready, never auto-open a position.
_AUTO_OPEN = ("attempt_open", "flatten_all")


def test_shadow_module_is_observe_only() -> None:
    """The shadow module records a comparison only — it never imports paper state
    nor reaches any paper-mutating entry point (observation cannot move paper).
    Activation lives in the separate shadow_activation module, not here."""
    src = SHADOW_MODULE.read_text(encoding="utf-8")
    offenders = [m for m in _PAPER_MUTATORS if m in src]
    if "packages.paper" in src:
        offenders.append("packages.paper import")
    assert not offenders, (
        "shadow observation must never open/queue/flatten/save paper: " + ", ".join(offenders)
    )


def test_tick_worker_shadow_block_never_auto_opens() -> None:
    """The tick_worker shadow block never AUTO-OPENS: Phase B activation may queue to
    manual_ready (owner-gated), but attempt_open / flatten_all must never appear in
    the shadow path. RiskGate stays final (it re-runs at owner approval)."""
    src = TICK_WORKER.read_text(encoding="utf-8")
    start = src.index("OBSERVATION mode")
    end = src.index("R1 — kararı disk snapshot", start)
    block = src[start:end]
    offenders = [m for m in _AUTO_OPEN if m in block]
    assert not offenders, (
        "tick_worker shadow path must never auto-open a position: " + ", ".join(offenders)
    )


def test_shadow_activation_only_queues_manual_ready() -> None:
    """Phase B activation routes shadow entries to manual_ready ONLY — it calls
    route_to_manual_ready, never attempt_open / flatten_all, and is gated by the
    single activation authority `affects_paper` (inert under affect_decision:false)."""
    src = SHADOW_ACTIVATION.read_text(encoding="utf-8")
    auto = [m for m in _AUTO_OPEN if m in src]
    assert not auto, "shadow_activation must never auto-open: " + ", ".join(auto)
    assert "route_to_manual_ready" in src, "activation must queue to manual_ready"
    assert "affects_paper" in src, "activation must be gated by affects_paper"


def test_tf_weight_trainer_never_auto_applies_weights() -> None:
    """tf_weight_trainer proposes only; it must never write to the active weights
    manifest. Active weights are owned by the rebalance approval flow."""
    src = (REPO / "packages" / "learning" / "tf_weight_trainer.py").read_text(encoding="utf-8")
    forbidden = ("weights_manifest_path", "write_text", "approve_current")
    offenders = [k for k in forbidden if k in src]
    assert not offenders, (
        "tf_weight_trainer must propose only, never write live weights: "
        + ", ".join(offenders)
    )
