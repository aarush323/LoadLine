"""Pipeline goes boot → investigator only (no calibration/baseline/ladder)."""

from pathlib import Path
from unittest.mock import patch

from loadline.investigator.run import InvestigationResult
from loadline.run_pipeline import run_loadline


def test_run_loadline_skips_pre_agent_load_stages(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "loadline" / "runs" / "rid"
    run_dir.mkdir(parents=True)

    boot_payload = {
        "run_dir": str(run_dir),
        "network": "loadline_net",
        "services": [{"name": "web", "port": 8000}],
        "health": {"url": "http://web:8000/health"},
    }

    class BootOk:
        status = "booted"
        exit_code = 0
        run_id = "rid"
        boot = boot_payload
        blocker = None
        attempts = []
        capabilities = None

    inv_result = InvestigationResult("rid", run_dir, "completed", agent_output="# ok")
    (run_dir / "report.md").write_text("# ok")

    with patch("loadline.run_pipeline.boot_repository", return_value=BootOk()):
        with patch("loadline.run_pipeline.run_investigation_sync", return_value=inv_result) as inv_mock:
            with patch("loadline.run_pipeline.teardown_boot_outcome"):
                with patch("loadline.run_pipeline.register_run_cleanup"):
                    with patch("loadline.run_pipeline.unregister_run_cleanup"):
                        with patch("loadline.run_pipeline.shutdown_neatlogs"):
                            with patch(
                                "loadline.discovery.workload.discover_workload_operations",
                                side_effect=AssertionError("workload discovery must not run"),
                            ):
                                result = run_loadline(repo, require_auth=False, skip_investigator=False)

    inv_mock.assert_called_once()
    call_kw = inv_mock.call_args.kwargs
    assert call_kw["allowed_hosts"] == frozenset({"web"})
    assert call_kw["network"] == "loadline_net"
    assert result.status == "completed"
