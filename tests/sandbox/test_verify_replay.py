"""Replay the same k6 input after a test-only patch. No model."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from loadline.adapters.runtime.boot_teardown import teardown_boot_outcome
from loadline.adapters.runtime.compose_boot import boot_repository
from loadline.core.ledger import Ledger
from loadline.investigator.deps import InvestigationDeps
from loadline.investigator.k6_tool import run_k6
from loadline.verification import judge_replay, metrics_from_experiment

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "fx-blocking-handler"
FIXED = Path(__file__).resolve().parent / "blocking_handler_fixed_app.py"
ENDPOINTS = [
    {"id": "items", "method": "GET", "path": "/api/items"},
    {"id": "health", "method": "GET", "path": "/health"},
]
RATE = 10
DURATION_S = 15


def _deps(repo: Path, boot) -> InvestigationDeps:
    run_dir = Path(boot.boot["run_dir"])
    return InvestigationDeps(
        repo_root=repo,
        run_dir=run_dir,
        run_id=boot.run_id,
        ledger=Ledger.open(run_dir, boot.run_id),
        graph=None,
        boot=boot.boot,
        allowed_hosts=frozenset(s["name"] for s in boot.boot["services"]),
        network=boot.boot["network"],
    )


def _op(experiment: dict, op_id: str) -> dict:
    return metrics_from_experiment(experiment, op_id)


@pytest.mark.integration
def test_same_k6_input_improves_after_handler_patch(tmp_path, monkeypatch):
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path / "loadline"))
    repo = tmp_path / "app"
    shutil.copytree(FIXTURE, repo)
    first = boot_repository(repo, teardown=False, require_auth=False)
    assert first.status == "booted", first.blocker
    second = None
    try:
        before_out = run_k6(_deps(repo, first), ENDPOINTS, RATE, DURATION_S)
        assert "error" not in before_out, before_out
        before_path = Path(first.boot["run_dir"]) / "experiments" / f"{before_out['experiment_id']}.json"
        before = json.loads(before_path.read_text(encoding="utf-8"))
        assert before["input"]["endpoints"] == ENDPOINTS
        assert before["input"]["rate"] == RATE
        assert before["input"]["duration_s"] == DURATION_S
    finally:
        teardown_boot_outcome(first, repo)

    shutil.copyfile(FIXED, repo / "app.py")
    second = boot_repository(repo, teardown=False, require_auth=False)
    assert second.status == "booted", second.blocker
    try:
        after_out = run_k6(_deps(repo, second), ENDPOINTS, RATE, DURATION_S)
        assert "error" not in after_out, after_out
        after_path = Path(second.boot["run_dir"]) / "experiments" / f"{after_out['experiment_id']}.json"
        after = json.loads(after_path.read_text(encoding="utf-8"))
        assert after["input"]["endpoints"] == before["input"]["endpoints"]
        assert after["input"]["rate"] == before["input"]["rate"]
        assert after["input"]["duration_s"] == before["input"]["duration_s"]
        cited_before = _op(before, "items")
        cited_after = _op(after, "items")
        control_before = _op(before, "health")
        control_after = _op(after, "health")
        assert cited_before["p95_ms"] is not None
        assert cited_after["p95_ms"] is not None
        verdict = judge_replay(
            metric="p95_ms",
            cited_before=cited_before,
            cited_after=cited_after,
            control_before=control_before,
            control_after=control_after,
        )
        assert verdict == "improved", {
            "verdict": verdict,
            "items_before": cited_before,
            "items_after": cited_after,
            "health_before": control_before,
            "health_after": control_after,
        }
    finally:
        teardown_boot_outcome(second, repo)
