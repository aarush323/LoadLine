import json

from loadline.adapters.generator.k6_summary import (
    format_percentile,
    parse_handle_summary,
    successful_request_count,
)


def _sample_summary(count: int = 250, p95: float = 12.3) -> str:
    payload = {
        "metrics": {
            "http_reqs": {"values": {"count": count, "rate": count / 10.0}},
            "http_req_duration": {
                "values": {
                    "med": 5.0,
                    "p(95)": p95,
                    "p(99)": 99.0,
                }
            },
            "http_req_failed": {"values": {"rate": 0.01, "passes": count - 2, "fails": 2}},
            "dropped_iterations": {"values": {"count": 0}},
            "vus": {"values": {"max": 10}},
        },
        "root_group": {
            "groups": [],
            "checks": [{"name": "status ok", "passes": count, "fails": 0}],
        },
        "state": {"testRunDurationMs": 10000},
        "operations": {
            "health": {"http_reqs": count, "http_req_failed": 0},
        },
    }
    return json.dumps(payload)


def test_parse_throughput_and_p95():
    parsed = parse_handle_summary(_sample_summary())
    assert parsed.parse_ok
    assert parsed.throughput_rps == 25.0
    assert parsed.p50_ms == 5.0
    assert parsed.p95_ms == 12.3
    assert parsed.err_rate == 0.01
    assert parsed.dropped_iterations == 0
    assert parsed.vus_max == 10


def test_format_percentile_below_min_samples():
    assert format_percentile(50, "p95", 10.0) == "not measured (samples=50)"


def test_format_percentile_at_min_samples():
    assert format_percentile(200, "p95", 10.0) == "10.0"


def test_successful_request_count_uses_check_passes():
    parsed = parse_handle_summary(_sample_summary(count=100))
    assert successful_request_count(parsed) == 100
