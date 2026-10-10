"""limit_attribution ranked list (tech_doc.md §10.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loadline.constants import GEN_CPU_SATURATED, HOST_SATURATED
from loadline.core.metrics import NOT_MEASURED


@dataclass
class AttributionEntry:
    limit: str
    rank: int
    summary: str
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class StepAttributionContext:
    verdict: str
    host_cpu_ratio: float
    generator_cpu_ratio: float
    dropped_iteration_ratio: float
    app_cpu_percent: float | None
    throttle_value: Any = NOT_MEASURED
    oom_killed: bool | None = None
    parse_ok: bool = True
    telemetry_coverage: float = 1.0
    implied_concurrency: float | None = None
    measurement_ceiling_limited: bool = False
    dependency_evidence_ids: list[str] = field(default_factory=list)


def compute_limit_attribution(ctx: StepAttributionContext) -> list[AttributionEntry]:
    entries: list[AttributionEntry] = []
    verdict = ctx.verdict

    def add(limit: str, summary: str, evidence_ids: list[str]) -> None:
        entries.append(AttributionEntry(limit=limit, rank=len(entries) + 1, summary=summary, evidence_ids=evidence_ids))

    if not ctx.parse_ok or "measurement_gap" in verdict:
        add("measurement_failure", "Step metrics incomplete or below sample thresholds.", ["ev-k6-p95", "ev-k6-throughput"])
        return entries

    if "generator_limited" in verdict or ctx.dropped_iteration_ratio > 0.005:
        add("generator", "Generator dropped iterations or hit generator limits.", ["ev-k6-dropped", "ev-generator-cpu"])
    if "host_saturated" in verdict or ctx.host_cpu_ratio > HOST_SATURATED:
        add("host", "Host or engine CPU saturation dominated the step.", ["ev-host-cpu"])
    if ctx.measurement_ceiling_limited:
        add("host", "Docker engine CPU is below host logical cores (measurement_ceiling_limited).", ["ev-engine-ncpu"])

    throttle_measured = ctx.throttle_value is not NOT_MEASURED and ctx.throttle_value is not None
    if throttle_measured and ctx.throttle_value not in (0, "0", 0.0):
        add("environment_limit", "CPU throttling was observed on a container.", ["ev-app-throttle", "ev-generator-throttle"])
    if ctx.oom_killed:
        add("environment_limit", "A container reported OOMKilled.", ["ev-app-oom"])

    # Application bottlenecks must not be attributed when host/generator saturated.
    host_or_gen = any(
        e.limit in ("host", "generator")
        for e in entries
    ) or "host_saturated" in verdict or "generator_limited" in verdict

    if not host_or_gen:
        if ctx.app_cpu_percent is not None and ctx.app_cpu_percent > 70:
            add("application_cpu", "Application container CPU utilization was high.", ["ev-app-cpu"])
        if (
            ctx.app_cpu_percent is not None
            and ctx.app_cpu_percent < 40
            and ctx.implied_concurrency is not None
            and ctx.implied_concurrency > 5
        ):
            add("application_blocking", "Low CPU with rising implied concurrency.", ["ev-k6-p95", "ev-app-cpu"])

    if ctx.dependency_evidence_ids and not host_or_gen:
        add("dependency", "Dependency telemetry showed activity during the step.", ctx.dependency_evidence_ids)

    if not entries:
        if "fail" in verdict:
            add("unknown", "SLO breach without a dominant limit signal.", ["ev-k6-p95", "ev-k6-err-rate"])
        elif verdict == "pass":
            add("unknown", "Step passed; no limit signal required.", ["ev-k6-throughput"])
        else:
            add("unknown", "No dominant limit identified.", ["ev-k6-throughput"])

    return entries


def primary_limit_is_application_cpu(entries: list[AttributionEntry]) -> bool:
    if not entries:
        return False
    return entries[0].limit in ("application_cpu", "application_blocking")
