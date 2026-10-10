"""Canonical loadline-run skill file (repo + wheel bundle)."""

from __future__ import annotations

import hashlib
from pathlib import Path

SKILL_NAME = "loadline-run"
SKILL_FILENAME = "SKILL.md"


def _module_dir() -> Path:
    return Path(__file__).resolve().parent


def canonical_skill_path() -> Path:
    bundled = _module_dir() / "bundled" / SKILL_NAME / SKILL_FILENAME
    if bundled.is_file():
        return bundled
    repo_root = _module_dir().parents[1]
    return repo_root / "skills" / SKILL_NAME / SKILL_FILENAME


def read_canonical_skill() -> str:
    path = canonical_skill_path()
    if not path.is_file():
        raise FileNotFoundError(f"skill file missing: {path}")
    return path.read_text(encoding="utf-8")


def skill_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
