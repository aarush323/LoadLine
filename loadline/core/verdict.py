"""Load-step verdict order (tech_doc.md §9.3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from loadline.constants import (
    ACHIEVED_MIN,
    COVERAGE_MIN,
    DROP_MAX,
    GEN_CPU_SATURATED,
    HOST_SATURATED,
    MIN_SAMPLES,
    MIN_SAMPLES_P99,
    PROBE_MAX_BASELINE_MS,
    PROBE_RATIO,
)

VerdictCode = Literal[
    "pass",
    "fail",
    "target_unhealthy",
    "generator_failed",
    "measurement_gap",
    "host_saturated",
    "generator_limited",
    "achieved_below_target",
]


@dataclass(frozen=True)
class StepMetrics:
    telemetry_coverage: float
    host_cpu: float
    host_memory_pressure: bool
    host_port_or_fd_exhaustion: bool
    dropped_iteration_ratio: float
    vu_cap_hit: bool
    generator_cpu_ratio: float
    target_healthy: bool
    generator_ok: bool
    parse_ok: bool
    achieved_rate_ratio: float  # achieved / target
    has_drop_signal: bool
    p95_ms: float | None
    p99_ms: float | None
    err_rate: float
    slo_p95_ms: float
    slo_err_rate: float
    successful_samples: int
    probe_p95_ms: float | None
    probe_baseline_p95_ms: float | None
    need_percentile_for_verdict: bool = True


def percentile_allowed(samples: int, which: Literal["p50", "p95", "p99"]) -> bool:
    if which == "p99":
        return samples >= MIN_SAMPLES_P99
    return samples >= MIN_SAMPLES


def compute_verdict(m: StepMetrics) -> VerdictCode:
    if not m.target_healthy:
        return "target_unhealthy"
    if not m.generator_ok or not m.parse_ok:
        return "generator_failed"
    if m.telemetry_coverage < COVERAGE_MIN:
        return "measurement_gap"
    if m.host_cpu > HOST_SATURATED or m.host_memory_pressure or m.host_port_or_fd_exhaustion:
        return "host_saturated"
    if (
        m.dropped_iteration_ratio > DROP_MAX
        or m.vu_cap_hit
        or m.generator_cpu_ratio > GEN_CPU_SATURATED
    ):
        return "generator_limited"
    if m.need_percentile_for_verdict and m.successful_samples < MIN_SAMPLES:
        return "measurement_gap"
    probe_stall = False
    if m.probe_p95_ms is not None and m.probe_baseline_p95_ms is not None:
        threshold = max(PROBE_RATIO * m.probe_baseline_p95_ms, PROBE_MAX_BASELINE_MS)
        probe_stall = m.probe_p95_ms > threshold
    p95_breach = m.p95_ms is not None and m.p95_ms > m.slo_p95_ms
    err_breach = m.err_rate > m.slo_err_rate
    if p95_breach or err_breach or probe_stall:
        return "fail"
    if m.achieved_rate_ratio < ACHIEVED_MIN and not m.has_drop_signal:
        return "achieved_below_target"
    return "pass"


def moves_bracket(code: VerdictCode) -> bool:
    return code in ("pass", "fail")
