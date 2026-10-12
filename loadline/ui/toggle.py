"""Arrow-key two-option picker (presentation only)."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from typing import TextIO

KeyReader = Callable[[], str]


def read_key(stream: TextIO | None = None) -> str:
    """Read one key, including ANSI arrow sequences."""
    src = stream if stream is not None else sys.stdin
    ch = src.read(1)
    if not ch:
        return ""
    if ch == "\x1b":
        nxt = src.read(1)
        if nxt == "[":
            return "\x1b[" + (src.read(1) or "")
        return "\x1b" + (nxt or "")
    return ch


def _highlight(options: list[str], index: int) -> str:
    parts: list[str] = []
    for i, label in enumerate(options):
        if i == index:
            parts.append(f"> {label} <")
        else:
            parts.append(f"  {label}  ")
    return "   ".join(parts)


def apply_toggle_key(index: int, n: int, key: str) -> tuple[int, str | None]:
    """Return (index, action) where action is confirm, abort, or None (keep looping)."""
    if key in ("\r", "\n"):
        return index, "confirm"
    if key in ("q", "Q", "\x03"):
        return index, "abort"
    if n <= 0:
        return 0, None
    if key in ("\x1b[C", "\x1b[B", "l", "j"):
        return (index + 1) % n, None
    if key in ("\x1b[D", "\x1b[A", "h", "k"):
        return (index - 1) % n, None
    return index, None


def toggle_choice(
    question: str,
    options: list[str],
    *,
    default: int = 0,
    reader: KeyReader | Iterator[str] | None = None,
    writer: TextIO | None = None,
    keys: list[str] | None = None,
) -> int | None:
    """Highlight one option. Enter confirms, q aborts. Returns index or None."""
    if not options:
        return None
    index = max(0, min(default, len(options) - 1))
    out = writer if writer is not None else sys.stderr

    sequence: Iterator[str]
    if keys is not None:
        sequence = iter(keys)
    elif reader is None:
        sequence = _live_keys()
    elif callable(reader):
        def _call() -> Iterator[str]:
            while True:
                yielded = reader()
                if yielded == "":
                    return
                yield yielded

        sequence = _call()
    else:
        sequence = reader

    def paint(first: bool = False) -> None:
        line = f"{question}\n  {_highlight(options, index)}"
        if first:
            print(line, file=out, end="", flush=True)
        else:
            print(f"\r\033[1A\033[J{line}", file=out, end="", flush=True)

    paint(first=True)
    try:
        for key in sequence:
            index, action = apply_toggle_key(index, len(options), key)
            if action == "confirm":
                print(file=out)
                return index
            if action == "abort":
                print(file=out)
                return None
            paint()
    except KeyboardInterrupt:
        print(file=out)
        return None
    print(file=out)
    return None


def _live_keys() -> Iterator[str]:
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            key = read_key(sys.stdin)
            if not key:
                return
            yield key
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
