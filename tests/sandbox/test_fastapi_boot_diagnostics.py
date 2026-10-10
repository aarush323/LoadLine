"""Optional boot of the pinned FastAPI template: diagnostics, not a greenwash."""

from __future__ import annotations

from pathlib import Path

import pytest

from loadline.adapters.runtime.compose_boot import boot_repository

TEMPLATE = Path(__file__).resolve().parents[2] / "integration" / "targets" / "full-stack-fastapi-template"


@pytest.fixture
def loadline_home_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path / "loadline"))
    yield tmp_path / "loadline"


@pytest.mark.integration
def test_fastapi_boot_is_diagnosable_or_healthy(loadline_home_tmp):
    if not TEMPLATE.is_dir():
        pytest.skip("pinned FastAPI template is not checked out")
    outcome = boot_repository(TEMPLATE, teardown=True, require_auth=False)
    code = (outcome.blocker or {}).get("code")
    assert code != "policy_refused"
    if outcome.status == "booted":
        assert outcome.boot is not None
        return
    assert code == "health_timeout"
    summary = (outcome.blocker or {}).get("summary") or ""
    evidence = (outcome.blocker or {}).get("evidence") or {}
    assert "compose ps" in summary or evidence.get("ps")
