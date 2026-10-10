"""Plain and Rich stderr rendering."""

from __future__ import annotations

import os
import sys
from typing import TextIO


def use_color(explicit_no_color: bool) -> bool:
    if explicit_no_color or os.environ.get("NO_COLOR"):
        return False
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()


def is_tty(stream: TextIO) -> bool:
    try:
        return hasattr(stream, "isatty") and stream.isatty()
    except Exception:
        return False


_STYLE_MAP = {
    "dim": "dim",
    "brand": "bold #B96648",
    "rust": "#B96648",
    "coral": "bold #C84738",
    "pressure": "bold #C84738",
    "violet": "#8872B5",
    "hypothesis": "#8872B5",
    "healthy": "#38785F",
}


def emit(line: str, stream: TextIO, *, use_ansi: bool, style: str | None = None) -> None:
    if use_ansi and style:
        try:
            from rich.console import Console

            Console(file=stream, highlight=False).print(line, style=_STYLE_MAP.get(style, style))
            return
        except Exception:
            pass
    print(line, file=stream)
