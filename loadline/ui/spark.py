"""Tiny terminal formatters (presentation only, no I/O)."""

from __future__ import annotations

from typing import Any

_FILLED = "▓"
_EMPTY = "░"


def vu_bar(used: Any, ceiling: Any, width: int = 10) -> str:
    """Render a VU pressure bar from measured values only.

    Returns "" when either side is missing so callers can print
    "Not measured" instead of inventing a value.
    """
    try:
        u = float(used) if used is not None else None
        c = float(ceiling) if ceiling is not None else None
    except (TypeError, ValueError):
        return ""
    if u is None or c is None or c <= 0 or width <= 0:
        return ""
    frac = max(0.0, min(1.0, u / c))
    filled = int(round(frac * width))
    return _FILLED * filled + _EMPTY * (width - filled)


def fmt_ms(value: Any) -> str:
    try:
        return f"{int(round(float(value)))}ms"
    except (TypeError, ValueError):
        return "?"


def fmt_int(value: Any) -> str:
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return "?"
