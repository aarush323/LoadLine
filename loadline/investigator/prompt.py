"""Load investigator prompt (agents/investigator_prompt.md)."""

from __future__ import annotations

from pathlib import Path


def load_investigator_prompt(repo_root: Path) -> str:
    path = repo_root / "agents" / "investigator_prompt.md"
    return path.read_text(encoding="utf-8")
