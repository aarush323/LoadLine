"""Unit tests for SIGINT teardown re-entrancy."""

from __future__ import annotations

import signal

import pytest

from loadline.adapters.runtime.run_cleanup import RunCleanupState, handle_sigint, teardown_run


def test_teardown_run_ignores_nested_call() -> None:
    calls: list[str] = []
    state = RunCleanupState(run_id="r")

    def extra() -> None:
        calls.append("extra")
        teardown_run(state)

    state.extra = extra
    teardown_run(state)
    assert calls == ["extra"]


def test_sigint_during_teardown_does_not_reenter_extra() -> None:
    calls: list[str] = []

    def extra() -> None:
        calls.append("extra")
        with pytest.raises(KeyboardInterrupt):
            handle_sigint(signal.SIGINT, None)

    teardown_run(RunCleanupState(run_id="r", extra=extra))
    assert calls == ["extra"]
