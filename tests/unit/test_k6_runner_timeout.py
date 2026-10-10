import subprocess
from pathlib import Path
from unittest.mock import patch

from loadline.adapters.generator.k6_runner import run_k6_plan


def test_k6_runner_timeout_returns_error_dict(tmp_path: Path):
    plan = {
        "mix": [
            {
                "weight": 1,
                "op": {
                    "id": "h",
                    "service": "web",
                    "port": 8000,
                    "selector": {"method": "GET", "path": "/"},
                },
            }
        ],
        "shape": {"rate": 2, "duration": 5},
    }
    with patch("loadline.adapters.generator.k6_runner.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=30)
        result = run_k6_plan(
            plan=plan,
            allowed_hosts=frozenset({"web"}),
            network="net-test",
            run_id="rid",
            run_dir=tmp_path,
            wave_name="w1",
            timeout_s=30,
        )
    assert not result.summary.parse_ok
    assert "timed out" in (result.summary.error or "").lower()
