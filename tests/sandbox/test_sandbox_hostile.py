"""SandboxPolicy hostile compose plans (S3 gate)."""

from __future__ import annotations

import pytest
import yaml

from loadline.core.sandbox_policy import apply_sandbox_policy

NET = "loadline_run_test"


def _refuse(compose: dict) -> None:
    result = apply_sandbox_policy(compose, run_network=NET)
    assert result.action == "refuse"


def _rewrite(compose: dict) -> None:
    result = apply_sandbox_policy(compose, run_network=NET)
    assert result.action == "rewrite"
    assert result.plan is not None


@pytest.mark.parametrize(
    "compose",
    [
        {"services": {"w": {"image": "x", "privileged": True}}},
        {"services": {"w": {"image": "x", "cap_add": ["SYS_ADMIN"]}}},
        {"services": {"w": {"image": "x", "pid": "host"}}},
        {"services": {"w": {"image": "x", "ipc": "host"}}},
        {"services": {"w": {"image": "x", "network_mode": "host"}}},
        {"services": {"w": {"image": "x", "volumes": ["/etc/passwd:/etc/passwd:ro"]}}},
        {"services": {"w": {"image": "x", "volumes": ["/var/run/docker.sock:/var/run/docker.sock"]}}},
        {"services": {"w": {"image": "x", "extra_hosts": ["host.docker.internal:host-gateway"]}}},
        {"services": {"w": {"image": "x", "network_mode": "bridge"}}},
        {
            "services": {"w": {"image": "x"}},
            "networks": {"outside": {"external": True}},
        },
        {"services": {"w": {"image": "x", "devices": ["/dev/kvm"]}}},
    ],
)
def test_hostile_compose_refused(compose: dict):
    _refuse(compose)


@pytest.mark.parametrize(
    "ports",
    [
        ["8000:8000"],
        ["0.0.0.0:8000:8000"],
        ["127.0.0.1:8000:8000"],
    ],
)
def test_published_ports_rewritten(ports: list[str]):
    compose = {"services": {"web": {"image": "x", "ports": ports}}}
    _rewrite(compose)
    result = apply_sandbox_policy(compose, run_network=NET)
    assert result.plan["services"]["web"]["ports"] == []


def test_all_services_on_run_network():
    compose = {
        "services": {
            "web": {"image": "x"},
            "db": {"image": "postgres:16"},
        }
    }
    result = apply_sandbox_policy(compose, run_network=NET)
    assert result.plan["services"]["web"]["networks"] == [NET]
    assert result.plan["services"]["db"]["networks"] == [NET]
    assert result.plan["networks"][NET]["internal"] is True


def test_resource_limits_added():
    compose = {"services": {"web": {"image": "x"}}, "x_loadline_app": "web"}
    result = apply_sandbox_policy(compose, run_network=NET)
    limits = result.plan["services"]["web"]["deploy"]["resources"]["limits"]
    assert "cpus" in limits
    assert "memory" in limits


def test_prod_url_in_env_rewritten():
    compose = {
        "services": {
            "web": {
                "image": "x",
                "environment": {"API_URL": "https://service.prod.amazonaws.com/v1"},
            }
        }
    }
    result = apply_sandbox_policy(compose, run_network=NET)
    assert result.action == "rewrite"
    env = result.plan["services"]["web"]["environment"]
    assert "amazonaws.com" not in env["API_URL"]
    assert "sandbox.invalid" in env["API_URL"]


def test_host_bind_sidecar_dropped_app_remains():
    compose = {
        "x_loadline_app": "api",
        "services": {
            "api": {"image": "myapp", "build": "."},
            "proxy": {
                "image": "traefik",
                "volumes": ["/var/run/docker.sock:/var/run/docker.sock"],
            },
        },
    }
    result = apply_sandbox_policy(compose, run_network=NET)
    assert result.action == "rewrite"
    assert "proxy" not in result.plan["services"]
    assert "api" in result.plan["services"]
    assert "docker.sock" not in yaml.safe_dump(result.plan)


def test_literal_api_key_cleared_on_rewrite():
    compose = {
        "services": {
            "web": {
                "image": "x",
                "environment": {"STRIPE_SECRET_KEY": "sk_live_abcdefghijklmnop"},
            }
        }
    }
    result = apply_sandbox_policy(compose, run_network=NET)
    assert result.action == "rewrite"
    assert result.plan["services"]["web"]["environment"]["STRIPE_SECRET_KEY"] == ""
