#!/usr/bin/env python3
"""Contract-first codegen — OpenAPI is the single source of truth.

Generates canonical TypeScript contract types for `apps/web` from
`contracts/openapi.yaml` using the pinned `openapi-typescript` (in
`apps/web/node_modules`). The generated file is marked DO-NOT-EDIT.

Usage:
    python scripts/codegen.py            # write generated files
    python scripts/codegen.py --check    # fail (exit 1) if generated files are stale

Why no Pydantic yet: the backend hand-writes its response models and does not
import generated ones, so per "generate Python models *if used by backend*" we
defer Pydantic emission until a package actually consumes it. See
docs/MIGRATION_MAP_EYAY_CODEX_TO_CLEAN.md.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OPENAPI = REPO / "contracts" / "openapi.yaml"
WEB = REPO / "apps" / "web"
TS_OUT = WEB / "types" / "generated" / "schema.ts"
OPENAPI_TS_BIN = WEB / "node_modules" / ".bin" / "openapi-typescript"
# Invoke the package's JS entry via `node` directly so codegen works on every OS:
# the bare `.bin/openapi-typescript` shim is a unix shell script (not a valid
# Windows executable → WinError 193). `node cli.js` is platform-agnostic.
OPENAPI_TS_CLI = WEB / "node_modules" / "openapi-typescript" / "bin" / "cli.js"


def _node_env() -> dict[str, str]:
    """PATH that contains a `node` binary (CI default, or user-local fallback)."""
    env = dict(os.environ)
    if shutil.which("node") is None:
        local = Path.home() / ".local" / "node" / "bin"
        if (local / "node").exists():
            env["PATH"] = f"{local}{os.pathsep}{env.get('PATH', '')}"
    return env


def _ensure_tools() -> None:
    if not OPENAPI.exists():
        sys.exit(f"[codegen] missing contract: {OPENAPI}")
    if not OPENAPI_TS_CLI.exists():
        sys.exit(
            "[codegen] openapi-typescript not installed. Run:\n"
            "    cd apps/web && pnpm install"
        )
    env = _node_env()
    if shutil.which("node", path=env.get("PATH")) is None:
        sys.exit("[codegen] node not found on PATH (need Node 20+).")


def _run_openapi_ts(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    env = _node_env()
    node = shutil.which("node", path=env.get("PATH")) or "node"
    res = subprocess.run(
        [node, str(OPENAPI_TS_CLI), str(OPENAPI), "-o", str(out_path)],
        cwd=str(WEB),
        env=env,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        sys.exit(f"[codegen] openapi-typescript failed:\n{res.stderr or res.stdout}")


def generate() -> None:
    _ensure_tools()
    _run_openapi_ts(TS_OUT)
    rel = TS_OUT.relative_to(REPO)
    print(f"[codegen] wrote {rel} ({TS_OUT.stat().st_size} bytes)")
    print("[codegen] done — TypeScript contract types regenerated from openapi.yaml")


def check() -> int:
    """Regenerate into a temp file; fail if it differs from the committed file."""
    _ensure_tools()
    if not TS_OUT.exists():
        print(f"[codegen --check] FAIL: {TS_OUT.relative_to(REPO)} does not exist; run `make codegen`")
        return 1
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "schema.ts"
        _run_openapi_ts(tmp)
        fresh = tmp.read_text(encoding="utf-8")
    committed = TS_OUT.read_text(encoding="utf-8")
    # Compare line-ending-insensitively so a CRLF working-tree checkout (Windows)
    # is not flagged as drift against the LF the generator emits.
    if fresh.replace("\r\n", "\n") != committed.replace("\r\n", "\n"):
        print(
            f"[codegen --check] FAIL: {TS_OUT.relative_to(REPO)} is out of sync with "
            "contracts/openapi.yaml. Run `make codegen` and commit the result."
        )
        return 1
    print("[codegen --check] OK — generated types match contracts/openapi.yaml")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="OpenAPI → TypeScript contract codegen")
    ap.add_argument("--check", action="store_true", help="fail if generated files are stale")
    args = ap.parse_args()
    if args.check:
        return check()
    generate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
