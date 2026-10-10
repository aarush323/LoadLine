"""SIGINT and run teardown (tech_doc.md §7.8)."""

from __future__ import annotations

import signal
from dataclasses import dataclass
from typing import Callable

from loadline.adapters.runtime.docker_runner import docker_cmd, remove_labeled

TeardownFn = Callable[[], None]


@dataclass
class RunCleanupState:
    run_id: str
    extra: TeardownFn | None = None


_state: RunCleanupState | None = None
_previous_handler: object | None = None
_teardown_in_progress: bool = False


def teardown_run(state: RunCleanupState) -> None:
    global _teardown_in_progress
    if _teardown_in_progress:
        return
    _teardown_in_progress = True
    try:
        if state.extra:
            state.extra()
        else:
            remove_labeled(state.run_id)
            docker_cmd(["network", "rm", f"loadline_net_{state.run_id}"], timeout=60)
    finally:
        _teardown_in_progress = False


def handle_sigint(signum: int, frame: object | None) -> None:
    """Production SIGINT handler; registered during an active boot."""
    if _teardown_in_progress:
        raise KeyboardInterrupt
    if _state is not None:
        teardown_run(_state)
    raise KeyboardInterrupt


def register_run_cleanup(state: RunCleanupState) -> None:
    global _state, _previous_handler
    _state = state
    _previous_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, handle_sigint)


def unregister_run_cleanup() -> None:
    global _state, _previous_handler
    if _previous_handler is not None:
        signal.signal(signal.SIGINT, _previous_handler)
    _state = None
    _previous_handler = None

