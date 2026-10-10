from pathlib import Path

import pytest

from loadline.adapters.runtime.compose_boot import boot_repository, labeled_objects_remaining

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "fx-docker-http"


@pytest.fixture
def loadline_home_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path / "loadline"))
    yield tmp_path / "loadline"


@pytest.mark.integration
def test_dockerfile_only_fixture_boots(loadline_home_tmp):
    outcome = boot_repository(FIXTURE, teardown=True, require_auth=False)
    assert outcome.status == "booted"
    assert outcome.run_id is not None
    assert labeled_objects_remaining(outcome.run_id) == 0
