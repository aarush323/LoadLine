"""Classy run banner (presentation only, stderr, TTY-gated)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

SIGNAL = "─────╱╲────●"
SUB = "capacity with evidence"
RULE = "─" * 51


def fancy_ok(*, no_color: bool, json_mode: bool, quiet: bool) -> bool:
    """Banner is a TTY-only flourish; CI / --json / --quiet stay plain."""
    if json_mode or quiet or no_color:
        return False
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
    except Exception:
        return False


def banner_rows(
    *,
    run_id: str | None,
    repo: Path | str,
    run_dir: Path | str | None,
) -> list[tuple[str, str | None]]:
    """(text, style) rows. Keeps run_id=/repo=/artifacts: greppable."""
    rid = run_id or "pending"
    rows: list[tuple[str, str | None]] = [
        (f"loadline  {SIGNAL}", "brand"),
        (SUB, "dim"),
        (RULE, "dim"),
        (f"run_id={rid}  repo={repo}", "dim"),
    ]
    if run_dir:
        rows.append((f"artifacts: {run_dir}", "dim"))
    return rows
