"""Plain and Rich stderr rendering."""

from __future__ import annotations

import os
import sys
from typing import TextIO


def use_color(explicit_no_color: bool) -> bool:
    if explicit_no_color or os.environ.get("NO_COLOR"):
        return False
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()


def emit(line: str, stream: TextIO, *, use_ansi: bool, style: str | None = None) -> None:
    if use_ansi and style:
        try:
            from rich.console import Console

            Console(file=stream, highlight=False).print(line, style=style)
            return
        except ImportError:
            pass
    print(line, file=stream)
