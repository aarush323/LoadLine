"""Teardown helpers for boot outcomes left running (e.g. load tests)."""

from __future__ import annotations

from pathlib import Path

from loadline.adapters.runtime.compose_boot import BootOutcome, _teardown


def teardown_boot_outcome(outcome: BootOutcome, repo: Path) -> None:
    if not outcome.boot or not outcome.run_id:
        return
    run_dir = Path(outcome.boot["run_dir"])
    compose = run_dir / "compose.runtime.yaml"
    if not compose.is_file():
        compose = run_dir / "launch_plan.validated.yaml"
    project = f"loadline_{outcome.run_id}"
    _teardown(project, compose, repo.resolve(), outcome.run_id)
