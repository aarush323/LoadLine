"""End-to-end pipeline on a fixture (boot → calibrate → baseline → report; no model)."""

from __future__ import annotations

from pathlib import Path

import pytest

from loadline.adapters.runtime.compose_boot import labeled_objects_remaining
from loadline.run_pipeline import run_loadline

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "fx-pyhttp-pg"


@pytest.fixture
def loadline_home_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path / "loadline"))
    yield tmp_path / "loadline"


@pytest.mark.integration
def test_loadline_run_pipeline_writes_report(loadline_home_tmp):
    result = run_loadline(
        FIXTURE,
        skip_investigator=True,
        fast_baseline=True,
        require_auth=False,
    )
    assert result.exit_code == 0
    assert result.run_dir is not None
    assert result.report_md is not None
    assert result.report_md.is_file()
    text = result.report_md.read_text()
    assert "Loadline report" in text
    assert result.run_id is not None
    assert labeled_objects_remaining(result.run_id) == 0
