"""Collect telemetry for a k6 load step (S5)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loadline.adapters.generator.k6_runner import K6RunResult, run_k6_plan
from loadline.adapters.observability.docker_stats import (
    StatsCollector,
    _service_roles_from_launch_plan,
    aggregate_role,
    container_stats_series,
)
from loadline.adapters.observability.engine_caps import engine_placement
from loadline.adapters.observability.k6_metrics import k6_summary_to_series
from loadline.adapters.observability.postgres import discover_postgres_targets, snapshot_postgres
from loadline.core.limit_attribution import AttributionEntry, StepAttributionContext, compute_limit_attribution
from loadline.core.metrics import MetricSeries, NOT_MEASURED
@dataclass
class InstrumentedStepResult:
    k6: K6RunResult
    series: list[MetricSeries] = field(default_factory=list)
    attribution: list[AttributionEntry] = field(default_factory=list)
    observability: dict[str, Any] = field(default_factory=dict)


def run_instrumented_k6_plan(
    *,
    plan: dict[str, Any],
    allowed_hosts: frozenset[str],
    network: str,
    run_id: str,
    run_dir: Path,
    repo: Path,
    wave_name: str = "baseline",
    timeout_s: int = 180,
) -> InstrumentedStepResult:
    shape = plan.get("shape") or {}
    window_s = float(shape.get("warmup", 1)) + float(shape.get("duration", 3))
    launch_plan: dict[str, Any] = {}
    plan_path = run_dir / "launch_plan.json"
    if plan_path.is_file():
        launch_plan = json.loads(plan_path.read_text())
    collector = StatsCollector(run_id=run_id, service_roles=_service_roles_from_launch_plan(launch_plan))
    k6 = run_k6_plan(
        plan=plan,
        allowed_hosts=allowed_hosts,
        network=network,
        run_id=run_id,
        run_dir=run_dir,
        wave_name=wave_name,
        timeout_s=timeout_s,
        stats_collector=collector,
    )

    placement = engine_placement()
    series = k6_summary_to_series(k6.summary, evidence_prefix="ev-k6")
    series.extend(
        container_stats_series(collector.samples, window_s=window_s, evidence_prefix="ev-docker")
    )

    observability: dict[str, Any] = {
        "engine": {
            "ncpu": placement.engine_ncpu,
            "host_logical_cores": placement.host_logical_cores,
            "limiter": placement.limiter,
            "measurement_ceiling_limited": placement.measurement_ceiling_limited,
            "stats_fields_seen": sorted(collector.fields_seen),
        },
        "postgres": [],
    }

    project = f"loadline_{run_id}"
    compose = run_dir / "compose.runtime.yaml"
    if not compose.is_file():
        compose = run_dir / "launch_plan.validated.yaml"
    dep_evidence: list[str] = []
    for target in discover_postgres_targets(run_dir):
        if compose.is_file():
            pg_series, status = snapshot_postgres(
                project=project,
                compose_file=compose,
                repo=repo,
                target=target,
            )
            observability["postgres"].append({"service": target.service, "status": status})
            if pg_series:
                series.append(pg_series)
                dep_evidence.append(pg_series.evidence_id or f"ev-pg-{target.service}")
        else:
            observability["postgres"].append({"service": target.service, "status": "degraded"})

    app_stats = aggregate_role(collector.samples, "app")
    gen_stats = aggregate_role(collector.samples, "generator")
    host_cpu = _estimate_host_cpu_ratio(gen_stats, app_stats)
    implied = None
    if k6.summary.throughput_rps and k6.summary.p95_ms:
        implied = k6.summary.throughput_rps * (k6.summary.p95_ms / 1000.0)

    ctx = StepAttributionContext(
        verdict=k6.verdict,
        host_cpu_ratio=host_cpu,
        generator_cpu_ratio=_cpu_ratio(gen_stats.get("cpu_percent_max")),
        dropped_iteration_ratio=k6.summary.dropped_iterations / max(1, k6.successful_samples + k6.summary.dropped_iterations),
        app_cpu_percent=app_stats.get("cpu_percent_max"),
        throttle_value=app_stats.get("throttle_value", NOT_MEASURED),
        oom_killed=app_stats.get("oom_killed"),
        parse_ok=k6.summary.parse_ok,
        telemetry_coverage=_series_coverage(series),
        implied_concurrency=implied,
        measurement_ceiling_limited=placement.measurement_ceiling_limited,
        dependency_evidence_ids=[e for e in dep_evidence if e],
    )
    attribution = compute_limit_attribution(ctx)

    payload = {
        "series": [s.to_dict() for s in series],
        "attribution": [
            {"limit": a.limit, "rank": a.rank, "summary": a.summary, "evidence_ids": a.evidence_ids}
            for a in attribution
        ],
        "observability": observability,
        "verdict": k6.verdict,
    }
    wave_dir = run_dir / "waves" / wave_name
    wave_dir.mkdir(parents=True, exist_ok=True)
    (wave_dir / "telemetry.json").write_text(json.dumps(payload, indent=2))

    return InstrumentedStepResult(k6=k6, series=series, attribution=attribution, observability=observability)


def _cpu_ratio(percent: float | None) -> float:
    if percent is None:
        return 0.0
    return min(1.0, percent / 100.0)


def _estimate_host_cpu_ratio(gen_stats: dict[str, Any], app_stats: dict[str, Any]) -> float:
    vals = [v for v in (gen_stats.get("cpu_percent_max"), app_stats.get("cpu_percent_max")) if v is not None]
    if not vals:
        return 0.0
    return min(1.0, max(vals) / 100.0)


def _series_coverage(series: list[MetricSeries]) -> float:
    if not series:
        return 0.0
    return sum(s.coverage for s in series) / len(series)
