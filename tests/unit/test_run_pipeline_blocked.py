import json
from pathlib import Path
from unittest.mock import patch

from loadline.adapters.runtime.compose_boot import BootOutcome
from loadline.run_pipeline import run_loadline


def test_blocked_boot_writes_profile_without_docker(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path / "state"))
    blocker = {"code": "policy_refused", "summary": "refused"}
    boot = BootOutcome(
        status="blocked",
        exit_code=10,
        blocker=blocker,
        run_id="runblocked1",
        capabilities={"blockers": []},
    )
    run_dir = tmp_path / "state" / "runs" / "runblocked1"
    run_dir.mkdir(parents=True)
    with patch("loadline.run_pipeline.boot_repository", return_value=boot):
        with patch("loadline.core.auth.require_model_auth", return_value=None):
            result = run_loadline(tmp_path, require_auth=False)
    assert result.exit_code == 10
    assert result.run_dir == run_dir
    profile = json.loads((run_dir / "profile.json").read_text())
    caps = json.loads((run_dir / "capabilities.json").read_text())
    assert isinstance(profile, dict)
    assert isinstance(caps, dict)
