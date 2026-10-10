"""Loadline state paths (never inside the target repository)."""

from __future__ import annotations

import os
from pathlib import Path

from loadline.adapters.runtime.docker_runner import run_id


def loadline_home() -> Path:
    raw = os.environ.get("LOADLINE_HOME", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".local/share/loadline").resolve()


def allocate_run_dir(_repo: Path) -> tuple[str, Path]:
    """Return (run_id, run_dir). Ignores a target folder named `runs`."""
    rid = run_id()
    run_dir = loadline_home() / "runs" / rid
    run_dir.mkdir(parents=True, exist_ok=True)
    return rid, run_dir
