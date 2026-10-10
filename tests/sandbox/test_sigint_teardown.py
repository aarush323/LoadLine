"""SIGINT must invoke production run cleanup."""

from __future__ import annotations

import signal
import uuid

import pytest

from loadline.adapters.runtime.compose_boot import labeled_objects_remaining
from loadline.adapters.runtime.docker_runner import docker_cmd, probe_image
from loadline.adapters.runtime.run_cleanup import (
    RunCleanupState,
    handle_sigint,
    register_run_cleanup,
    teardown_run,
    unregister_run_cleanup,
)


@pytest.mark.integration
def test_sigint_handler_clears_labelled_container():
    run_id = uuid.uuid4().hex[:12]
    proc = docker_cmd(
        [
            "run",
            "-d",
            "--label",
            f"loadline.run={run_id}",
            probe_image(),
            "sleep",
            "120",
        ],
        timeout=60,
    )
    assert proc.returncode == 0
    assert labeled_objects_remaining(run_id) >= 1
    register_run_cleanup(RunCleanupState(run_id=run_id))
    try:
        try:
            handle_sigint(signal.SIGINT, None)
        except KeyboardInterrupt:
            pass
    finally:
        unregister_run_cleanup()
    assert labeled_objects_remaining(run_id) == 0


@pytest.mark.integration
def test_teardown_run_without_extra():
    run_id = uuid.uuid4().hex[:12]
    net = f"loadline_net_{run_id}"
    assert create_net(net, run_id) is None
    proc = docker_cmd(
        [
            "run",
            "-d",
            "--network",
            net,
            "--label",
            f"loadline.run={run_id}",
            probe_image(),
            "sleep",
            "60",
        ],
        timeout=60,
    )
    assert proc.returncode == 0
    teardown_run(RunCleanupState(run_id=run_id))
    assert labeled_objects_remaining(run_id) == 0


def create_net(name: str, run_id: str):
    from loadline.adapters.runtime.docker_runner import create_internal_network

    return create_internal_network(name, run_id=run_id)
