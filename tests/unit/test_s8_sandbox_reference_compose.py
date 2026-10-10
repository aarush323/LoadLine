"""Reference template: drop Traefik proxy (docker.sock), keep app stack."""

from pathlib import Path

import yaml

from loadline.core.sandbox_policy import apply_sandbox_policy

TARGET = Path(__file__).resolve().parents[2] / "integration" / "targets" / "full-stack-fastapi-template"


def test_reference_compose_proxy_dropped_backend_and_db_remain():
    compose_path = TARGET / "compose.yml"
    if not compose_path.is_file():
        return
    doc = yaml.safe_load(compose_path.read_text())
    services = doc.get("services") or {}
    if "proxy" not in services:
        return
    compose = {
        "x_loadline_app": "backend",
        "services": {
            "proxy": services["proxy"],
            "backend": {"image": "backend:latest", "build": "."},
            "db": services["db"],
        },
    }
    result = apply_sandbox_policy(compose, run_network="loadline-net-test")
    assert result.action == "rewrite"
    assert result.plan is not None
    kept = result.plan["services"]
    assert "proxy" not in kept
    assert "backend" in kept
    assert "db" in kept
    dumped = yaml.safe_dump(result.plan)
    assert "docker.sock" not in dumped
