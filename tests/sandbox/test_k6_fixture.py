"""S4: k6 container on the boot network hits the app."""

from __future__ import annotations

from pathlib import Path

import pytest

from loadline.adapters.generator.k6_runner import run_k6_plan
from loadline.adapters.runtime.boot_teardown import teardown_boot_outcome
from loadline.adapters.runtime.compose_boot import boot_repository
from loadline.discovery.workload import discover_workload_operations, operations_to_mix

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "fx-pyhttp-pg"

TEST_MEASURE_S = 3
TEST_RATE = 5


@pytest.fixture
def loadline_home_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path / "loadline"))
    yield tmp_path / "loadline"


@pytest.mark.integration
def test_k6_container_sends_traffic_to_booted_app(loadline_home_tmp):
    boot = boot_repository(FIXTURE, teardown=False, require_auth=False)
    assert boot.status == "booted"
    assert boot.boot is not None and boot.run_id is not None
    try:
        network = boot.boot["network"]
        run_dir = Path(boot.boot["run_dir"])
        hosts = frozenset(s["name"] for s in boot.boot["services"])
        operations = discover_workload_operations(FIXTURE, boot.boot, network)
        assert operations, "expected at least one smoke-passing operation"
        mix = operations_to_mix(operations)

        plan = {
            "mix": mix,
            "shape": {"rate": TEST_RATE, "duration": TEST_MEASURE_S},
        }
        result = run_k6_plan(
            plan=plan,
            allowed_hosts=hosts,
            network=network,
            run_id=boot.run_id,
            run_dir=run_dir,
            wave_name="baseline",
            timeout_s=180,
        )
        assert result.stdout_path.is_file()
        assert (run_dir / "waves" / "baseline" / "k6.stdout").read_text()
        assert result.summary.parse_ok
        assert result.successful_samples > 0
        assert result.summary.throughput_rps and result.summary.throughput_rps > 0
        if result.summary.operations:
            assert sum(v.get("http_reqs", 0) for v in result.summary.operations.values()) > 0
    finally:
        teardown_boot_outcome(boot, FIXTURE)
