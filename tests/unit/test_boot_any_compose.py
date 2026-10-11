"""Nested compose discovery, HTTP-app inference, hints, and path mapping."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from loadline.adapters.generator.k6_runner import run_k6_plan
from loadline.adapters.runtime.compose_boot import (
    _apply_runtime_hints,
    _http_app_blocker,
    _infer_app_service,
    _resolve_compose_path,
    boot_repository,
)
from loadline.cli import normalize_user_repo_path
from loadline.core.hints import LoadlineHints, slo_from_hints
from loadline.core.readiness import excerpt_compose_up_output
from loadline.core.sandbox_policy import apply_sandbox_policy
from loadline.discovery.intake import discover_profile
from loadline.discovery.workload import discover_workload_operations
from loadline.load_cmd import load_repository


HOH_COMPOSE = """
services:
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    ports: ["2181:2181"]
  kafka:
    image: confluentinc/cp-kafka:7.5.0
    ports: ["9093:9093"]
  redis:
    image: redis:7.2
    ports: ["6379:6379"]
  postgres:
    image: postgres:15
    ports: ["5433:5432"]
  cassandra:
    image: cassandra:4.1
    ports: ["9042:9042"]
    container_name: cassandra
"""


def test_nested_compose_with_app_beats_root_databases(tmp_path: Path):
    (tmp_path / "docker-compose.yml").write_text(HOH_COMPOSE)
    nested = tmp_path / "gemma"
    nested.mkdir()
    (nested / "docker-compose.yml").write_text(
        "services:\n  backend:\n    build: .\n    command: uvicorn app.main:app --port 8000\n"
    )
    profile = discover_profile(tmp_path)
    assert "docker-compose.yml" in profile["compose_files"]
    assert "gemma/docker-compose.yml" in profile["compose_files"]
    chosen = _resolve_compose_path(tmp_path, profile, None)
    assert chosen is not None
    assert chosen.as_posix().endswith("gemma/docker-compose.yml")


def test_hoh_shaped_compose_is_not_cassandra(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path / "loadline"))
    (tmp_path / "docker-compose.yml").write_text(HOH_COMPOSE)
    compose = {
        "services": {
            "zookeeper": {"image": "confluentinc/cp-zookeeper:7.5.0", "ports": ["2181:2181"]},
            "kafka": {"image": "confluentinc/cp-kafka:7.5.0", "ports": ["9093:9093"]},
            "redis": {"image": "redis:7.2", "ports": ["6379:6379"]},
            "postgres": {"image": "postgres:15", "ports": ["5433:5432"]},
            "cassandra": {"image": "cassandra:4.1", "ports": ["9042:9042"]},
        }
    }
    assert _infer_app_service(compose, None) is None
    blocker = _http_app_blocker(compose)
    assert blocker["retryable"] is False
    assert blocker["user_can_provide"] == []
    assert "cassandra" in blocker["summary"]
    outcome = boot_repository(tmp_path, teardown=True, require_auth=False)
    assert outcome.status == "needs_input"
    assert outcome.blocker and outcome.blocker["retryable"] is False
    assert "cassandra" in (outcome.blocker.get("summary") or "")


def test_needs_input_does_not_call_setup(tmp_path: Path, monkeypatch):
    calls: list[int] = []
    from loadline.adapters.runtime.compose_boot import BootOutcome

    outcome = BootOutcome(
        status="needs_input",
        exit_code=9,
        blocker={
            "code": "needs_input",
            "summary": "Compose has no HTTP application. Services are data or messaging: cassandra.",
            "retryable": False,
            "security": False,
            "user_can_provide": [],
            "remediation": [],
        },
    )
    monkeypatch.setattr("loadline.load_cmd.boot_repository", lambda *a, **k: outcome)

    def runner(repo, blocked):
        calls.append(1)
        return blocked

    code = load_repository(tmp_path, require_auth=False, setup_runner=runner)
    assert code == 9
    assert calls == []
    assert not (tmp_path / ".loadline.yaml").exists()


def test_compose_error_excerpt_prefers_failed_line():
    log = (
        " Container redis Creating \n Volume x Creating \n Container zookeeper Creating \n"
        "Error: Conflict. The container name \"/redis\" is already in use\n"
        "failed to create container\n"
    )
    excerpt = excerpt_compose_up_output(log)
    assert "Conflict" in excerpt
    assert "failed to create" in excerpt
    assert not excerpt.startswith(" Container redis Creating")


def test_container_name_is_stripped():
    compose = {
        "x_loadline_app": "app",
        "services": {"app": {"build": ".", "container_name": "cassandra"}},
    }
    result = apply_sandbox_policy(compose, run_network="loadline_run")
    assert result.action == "rewrite"
    assert "container_name" not in result.plan["services"]["app"]
    assert any("container_name" in d.summary for d in result.diffs)


def test_apply_command_and_env_hints():
    raw = {"services": {"app": {"build": ".", "environment": {"A": "1"}}}}
    hints = LoadlineHints.model_validate({"schema_version": "1", "command": "uvicorn app:app", "env": {"B": "2"}})
    _apply_runtime_hints(raw, "app", hints)
    assert raw["services"]["app"]["command"] == "uvicorn app:app"
    assert raw["services"]["app"]["environment"]["B"] == "2"
    policy = apply_sandbox_policy(
        {**raw, "x_loadline_app": "app"},
        run_network="loadline_run",
    )
    assert policy.plan["services"]["app"]["command"] == "uvicorn app:app"


def test_exclude_operations_drops_ids(tmp_path: Path, monkeypatch):
    (tmp_path / ".loadline.yaml").write_text(
        "schema_version: '1'\nexclude_operations:\n  - health\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("loadline.discovery.workload._fetch_live_openapi", lambda *a, **k: None)
    monkeypatch.setattr("loadline.discovery.workload._load_repo_openapi", lambda *_a: None)
    monkeypatch.setattr("loadline.discovery.workload._smoke_operation", lambda *a, **k: True)
    boot = {
        "health": {"url": "http://web:8000/health", "path": "/health"},
        "services": [{"name": "web"}],
    }
    ops = discover_workload_operations(tmp_path, boot, "net")
    assert ops == []


def test_slo_from_hints_and_k6_runner(tmp_path: Path):
    (tmp_path / ".loadline.yaml").write_text(
        "schema_version: '1'\nslo.p95_ms: 150\nslo.err_rate: 0.2\n",
        encoding="utf-8",
    )
    p95, err = slo_from_hints(tmp_path)
    assert p95 == 150.0
    assert err == 0.2
    plan = {
        "mix": [
            {
                "weight": 1,
                "op": {
                    "id": "h",
                    "service": "web",
                    "port": 8000,
                    "selector": {"method": "GET", "path": "/"},
                },
            }
        ],
        "shape": {"rate": 2, "duration": 5},
    }
    payload = {
        "metrics": {
            "http_reqs": {"values": {"rate": 10, "count": 50}},
            "http_req_duration": {"values": {"med": 1, "p(95)": 2, "p(99)": 3}},
            "http_req_failed": {"values": {"rate": 0}},
        },
        "state": {"testRunDurationMs": 5000},
    }
    proc = subprocess.CompletedProcess(["docker"], 0, stdout=json.dumps(payload), stderr="")
    seen: dict[str, float] = {}

    def capture_verdict(metrics):
        seen["slo_p95_ms"] = metrics.slo_p95_ms
        seen["slo_err_rate"] = metrics.slo_err_rate
        return "pass"

    with (
        patch("loadline.adapters.generator.k6_runner.subprocess.run", return_value=proc),
        patch("loadline.adapters.generator.k6_runner.compute_verdict", side_effect=capture_verdict),
    ):
        result = run_k6_plan(
            plan=plan,
            allowed_hosts=frozenset({"web"}),
            network="net-test",
            run_id="rid",
            run_dir=tmp_path,
            wave_name="w1",
            slo_p95_ms=p95,
            slo_err_rate=err,
        )
    assert result.summary.parse_ok
    assert seen["slo_p95_ms"] == 150.0
    assert seen["slo_err_rate"] == 0.2


def test_windows_path_maps_when_mount_exists():
    hoh = Path("/mnt/d/GitHub Repos/HoH")
    if not hoh.exists():
        pytest.skip("WSL mount for HoH is not present")
    got = normalize_user_repo_path(r"D:\GitHub Repos\HoH")
    assert got == hoh.resolve()


def test_existing_path_is_not_remapped(tmp_path: Path):
    assert normalize_user_repo_path(tmp_path) == tmp_path.resolve()


def test_path_strips_embedded_newlines():
    got = normalize_user_repo_path("/tmp/api-\nperformance")
    assert "\n" not in str(got)
    assert got.name == "api-performance"
