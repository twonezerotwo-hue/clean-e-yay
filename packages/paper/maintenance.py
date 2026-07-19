"""Phase 2e — owner-admin paper maintenance: archive / repair / reset.

Safe, non-destructive tools for the *paper* account state file. These operate on
paper state only — they never open, close, resize, or trigger a trade, never call a
broker or live network, never invent market prices, and never bypass RiskGate
(there is no trade decision here at all). Every mutation archives first.

PAPER_SAFE / NO_EXECUTION. Repair fixes only deterministic, unambiguous accounting
impossibilities; anything that would require inventing data is reported as a warning
and left untouched.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from packages.paper import state as paper_state
from packages.paper.state import PaperState

_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class MaintenanceResult:
    """Structured, replay-friendly outcome of a maintenance operation."""

    status: str            # "ok" | "no_op" | "error"
    action: str            # "archive" | "repair" | "reset"
    dry_run: bool
    reason: str
    created_at: str
    changed: bool = False
    archive_path: str | None = None
    changes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    paper_safe: bool = True
    no_execution: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


# ── paths / helpers ──────────────────────────────────────────────────────────


def _archive_dir() -> Path:
    """Archive directory. Defaults next to the active state file so tests that
    redirect STATE_PATH are auto-isolated; overridable via PAPER_ARCHIVE_DIR."""
    override = os.environ.get("PAPER_ARCHIVE_DIR")
    if override:
        return Path(override)
    return paper_state.STATE_PATH.parent / "paper_archives"


def _slug(reason: str) -> str:
    s = _SLUG_RE.sub("-", (reason or "").lower()).strip("-")
    return (s or "manual")[:48]


def _archive_name(reason: str) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S_%f")
    return f"paper_state_{ts}_{_slug(reason)}.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _now() -> str:
    return paper_state.utc_iso()


# ── archive ──────────────────────────────────────────────────────────────────


def archive_state(reason: str) -> MaintenanceResult:
    """Copy the current paper state to a timestamped archive. Never mutates state.

    Copies raw bytes when a state file exists (faithful forensic snapshot, even if
    the file is corrupt); if none exists yet, archives a serialized default snapshot
    and warns. Archive path: <state_dir>/paper_archives/paper_state_<ts>_<slug>.json
    """
    warnings: list[str] = []
    errors: list[str] = []
    src = paper_state.STATE_PATH
    dest = _archive_dir() / _archive_name(reason)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(src, dest)  # raw copy — does not touch current state
        else:
            warnings.append("no_state_file:archived_default_snapshot")
            _write_json(dest, paper_state._initial_state().to_dict())
    except OSError as exc:
        errors.append(f"archive_failed:{type(exc).__name__}")
        return MaintenanceResult(
            status="error", action="archive", dry_run=False, reason=reason,
            created_at=_now(), changed=False, archive_path=None,
            warnings=warnings, errors=errors,
        )
    return MaintenanceResult(
        status="ok", action="archive", dry_run=False, reason=reason,
        created_at=_now(), changed=False, archive_path=str(dest),
        warnings=warnings, errors=errors,
    )


# ── repair ───────────────────────────────────────────────────────────────────


def _load_raw_state() -> tuple[PaperState | None, list[str]]:
    """Read state for inspection WITHOUT triggering state.load()'s repair/rewrite
    side effect (so dry-run stays read-only). Returns (state|None, warnings)."""
    warnings: list[str] = []
    path = paper_state.STATE_PATH
    if not path.exists():
        warnings.append("no_state_file")
        return None, warnings
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return PaperState.from_dict(raw), warnings
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        warnings.append(f"unreadable_state:{type(exc).__name__}")
        return None, warnings


def _detect(st: PaperState) -> tuple[list[str], list[str]]:
    """Return (changes, warnings). `changes` are safe deterministic repairs;
    `warnings` are impossible values we refuse to "fix" (would invent data)."""
    changes: list[str] = []
    warnings: list[str] = []

    # Detect-only — non-finite accounting fields (cannot correct without inventing).
    for name, val in (
        ("equity_usd", st.equity_usd),
        ("peak_equity_usd", st.peak_equity_usd),
        ("realized_pnl_usd", st.realized_pnl_usd),
        ("daily_pnl_usd", st.daily_pnl_usd),
    ):
        if not math.isfinite(val):
            warnings.append(f"non_finite_field:{name}")

    # Detect-only — malformed positions (do NOT close/repair; no invented prices).
    for p in st.open_positions:
        if not math.isfinite(p.entry_price) or p.entry_price <= 0:
            warnings.append(f"position:{p.id}:non_positive_entry_price")
        if p.side not in ("long", "short"):
            warnings.append(f"position:{p.id}:invalid_side:{p.side}")

    # Repairable — peak equity must be >= current equity (drawdown invariant).
    if (
        math.isfinite(st.equity_usd)
        and math.isfinite(st.peak_equity_usd)
        and st.peak_equity_usd < st.equity_usd
    ):
        changes.append(f"peak_equity_usd:{st.peak_equity_usd}->{st.equity_usd}")

    # Repairable — negative position size is impossible; neutralize to 0 (keep
    # the position open: closing is never automatic).
    for p in st.open_positions:
        if math.isfinite(p.size_usd) and p.size_usd < 0:
            changes.append(f"position:{p.id}:size_usd:{p.size_usd}->0.0")

    return changes, warnings


def _apply(st: PaperState) -> None:
    """Apply the deterministic repairs detected by _detect (mutates `st`)."""
    if (
        math.isfinite(st.equity_usd)
        and math.isfinite(st.peak_equity_usd)
        and st.peak_equity_usd < st.equity_usd
    ):
        st.peak_equity_usd = st.equity_usd
    for p in st.open_positions:
        if math.isfinite(p.size_usd) and p.size_usd < 0:
            p.size_usd = 0.0


def repair_state(dry_run: bool = True) -> MaintenanceResult:
    """Detect + (optionally) fix deterministic paper-state inconsistencies.

    dry_run=True  → report planned changes, write nothing.
    dry_run=False → if there are changes, archive first, then apply and save.
    Missing/corrupt state is handled safely (no crash, no write, no_op).
    """
    st, warnings = _load_raw_state()
    if st is None:
        return MaintenanceResult(
            status="no_op", action="repair", dry_run=dry_run, reason="repair",
            created_at=_now(), changed=False, archive_path=None,
            warnings=warnings, errors=[],
        )

    changes, detect_warnings = _detect(st)
    warnings.extend(detect_warnings)
    archive_path: str | None = None

    if changes and not dry_run:
        arch = archive_state(reason="pre_repair")  # archive BEFORE writing
        archive_path = arch.archive_path
        warnings.extend(arch.warnings)
        if arch.status == "error":
            return MaintenanceResult(
                status="error", action="repair", dry_run=dry_run, reason="repair",
                created_at=_now(), changed=False, archive_path=None,
                changes=changes, warnings=warnings, errors=arch.errors,
            )
        # T3 — yazım tek kilit altında ve TAZE state üstünde: ilk tespit ile yazım
        # arasında başka bir süreç defteri değiştirmiş olabilir; kilit içinde
        # yeniden tespit edip onu uygularız (rapor da yazım anının gerçeğidir).
        with paper_state.transaction("maintenance:repair") as fresh_st:
            changes, redetect_warnings = _detect(fresh_st)
            warnings.extend(redetect_warnings)
            _apply(fresh_st)

    return MaintenanceResult(
        status="ok" if changes else "no_op", action="repair", dry_run=dry_run,
        reason="repair", created_at=_now(), changed=bool(changes),
        archive_path=archive_path, changes=changes, warnings=warnings, errors=[],
    )


# ── reset ────────────────────────────────────────────────────────────────────


def reset_state(reason: str, preserve_learning: bool = True) -> MaintenanceResult:
    """Archive current paper state, then reset the paper account to a clean initial
    state. Learning + decision logs live in separate files and are NEVER deleted
    here (preserved by default; an explicit purge is out of scope for this tool).
    """
    warnings: list[str] = []
    arch = archive_state(reason=f"pre_reset_{reason}")
    if arch.status == "error":
        return MaintenanceResult(
            status="error", action="reset", dry_run=False, reason=reason,
            created_at=_now(), changed=False, archive_path=None,
            warnings=arch.warnings, errors=arch.errors,
        )
    warnings.extend(arch.warnings)

    # T3 — sıfırlama da kilit altında (revision monoton devam eder; eşzamanlı
    # tick yazımıyla yarışıp yarım devir bırakmaz).
    txn = paper_state.begin("maintenance:reset")
    try:
        txn.state = paper_state._initial_state()
        txn.commit()
    finally:
        txn.abort()

    if preserve_learning:
        warnings.append("learning_and_decision_logs_preserved")
    else:
        # We still never delete the decision log / learning artifacts here.
        warnings.append("learning_reset_not_performed:decision_log_retained")

    return MaintenanceResult(
        status="ok", action="reset", dry_run=False, reason=reason,
        created_at=_now(), changed=True, archive_path=arch.archive_path,
        changes=["paper_state->initial"], warnings=warnings, errors=[],
    )


__all__ = ["MaintenanceResult", "archive_state", "repair_state", "reset_state"]
