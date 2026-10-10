"""Install destination paths for loadline-run skill."""

from __future__ import annotations

from pathlib import Path

from loadline.skills.bundle import SKILL_FILENAME, SKILL_NAME

HOST_AGENTS = "agents"
HOST_CLAUDE = "claude"


def user_home(home: Path | None = None) -> Path:
    return (home or Path.home()).expanduser().resolve()


def agents_skill_file(home: Path | None = None) -> Path:
    return user_home(home) / ".agents" / "skills" / SKILL_NAME / SKILL_FILENAME


def claude_skill_file(home: Path | None = None) -> Path:
    return user_home(home) / ".claude" / "skills" / SKILL_NAME / SKILL_FILENAME


def dest_skill_file(dest_root: Path) -> Path:
    """Install under DEST/loadline-run/SKILL.md (dest_root is the skills parent dir)."""
    return dest_root.expanduser().resolve() / SKILL_NAME / SKILL_FILENAME


def install_targets(
    *,
    home: Path | None = None,
    host_all: bool = False,
    dest_root: Path | None = None,
) -> list[tuple[str, Path]]:
    if dest_root is not None:
        return [(HOST_AGENTS, dest_skill_file(dest_root))]
    targets: list[tuple[str, Path]] = [(HOST_AGENTS, agents_skill_file(home))]
    if host_all:
        targets.append((HOST_CLAUDE, claude_skill_file(home)))
    return targets
