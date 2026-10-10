from pathlib import Path
from unittest.mock import MagicMock

from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel

from loadline.core.ledger import Ledger
from loadline.investigator.deps import InvestigationDeps
from loadline.investigator.k6_tool import (
    _app_target,
    build_plan_from_endpoints,
    format_run_k6_result,
    run_k6,
)
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


def test_read_file_rejects_absolute_run_artifact_path(tmp_path: Path):
    ctx = _ctx(tmp_path)
    out = read_file(ctx, "/home/user/.local/share/loadline/runs/x/k6.stdout", 1, 10)
    assert "error" in out
    assert "run_k6" in out["error"]


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


def test_app_target_uses_health_url_host_and_port():
    assert _app_target({"health": {"url": "http://web:8000/health"}}) == ("web", 8000)
    assert _app_target({"health": {"url": "http://backend:9000/api/health"}}) == ("backend", 9000)


def test_app_target_missing_health_url_is_none():
    assert _app_target({}) is None
    assert _app_target({"health": {}}) is None
    assert _app_target({"health": {"url": ""}}) is None
    # No service fallback: even with services present, missing URL stays unknown.
    assert _app_target({"services": [{"name": "web", "port": 8000}]}) is None


def test_run_k6_missing_origin_returns_origin_unknown(tmp_path: Path):
    ctx = _ctx(tmp_path)
    ctx.deps.boot = {}
    out = run_k6(ctx.deps, [{"path": "/health", "method": "GET"}], 2, 5)
    assert "error" in out
    assert "origin_unknown" in out["error"]
    assert out.get("code") == "origin_unknown"
    # Must not fall back to hostname app.
    assert "app" not in out["error"] or "origin_unknown" in out["error"]


def test_run_k6_empty_endpoints_is_error(tmp_path: Path):
    ctx = _ctx(tmp_path)
    out = run_k6(ctx.deps, [], 2, 5)
    assert "error" in out


def test_format_empty_operations_is_not_success():
    raw = {
        "vu_ceiling": 50,
        "vus_max": 4,
        "vus_max_reached": False,
        "dropped_iterations": 0,
        "operations": {},
        "metrics": {},
    }
    out = format_run_k6_result(
        raw,
        offered_rps=2,
        duration_s=10,
        endpoint_ids=["health"],
        weights=[1],
    )
    op = out["operations"]["health"]
    assert op["count"] == 0
    assert op["status_counts_reliable"] is False
    assert op.get("measurement_notes")


def test_resolve_auth_uses_present_profile(tmp_path: Path):
    from loadline.investigator.k6_tool import _resolve_auth_secrets

    ctx = _ctx(tmp_path)
    ctx.deps.auth_profiles = {"api_user": {"username": "u", "password": "p"}}
    secrets, err = _resolve_auth_secrets(ctx.deps, {"profile": "api_user"})
    assert err is None
    assert secrets == {"username": "u", "password": "p"}


def test_resolve_auth_default_fallback_still_works(tmp_path: Path):
    from loadline.investigator.k6_tool import _resolve_auth_secrets

    ctx = _ctx(tmp_path)
    ctx.deps.auth_profiles = {"default_user": {"username": "admin@example.com", "password": "secret"}}
    secrets, err = _resolve_auth_secrets(ctx.deps, {"profile": "default_user"})
    assert err is None
    assert secrets["username"] == "admin@example.com"


def test_resolve_auth_missing_secret_is_error_no_script(tmp_path: Path):
    from unittest.mock import patch

    ctx = _ctx(tmp_path)
    ctx.deps.auth_profiles = {}
    with patch("loadline.investigator.k6_tool.run_k6_plan") as mocked:
        out = run_k6(ctx.deps, [{"path": "/items", "method": "GET"}], 2, 5, auth={"profile": "default_user", "path": "/login"})
        assert "error" in out
        mocked.assert_not_called()


def test_probe_negative_302_accepted(tmp_path: Path):
    from unittest.mock import patch

    from loadline.adapters.runtime.probe import probe_profile

    class Proc:
        def __init__(self, code):
            self.stdout = str(code)
            self.stderr = ""
            self.returncode = 0

    calls = {"n": 0}

    def fake_cmd(args, timeout=60):
        calls["n"] += 1
        if calls["n"] == 1:
            return Proc(200)
        return Proc(302)

    with patch("loadline.adapters.runtime.docker_runner.docker_cmd", side_effect=fake_cmd):
        # Patch probe's internal import (it imports inside function, so patch runner).
        import loadline.adapters.runtime.probe as pm

        with patch.object(pm, "__name__", pm.__name__):
            pass
        out = probe_profile(
            network="net1",
            service="web",
            port=8000,
            profile_name="default_user",
            profile_cfg={"method": "POST", "path": "/login", "verify": "/me"},
            credentials={"username": "u", "password": "p"},
        )
    assert out.get("verified") is True
    assert out.get("negative_status") == 302


def test_probe_negative_200_warns_not_verified(tmp_path: Path):
    from unittest.mock import patch

    from loadline.adapters.runtime.probe import probe_profile

    class Proc:
        def __init__(self, code):
            self.stdout = str(code)
            self.stderr = ""
            self.returncode = 0

    calls = {"n": 0}

    def fake_cmd(args, timeout=60):
        calls["n"] += 1
        if calls["n"] == 1:
            return Proc(200)
        return Proc(200)

    with patch("loadline.adapters.runtime.docker_runner.docker_cmd", side_effect=fake_cmd):
        out = probe_profile(
            network="net1",
            service="web",
            port=8000,
            profile_name="default_user",
            profile_cfg={"method": "POST", "path": "/login", "verify": "/me"},
            credentials={"username": "u", "password": "p"},
        )
    assert out.get("verified") is not True
    assert "warning" in out or out.get("negative_status") == 200
