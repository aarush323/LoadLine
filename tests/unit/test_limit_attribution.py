from loadline.core.limit_attribution import (
    StepAttributionContext,
    compute_limit_attribution,
    primary_limit_is_application_cpu,
)
from loadline.constants import HOST_SATURATED


def test_host_saturated_not_attributed_as_application_cpu():
    ctx = StepAttributionContext(
        verdict="invalid(host_saturated)",
        host_cpu_ratio=HOST_SATURATED + 0.05,
        generator_cpu_ratio=0.1,
        dropped_iteration_ratio=0.0,
        app_cpu_percent=95.0,
        parse_ok=True,
    )
    entries = compute_limit_attribution(ctx)
    assert entries
    assert entries[0].limit == "host"
    assert not primary_limit_is_application_cpu(entries)
    assert all(e.limit != "application_cpu" or e.rank > 1 for e in entries)


def test_generator_limited_ranked_before_application():
    ctx = StepAttributionContext(
        verdict="invalid(generator_limited)",
        host_cpu_ratio=0.2,
        generator_cpu_ratio=0.9,
        dropped_iteration_ratio=0.02,
        app_cpu_percent=80.0,
        parse_ok=True,
    )
    entries = compute_limit_attribution(ctx)
    assert entries[0].limit == "generator"
    assert not primary_limit_is_application_cpu(entries)
