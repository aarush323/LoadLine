"""Merge a compose file with its conventional override, using Docker's own config."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from loadline.discovery.intake import load_compose

_OVERRIDE_NAMES = {
    "compose.yaml": "compose.override.yaml",
    "compose.yml": "compose.override.yml",
    "docker-compose.yaml": "docker-compose.override.yaml",
    "docker-compose.yml": "docker-compose.override.yml",
}


def override_sibling(compose_path: Path) -> Path | None:
    name = _OVERRIDE_NAMES.get(compose_path.name)
    if not name:
        return None
    candidate = compose_path.with_name(name)
    return candidate if candidate.is_file() else None


def merge_argv(repo: Path, compose_path: Path, override: Path) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-directory",
        str(repo),
        "-f",
        str(compose_path),
        "-f",
        str(override),
        "config",
        "--format",
        "json",
    ]


def load_project_compose(repo: Path, compose_path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Load one compose file, or the Docker-merged project when an override sibling exists."""
    override = override_sibling(compose_path)
    if override is None:
        try:
            return load_compose(compose_path), None
        except (OSError, ValueError) as exc:
            return None, str(exc)
    proc = subprocess.run(
        merge_argv(repo, compose_path, override),
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "docker compose config failed").strip()
        return None, detail[:2000]
    try:
        data = json.loads(proc.stdout or "")
    except json.JSONDecodeError:
        return None, "docker compose config returned invalid JSON"
    if not isinstance(data, dict):
        return None, "docker compose config returned a non-object"
    return data, None
