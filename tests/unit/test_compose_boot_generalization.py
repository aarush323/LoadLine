"""Generalized compose boot helpers (healthcheck, app selection, postgres creds)."""

from loadline.adapters.observability.postgres import postgres_target_from_spec
from loadline.adapters.runtime.compose_boot import (
    _health_path_candidates,
    _health_url,
    _infer_app_service,
    _listen_port_from_service,
    _parse_healthcheck_http,
)
from loadline.neatlogs_setup import LOADLINE_WORKFLOW
from loadline.neatlogs_workflows import CAPACITY_INVESTIGATION


def test_healthcheck_http_parsed_for_probe_url():
    svc = {
        "healthcheck": {
            "test": ["CMD", "curl", "-f", "http://localhost:8000/api/v1/utils/health-check/"],
        }
    }
    assert _parse_healthcheck_http(svc) == (8000, "/api/v1/utils/health-check/")
    port, path = _health_url("backend", None, svc)
    assert port == 8000
    assert path == "/api/v1/utils/health-check/"


def test_infer_app_service_prefers_healthcheck_over_name():
    compose = {
        "services": {
            "web": {"image": "nginx"},
            "backend": {
                "build": ".",
                "healthcheck": {
                    "test": "curl -f http://localhost:8000/health/",
                },
            },
        }
    }
    assert _infer_app_service(compose, None) == "backend"


def test_postgres_target_uses_env_not_fixture_literals():
    spec = {
        "image": "postgres:16",
        "environment": {"POSTGRES_USER": "myuser", "POSTGRES_DB": "mydb"},
    }
    target = postgres_target_from_spec("db", spec)
    assert target is not None
    assert target.user == "myuser"
    assert target.database == "mydb"


def test_postgres_target_missing_credentials_not_measured():
    spec = {"image": "postgres:16", "environment": {"POSTGRES_DB": "app"}}
    assert postgres_target_from_spec("db", spec) is None


def test_loadline_workflow_import():
    assert LOADLINE_WORKFLOW == CAPACITY_INVESTIGATION


def test_infer_app_service_prefers_db_backed_app_over_downstream():
    compose = {
        "services": {
            "db": {"image": "postgres:16-alpine"},
            "downstream": {
                "build": ".",
                "command": "uvicorn downstream.main:app --host 0.0.0.0 --port 9000",
            },
            "app": {
                "build": ".",
                "depends_on": {"db": {"condition": "service_healthy"}},
            },
        }
    }
    assert _infer_app_service(compose, None) == "app"


def test_listen_port_from_uvicorn_command():
    svc = {"command": "uvicorn downstream.main:app --host 0.0.0.0 --port 9000"}
    assert _listen_port_from_service(svc) == 9000


def test_health_path_candidates_include_healthz():
    assert _health_path_candidates("/health")[:3] == ["/health", "/healthz", "/readyz"]


def test_health_url_uses_command_port_when_no_healthcheck():
    svc = {"command": "uvicorn app.main:app --host 0.0.0.0 --port 8000"}
    port, path = _health_url("app", None, svc)
    assert port == 8000
    assert path == "/health"
