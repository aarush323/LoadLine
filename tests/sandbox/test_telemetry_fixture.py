"""S5: telemetry and limit_attribution on a real booted step."""

from __future__ import annotations

from pathlib import Path

import pytest

from loadline.adapters.observability.step_telemetry import run_instrumented_k6_plan
from loadline.adapters.runtime.boot_teardown import teardown_boot_outcome
from loadline.adapters.runtime.compose_boot import boot_repository
from loadline.discovery.workload import discover_workload_operations, operations_to_mix

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "fx-pyhttp-pg"

TEST_WARMUP_S = 1
TEST_MEASURE_S = 3
TEST_RATE = 5


@pytest.fixture
def loadline_home_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path / "loadline"))
    yield tmp_path / "loadline"


@pytest.mark.integration
def test_step_has_attribution_and_evidence(loadline_home_tmp):
    boot = boot_repository(FIXTURE, teardown=False, require_auth=False)
    assert boot.status == "booted" and boot.run_id and boot.boot
    try:
        network = boot.boot["network"]
        run_dir = Path(boot.boot["run_dir"])
        hosts = frozenset(s["name"] for s in boot.boot["services"])
        ops = discover_workload_operations(FIXTURE, boot.boot, network)
        mix = operations_to_mix(ops)
        plan = {"mix": mix, "shape": {"rate": TEST_RATE, "warmup": TEST_WARMUP_S, "duration": TEST_MEASURE_S}}
        result = run_instrumented_k6_plan(
            plan=plan,
            allowed_hosts=hosts,
            network=network,
            run_id=boot.run_id,
            run_dir=run_dir,
            repo=FIXTURE,
            wave_name="baseline",
        )
        assert result.attribution
        assert all(a.evidence_ids for a in result.attribution)
        assert result.series
        tele_path = run_dir / "waves" / "baseline" / "telemetry.json"
        assert tele_path.is_file()
        assert result.k6.successful_samples > 0
        assert result.observability.get("engine", {}).get("stats_fields_seen")
    finally:
        teardown_boot_outcome(boot, FIXTURE)
