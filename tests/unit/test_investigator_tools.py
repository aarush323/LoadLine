from pathlib import Path
from unittest.mock import MagicMock

from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel

from loadline.core.ledger import Ledger
from loadline.investigator.deps import InvestigationDeps
from loadline.investigator.k6_tool import format_run_k6_result
from loadline.investigator.tools import RunK6Input, EndpointSpec, read_file


def _ctx(tmp_path: Path) -> RunContext[InvestigationDeps]:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ledger = Ledger.open(run_dir, "rid1")
    deps = InvestigationDeps(
        repo_root=tmp_path,
        run_dir=run_dir,
        run_id="rid1",
        ledger=ledger,
        graph=None,
        boot={"health": {"url": "http://web:8000/health"}},
        allowed_hosts=frozenset({"web"}),
        network="net1",
    )
    return RunContext(deps=deps, model=TestModel(), usage=MagicMock(), prompt=None)


def test_read_file_records_range(tmp_path: Path):
    src = tmp_path / "app.py"
    src.write_text("line1\nline2\nline3\n")
    ctx = _ctx(tmp_path)
    out = read_file(ctx, "app.py", 1, 2)
    assert "snippet" in out
    assert len(ctx.deps.read_ranges) == 1


def test_format_run_k6_result_has_per_operation_latency_and_no_verdict():
    raw = {
        "vu_ceiling": 50,
        "vus_max": 4,
        "vus_max_reached": False,
        "dropped_iterations": 0,
        "operations": {
            "login": {
                "count": 30,
                "error_rate": 0.0,
                "p50_ms": 12,
                "p95_ms": 40,
                "achieved_rps": 2.0,
                "status_counts": {"200": 30},
            }
        },
    }
    out = format_run_k6_result(
        raw,
        offered_rps=10,
        duration_s=15,
        endpoint_ids=["login"],
        weights=[1],
    )
    assert "verdict" not in out
    assert out["operations"]["login"]["p95_ms"] == 40
    assert out["operations"]["login"]["status_counts"] == {"200": 30}
    assert out["operations"]["login"]["status_counts_reliable"] is True


def test_format_run_k6_result_flags_unreliable_status_counts():
    raw = {
        "vu_ceiling": 50,
        "vus_max": 4,
        "vus_max_reached": False,
        "dropped_iterations": 0,
        "operations": {
            "healthz": {
                "count": 20,
                "error_count": 0,
                "error_rate": 0.0,
                "p95_ms": 5,
                "status_counts": {},
                "http_status_known": False,
                "status_counts_reliable": False,
            }
        },
    }
    out = format_run_k6_result(
        raw,
        offered_rps=2,
        duration_s=10,
        endpoint_ids=["healthz"],
        weights=[1],
    )
    op = out["operations"]["healthz"]
    assert op["status_counts_reliable"] is False
    assert any("status_counts" in n for n in op.get("measurement_notes", []))


def test_format_run_k6_result_aggregate_when_tags_missing():
    raw = {
        "vu_ceiling": 50,
        "vus_max": 10,
        "vus_max_reached": False,
        "dropped_iterations": 0,
        "operations": {},
        "metrics": {
            "http_reqs": {"values": {"count": 500, "rate": 50}},
            "http_req_duration": {"values": {"med": 20, "p(95)": 80, "count": 500}},
        },
    }
    out = format_run_k6_result(
        raw,
        offered_rps=50,
        duration_s=10,
        endpoint_ids=["health"],
        weights=[1],
    )
    assert out["operations"]["health"]["count"] == 0
    assert out.get("aggregate", {}).get("http_reqs_count") == 500
    assert "metrics_note" in out


def test_validate_endpoint_rejects_path_templates():
    from loadline.investigator.k6_tool import validate_endpoint

    assert validate_endpoint({"path": "/items/{id}", "method": "GET"}) is not None
    assert validate_endpoint({"path": "/health", "method": "GET"}) is None


def test_run_k6_input_accepts_endpoints():
    payload = RunK6Input(endpoints=[EndpointSpec(id="h", path="/health")], rate=2, duration_s=5)
    assert payload.endpoints[0].path == "/health"
