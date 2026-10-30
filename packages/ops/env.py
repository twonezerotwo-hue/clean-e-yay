"""Process-wide environment bootstrap shared by API and workers.

The API historically loaded ``.env`` while the tick and learning workers did
not.  That made the same repository produce different snapshots depending on
which process served the request (notably missing FRED/news credentials).  The
loader is deliberately small and additive: shell variables always win, the
file is optional, and malformed lines are ignored.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def load_repo_dotenv(*, skip_pytest: bool = False, path: Path | None = None) -> bool:
    """Load the repository ``.env`` once for the current process.

    Returns ``True`` when the file was read.  Existing environment variables
    are never overwritten.  ``skip_pytest`` preserves the API test isolation
    contract; callers that need the historical LLM behaviour can leave it
    false.
    """
    if skip_pytest and "pytest" in sys.modules:
        return False
    env_path = path or (Path(__file__).resolve().parents[2] / ".env")
    if not env_path.exists():
        return False
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
    return True
