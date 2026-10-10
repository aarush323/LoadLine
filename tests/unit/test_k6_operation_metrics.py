import json

from loadline.adapters.generator.k6_operation_metrics import (
    aggregate_operations_from_metrics,
    sanitize_operation_metrics,
)
from loadline.adapters.generator.k6_summary import parse_handle_summary


def test_parse_handle_summary_uses_operations_blob_with_status():
    metrics = {
        "http_reqs{operation:widget,status:200}": {"values": {"count": 50}},
        "http_reqs{operation:widget,status:503}": {"values": {"count": 5}},
        "http_req_duration{operation:widget}": {"values": {"med": 100, "p(95)": 500, "count": 55}},
        "http_req_failed": {"values": {"rate": 0}},
    }
    payload = {
        "vu_ceiling": 50,
        "duration_s": 10,
        "vus_max": 4,
        "dropped_iterations": 0,
        "metrics": metrics,
        "operations": {
            "widget": {
                "count": 55,
                "status_counts": {"200": 50, "503": 5},
                "error_count": 5,
            }
        },
        "state": {"testRunDurationMs": 10000},
    }
    parsed = parse_handle_summary(json.dumps(payload))
    assert parsed.parse_ok
    assert parsed.operations["widget"]["status_counts"].get("503") == 5


def test_aggregate_two_operations_different_p95_not_hidden_by_aggregate():
    metrics = {
        "http_reqs": {"values": {"count": 200, "rate": 20}},
        "http_req_duration": {"values": {"med": 30, "p(95)": 120, "count": 200}},
        "http_reqs{operation:fast,status:200}": {"values": {"count": 100}},
        "http_req_duration{operation:fast}": {"values": {"med": 5, "p(95)": 12, "count": 100}},
        "http_reqs{operation:slow,status:200}": {"values": {"count": 100}},
        "http_req_duration{operation:slow}": {"values": {"med": 80, "p(95)": 250, "count": 100}},
        "http_req_failed": {"values": {"rate": 0}},
        "dropped_iterations": {"values": {"count": 0}},
        "vus": {"values": {"max": 4}},
    }
    payload = {
        "vu_ceiling": 50,
        "duration_s": 10,
        "vus_max": 4,
        "vus_max_reached": False,
        "dropped_iterations": 0,
        "metrics": metrics,
        "state": {"testRunDurationMs": 10000},
    }
    parsed = parse_handle_summary(json.dumps(payload))
    assert parsed.parse_ok
    assert parsed.p95_ms == 120
    assert parsed.operations["fast"]["p95_ms"] == 12
    assert parsed.operations["slow"]["p95_ms"] == 250
    assert parsed.operations["fast"]["count"] == 100
    assert parsed.operations["slow"]["count"] == 100


def test_aggregate_counts_non_2xx_as_errors():
    metrics = {
        "http_reqs{operation:login,status:401}": {"values": {"count": 40}},
        "http_reqs{operation:login,status:200}": {"values": {"count": 10}},
        "http_req_failed{operation:login}": {"values": {"rate": 0.8}},
    }
    ops = aggregate_operations_from_metrics(metrics)
    assert ops["login"]["error_count"] == 40
    assert ops["login"]["status_counts"]["401"] == 40


def test_operation_only_http_reqs_does_not_invent_status_zero_errors():
    metrics = {
        "http_reqs{operation:healthz}": {"values": {"count": 50}},
        "http_req_duration{operation:healthz}": {"values": {"med": 2, "p(95)": 4, "count": 50}},
        "http_req_failed{operation:healthz}": {"values": {"rate": 0}},
    }
    ops = aggregate_operations_from_metrics(metrics)
    row = ops["healthz"]
    assert row["count"] == 50
    assert row["status_counts"] == {}
    assert row["error_count"] == 0
    assert row["error_rate"] == 0.0
    assert row["http_status_known"] is False
    assert row["status_counts_reliable"] is False


def test_sanitize_legacy_status_zero_bucket():
    row = sanitize_operation_metrics(
        {"count": 20, "error_count": 20, "error_rate": 1.0, "status_counts": {"0": 20}}
    )
    assert row["status_counts"] == {}
    assert row["error_count"] == 0
    assert row["error_rate"] == 0.0
