from pathlib import Path
from unittest.mock import MagicMock

from loadline.adapters.runtime.compose_boot import (
    _health_failure_detail,
    _healthcheck_budget_s,
    _readiness_budget_s,
)


def test_healthcheck_budget_from_timing():
    svc = {
        "healthcheck": {
            "start_period": "30s",
            "interval": "10s",
            "retries": 5,
        }
    }
    assert _healthcheck_budget_s(svc) == 105.0


def test_readiness_budget_caps_and_includes_slack():
    plan = {
        "services": {
            "app": {
                "depends_on": {"db": {"condition": "service_healthy"}},
                "healthcheck": {"interval": "10s", "retries": 5},
            },
            "db": {
                "healthcheck": {
                    "start_period": "30s",
                    "interval": "10s",
                    "retries": 5,
                }
            },
        }
    }
    budget = _readiness_budget_s(plan, "app")
    assert 80 <= budget <= 180


def test_readiness_budget_default_without_healthcheck():
    plan = {"services": {"app": {"image": "x"}}}
    budget = _readiness_budget_s(plan, "app")
    assert budget >= 30.0
    assert budget != 10.0


def test_health_failure_detail_includes_logs_marker(monkeypatch):
    def fake_compose(*_args, **kwargs):
        sub = kwargs.get("sub") if "sub" in kwargs else _args[3] if len(_args) > 3 else []
        proc = MagicMock()
        proc.returncode = 0
        if sub and sub[0] == "ps":
            proc.stdout = "NAME backend running"
        elif sub and sub[0] == "logs":
            proc.stdout = "Error: connection refused\n"
        else:
            proc.stdout = ""
        proc.stderr = ""
        return proc

    monkeypatch.setattr(
        "loadline.adapters.runtime.compose_boot._compose_cmd",
        lambda project, compose_file, repo, sub, **kw: fake_compose(project, compose_file, repo, sub, **kw),
    )
    detail = _health_failure_detail(
        "p",
        Path("/tmp/compose.yaml"),
        Path("/tmp/repo"),
        {"services": {"app": {"depends_on": ["db"]}, "db": {}}},
        "app",
        "http://app:8000/health",
    )
    assert "compose ps:" in detail
    assert "logs app:" in detail
    assert "connection refused" in detail
