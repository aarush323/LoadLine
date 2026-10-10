from pathlib import Path
from unittest.mock import patch

from loadline.core.auth import AuthPreflightError
from loadline.run_pipeline import run_loadline


def test_run_exits_before_docker_when_auth_missing(tmp_path: Path):
    with patch("loadline.run_pipeline.boot_repository") as boot_mock:
        with patch(
            "loadline.core.auth.require_model_auth",
            return_value=AuthPreflightError("LOADLINE_MODEL is not set.", "LOADLINE_MODEL"),
        ):
            result = run_loadline(tmp_path, require_auth=True)
    assert result.exit_code == 2
    boot_mock.assert_not_called()
