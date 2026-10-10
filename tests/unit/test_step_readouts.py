from loadline.adapters.generator.k6_runner import K6RunResult
from pathlib import Path

from loadline.adapters.generator.k6_summary import K6Summary
from loadline.adapters.observability.step_telemetry import InstrumentedStepResult
from loadline.core.metrics import MetricPoint, MetricSeries
from loadline.core.step_readouts import readouts_from_step


def _step(cpu: float | None = 42.0) -> InstrumentedStepResult:
    summary = K6Summary(parse_ok=True, throughput_rps=100.0, p95_ms=1.0, p50_ms=0.5, err_rate=0.0)
    k6 = K6RunResult(
        summary=summary,
        verdict="pass",
        successful_samples=500,
        stdout_path=Path("/tmp/k6-out"),
        exit_code=0,
        stderr="",
    )
    series: list[MetricSeries] = []
    if cpu is not None:
        series.append(
            MetricSeries(
                name="cpu_percent",
                unit="percent",
                entity="app",
                kind="gauge",
                points=[MetricPoint(t=0.0, value=cpu)],
                evidence_id="ev-docker-app-cpu",
            )
        )
    return InstrumentedStepResult(k6=k6, series=series, attribution=[], observability={})


def test_cpu_util_from_docker_series():
    out = readouts_from_step(_step())
    assert "cpu_util" in out
    assert out["cpu_util"]["value"] == 42.0


def test_missing_cpu_series_omitted():
    out = readouts_from_step(_step(cpu=None))
    assert "cpu_util" not in out
