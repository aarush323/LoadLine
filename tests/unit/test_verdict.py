from loadline.core.verdict import StepMetrics, compute_verdict, moves_bracket


def _healthy(**kwargs) -> StepMetrics:
    base = {
        "telemetry_coverage": 0.95,
        "host_cpu": 0.2,
        "host_memory_pressure": False,
        "host_port_or_fd_exhaustion": False,
        "dropped_iteration_ratio": 0.0,
        "vu_cap_hit": False,
        "generator_cpu_ratio": 0.1,
        "target_healthy": True,
        "generator_ok": True,
        "parse_ok": True,
        "achieved_rate_ratio": 1.0,
        "has_drop_signal": False,
        "p95_ms": 50.0,
        "p99_ms": None,
        "err_rate": 0.0,
        "slo_p95_ms": 200.0,
        "slo_err_rate": 0.01,
        "successful_samples": 250,
        "probe_p95_ms": 20.0,
        "probe_baseline_p95_ms": 15.0,
    }
    base.update(kwargs)
    return StepMetrics(**base)


def test_verdict_order_host_before_fail():
    m = _healthy(host_cpu=0.95, p95_ms=5000)
    assert compute_verdict(m) == "host_saturated"


def test_measurement_gap_low_samples():
    m = _healthy(successful_samples=50, p95_ms=5000)
    assert compute_verdict(m) == "measurement_gap"


def test_pass():
    assert compute_verdict(_healthy()) == "pass"
    assert moves_bracket("pass")
