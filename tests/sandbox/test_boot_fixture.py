"""Integration: real compose boot on internal network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from loadline.adapters.runtime.compose_boot import boot_repository, labeled_objects_remaining
from loadline.boot import analyze_boot_json
from loadline.paths import allocate_run_dir, loadline_home

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "fx-pyhttp-pg"


@pytest.fixture
def loadline_home_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path / "loadline"))
    yield tmp_path / "loadline"


@pytest.mark.integration
def test_run_dir_not_inside_target_repo(loadline_home_tmp):
    repo = FIXTURE.resolve()
    runs_inside = repo / "runs"
    runs_inside.mkdir(exist_ok=True)
    rid, run_dir = allocate_run_dir(repo)
    assert run_dir.is_relative_to(loadline_home())
    assert not str(run_dir).startswith(str(runs_inside))


@pytest.mark.integration
def test_fixture_boot_teardown_clean(loadline_home_tmp):
    outcome = boot_repository(FIXTURE, teardown=True, require_auth=False)
    assert outcome.status == "booted"
    assert outcome.launch_plan is not None
    assert outcome.boot is not None
    assert outcome.boot["health"]["status"] == "ok"
    assert outcome.run_id is not None
    assert labeled_objects_remaining(outcome.run_id) == 0
    serialized = json.dumps(outcome.launch_plan)
    assert "postgresql://app:app@" not in serialized
    assert "[redacted]" in serialized or "POSTGRES_PASSWORD" in serialized
    validated = Path(outcome.boot["run_dir"]) / "launch_plan.validated.yaml"
    assert validated.is_file()
    validated_text = validated.read_text()
    assert "postgresql://app:app@" not in validated_text
    assert "[redacted]" in validated_text
    assert not (Path(outcome.boot["run_dir"]) / "compose.runtime.yaml").exists()


@pytest.mark.integration
def test_probe_reaches_app_on_internal_network(loadline_home_tmp):
    outcome = boot_repository(FIXTURE, teardown=True, require_auth=False)
    assert outcome.status == "booted"
    health = outcome.boot["health"]
    assert health["url"].startswith("http://web:")


@pytest.mark.integration
def test_analyze_boot_json_shape(loadline_home_tmp):
    doc, code = analyze_boot_json(FIXTURE, require_auth=False, teardown=True)
    assert code == 0
    assert doc["status"] == "booted"
    assert doc["config_schema"] == "loadline-hints/1"
    assert doc["capabilities"] is not None
    assert doc["launch_plan"] is not None
    assert doc["boot"] is not None
    assert doc["blocker"] is None
    for key in ("status", "blocker", "attempts", "config_schema", "capabilities", "launch_plan", "boot"):
        assert key in doc


@pytest.mark.integration
def test_concurrent_runs_use_distinct_networks(loadline_home_tmp):
    a = boot_repository(FIXTURE, teardown=True, require_auth=False)
    b = boot_repository(FIXTURE, teardown=True, require_auth=False)
    assert a.status == "booted" and b.status == "booted"
    assert a.boot["network"] != b.boot["network"]
