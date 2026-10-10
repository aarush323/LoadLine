"""Run directory placement (tech_doc.md §7.2)."""

from __future__ import annotations

import os
from pathlib import Path

from loadline.adapters.runtime.docker_runner import run_id


def loadline_home() -> Path:
    raw = os.environ.get("LOADLINE_HOME", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.home() / ".local" / "share" / "loadline"


def new_run_dir() -> tuple[str, Path]:
    rid = run_id()
    path = loadline_home() / "runs" / rid
    path.mkdir(parents=True, exist_ok=True)
    return rid, path


def assert_not_target_runs_folder(repo: Path, run_dir: Path) -> None:
    """A target path named runs is not Loadline state."""
    if repo.resolve().name == "runs" and run_dir.resolve() == repo.resolve():
        raise ValueError("run directory must not be the target's runs folder")
