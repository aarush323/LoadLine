"""Table-driven readiness budget, wait, and compose-up classification."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import urlparse

import pytest
import yaml

from loadline.adapters.runtime.compose_boot import _health_url, boot_repository
from loadline.core.readiness import (
    COMPOSE_UP_TRANSIENT_ATTEMPTS,
    BootEvidence,
    HealthWaitResult,
    ProbeResult,
    classify_compose_up_failure,
    compose_up_with_retries,
    compute_readiness_budget_s,
    dockerfile_readiness_budget_s,
    excerpt_boot_log,
    healthcheck_budget_s,
    wait_until_http_ready,
)
from loadline.paths import loadline_home

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


class _Proc:
    def __init__(self, returncode: int, stderr: str = "", stdout: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout


@pytest.mark.parametrize(
    ("start_s", "expected"),
    [(5, 50.0), (30, 75.0), (60, 105.0)],
)
def test_budget_scales_with_dependency_delay(start_s: int, expected: float) -> None:
    plan = {
        "services": {
            "app": {"depends_on": ["db"]},
            "db": {
                "healthcheck": {
                    "start_period": f"{start_s}s",
                    "interval": "5s",
                    "timeout": "5s",
                    "retries": 3,
                }
            },
        }
    }
    assert compute_readiness_budget_s(plan, "app") == expected


def test_timeout_increases_healthcheck_budget() -> None:
    base = {"healthcheck": {"start_period": "0s", "interval": "5s", "retries": 3}}
    slower = {"healthcheck": {"start_period": "0s", "interval": "5s", "timeout": "20s", "retries": 3}}
    assert healthcheck_budget_s(slower) > healthcheck_budget_s(base)
    assert healthcheck_budget_s(base) == 30.0
    assert healthcheck_budget_s(slower) == 75.0


def test_transitive_depends_on_includes_db_budget() -> None:
    plan = {
        "services": {
            "app": {"depends_on": ["api"]},
            "api": {"depends_on": ["db"]},
            "db": {
                "healthcheck": {
                    "start_period": "60s",
                    "interval": "5s",
                    "timeout": "5s",
                    "retries": 3,
                }
            },
        }
    }
    assert compute_readiness_budget_s(plan, "app") == 105.0


def test_dockerfile_budget_is_within_cap() -> None:
    budget = dockerfile_readiness_budget_s()
    assert budget == 60.0
    assert 30.0 <= budget <= 180.0


def test_wait_succeeds_on_later_probe() -> None:
    clock = _Clock()
    calls = {"n": 0}

    def probe() -> ProbeResult:
        calls["n"] += 1
        if calls["n"] >= 3:
            return ProbeResult(ok=True, exit_code=0, http_code=200)
        return ProbeResult(ok=False, exit_code=7, http_code=None, detail="connect")

    result = wait_until_http_ready(
        probe, 30, poll_s=2, monotonic=clock.monotonic, sleep=clock.sleep
    )
    assert result.ready
    assert result.polls == 3
    assert clock.t == 4.0


def test_wait_deadline_is_not_ready() -> None:
    clock = _Clock()

    def probe() -> ProbeResult:
        return ProbeResult(ok=False, exit_code=7, http_code=0, detail="connection refused")

    result = wait_until_http_ready(
        probe, 5, poll_s=2, monotonic=clock.monotonic, sleep=clock.sleep
    )
    assert isinstance(result, HealthWaitResult)
    assert result.ready is False
    assert result.polls == 3
    assert result.elapsed_s == 5.0
    assert result.last_probe is not None
    assert result.last_probe.exit_code == 7


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("error pulling image: i/o timeout", "transient"),
        ("TLS handshake timeout talking to registry-1.docker.io", "transient"),
        ("toomanyrequests: too many requests", "transient"),
        ("failed to resolve reference: dial tcp: lookup: no such host", "transient"),
        ("required variable REQUIRED_APP_TOKEN is missing a value: must be set", "deterministic"),
        ("The FOO variable is not set. Defaulting to a blank string.", "deterministic"),
        ("failed to solve: dockerfile parse error", "deterministic"),
        ("service app depends on undefined service db", "deterministic"),
        ("yaml: line 4: did not find expected key", "deterministic"),
        ("something unrecognized happened", "deterministic"),
    ],
)
def test_classify_compose_up_failure(stderr: str, expected: str) -> None:
    assert classify_compose_up_failure(stderr) == expected


def test_transient_compose_up_retries_then_stops() -> None:
    calls = {"n": 0}
    slept: list[float] = []

    def run_up() -> _Proc:
        calls["n"] += 1
        return _Proc(1, stderr="error pulling image: i/o timeout")

    proc, failures = compose_up_with_retries(run_up, sleep=slept.append)
    assert proc.returncode == 1
    assert len(failures) == COMPOSE_UP_TRANSIENT_ATTEMPTS
    assert calls["n"] == COMPOSE_UP_TRANSIENT_ATTEMPTS
    assert slept == [5.0, 5.0]


def test_deterministic_compose_up_does_not_retry() -> None:
    calls = {"n": 0}

    def run_up() -> _Proc:
        calls["n"] += 1
        return _Proc(1, stderr="required variable REQUIRED_APP_TOKEN is missing a value")

    _proc, failures = compose_up_with_retries(run_up, sleep=lambda _s: (_ for _ in ()).throw(AssertionError("slept")))
    assert calls["n"] == 1
    assert len(failures) == 1
    assert failures[0].failure_class == "deterministic"


def test_probe_url_uses_service_dns_not_healthcheck_host() -> None:
    spec = {"healthcheck": {"test": ["CMD", "curl", "-f", "http://localhost:8000/health"]}}
    port, path = _health_url("api", None, spec)
    url = f"http://api:{port}{path}"
    assert urlparse(url).hostname == "api"
    assert "localhost" not in url


def _load_plan(path: Path) -> dict:
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict)
    return data


def test_slow_db_fixture_budget_includes_start_period() -> None:
    plan = _load_plan(FIXTURES / "fx-slow-db" / "compose.yaml")
    budget = compute_readiness_budget_s(plan, "app")
    assert budget >= 80.0
    assert budget <= 180.0


def test_slow_db_boot_waits_with_that_budget(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path / "loadline"))
    seen: dict[str, object] = {}

    def capture_wait(network, url, budget_s, poll_s=2.0, progress=None, **kwargs):
        seen["budget"] = budget_s
        seen["url"] = url
        seen["network"] = network
        return HealthWaitResult(
            ready=True,
            elapsed_s=0.0,
            budget_s=budget_s,
            polls=1,
            last_probe=ProbeResult(ok=True, exit_code=0, http_code=200),
        )

    def fake_compose(*_args, **_kwargs):
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "cid123\n"
        proc.stderr = ""
        return proc

    monkeypatch.setattr("loadline.adapters.runtime.compose_boot._wait_http", capture_wait)
    monkeypatch.setattr("loadline.adapters.runtime.compose_boot._compose_cmd", fake_compose)
    monkeypatch.setattr("loadline.adapters.runtime.compose_boot.create_internal_network", lambda *a, **k: None)
    monkeypatch.setattr("loadline.adapters.runtime.compose_boot.egress_check", lambda *a, **k: True)
    monkeypatch.setattr("loadline.adapters.runtime.compose_boot._egress_from_container", lambda *a, **k: True)

    outcome = boot_repository(FIXTURES / "fx-slow-db", teardown=False, require_auth=False)
    assert outcome.status == "booted"
    assert float(seen["budget"]) >= 80.0
    assert urlparse(str(seen["url"])).hostname == "app"
    assert "localhost" not in str(seen["url"])


def test_bad_config_fixture_is_deterministic_and_writes_attempts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path / "loadline"))
    calls = {"up": 0}

    def fake_compose(_project, _compose_file, _repo, sub, timeout=600):
        proc = MagicMock()
        proc.stdout = ""
        if sub and sub[0] == "up":
            calls["up"] += 1
            proc.returncode = 1
            proc.stderr = "required variable REQUIRED_APP_TOKEN is missing a value: must be set"
        else:
            proc.returncode = 0
            proc.stderr = ""
        return proc

    monkeypatch.setattr("loadline.adapters.runtime.compose_boot._compose_cmd", fake_compose)
    monkeypatch.setattr("loadline.adapters.runtime.compose_boot.create_internal_network", lambda *a, **k: None)
    monkeypatch.setattr("loadline.adapters.runtime.compose_boot.time.sleep", lambda _s: (_ for _ in ()).throw(AssertionError("slept")))

    outcome = boot_repository(FIXTURES / "fx-bad-config", teardown=False, require_auth=False)
    assert calls["up"] == 1
    assert outcome.status == "blocked"
    assert outcome.blocker is not None
    assert outcome.blocker["code"] == "boot_failed"
    assert outcome.blocker["retryable"] is False
    assert len(outcome.attempts) == 1
    assert outcome.run_id is not None
    attempts_path = loadline_home() / "runs" / outcome.run_id / "attempts.json"
    payload = json.loads(attempts_path.read_text())
    assert payload["attempts"][0]["result"] == "boot_failed"
    assert payload["blocker"]["code"] == "boot_failed"


def test_wait_aborts_early_when_abort_check_fires() -> None:
    clock = _Clock()

    def probe() -> ProbeResult:
        return ProbeResult(ok=False, exit_code=28, http_code=0, detail="timeout")

    result = wait_until_http_ready(
        probe,
        145,
        poll_s=2,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        abort_check=lambda: True,
    )
    assert not result.ready
    assert result.elapsed_s == 0.0
    assert result.polls == 0


def test_excerpt_boot_log_surfaces_validation_error_after_rich_trace() -> None:
    filler = "\n".join(f"backend-1  | │ line {i} │" for i in range(80))
    log = (
        filler
        + "\nbackend-1  | pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings\n"
        + "backend-1  | SECRET_KEY\n"
        + "backend-1  |   Field required [type=missing, input_value=...]\n"
    )
    excerpt = excerpt_boot_log(log)
    assert "ValidationError" in excerpt
    assert "Field required" in excerpt
    assert "line 0" not in excerpt


def test_boot_evidence_summary_skips_db_when_app_log_has_error() -> None:
    evidence = BootEvidence(
        health_url="http://app:8000/health",
        budget_s=30,
        elapsed_s=5,
        logs={
            "backend": "backend-1 | ValueError: changethis is not allowed\n",
            "db": "db-1 | PostgreSQL init process complete\n" * 20,
        },
    )
    text = evidence.summary_text()
    assert "logs backend:" in text
    assert "changethis" in text
    assert "logs db:" not in text


def test_wait_http_stops_when_app_container_exited(monkeypatch) -> None:
    from loadline.adapters.runtime.compose_boot import _wait_http

    monkeypatch.setattr(
        "loadline.adapters.runtime.compose_boot._compose_app_ps_state",
        lambda *_a, **_k: "exited",
    )
    monkeypatch.setattr(
        "loadline.adapters.runtime.compose_boot._probe_http_result",
        lambda *_a, **_k: ProbeResult(ok=False, exit_code=28, http_code=0),
    )
    result = _wait_http(
        "net",
        "http://backend:8000/health",
        145,
        project="p",
        compose_file=Path("/tmp/c.yaml"),
        repo=Path("/tmp"),
        app_service="backend",
    )
    assert not result.ready
    assert result.elapsed_s < 5.0
