"""Serialize launch plans for disk and boot JSON (secrets redacted)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from loadline.core.redaction import redact_env
from loadline.core.sandbox_policy import PolicyDiff


def redact_compose_doc(compose_doc: dict[str, Any]) -> dict[str, Any]:
    """Disk-safe compose fragment (services/networks/volumes) with redacted env."""
    out = deepcopy(compose_doc)
    services = out.get("services")
    if isinstance(services, dict):
        out["services"] = {
            name: _redact_service_env(svc) if isinstance(svc, dict) else svc
            for name, svc in services.items()
        }
    return out


def _redact_service_env(svc: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(svc)
    env = out.get("environment")
    if isinstance(env, dict):
        out["environment"] = redact_env({str(k): str(v) for k, v in env.items()})
    elif isinstance(env, list):
        redacted: list[str] = []
        for item in env:
            if isinstance(item, str) and "=" in item:
                key, val = item.split("=", 1)
                redacted.append(f"{key}={redact_env({key: val})[key]}")
            else:
                redacted.append(str(item))
        out["environment"] = redacted
    return out


def export_launch_plan(
    plan: dict[str, Any],
    *,
    run_network: str,
    diffs: list[PolicyDiff],
    build_egress: str = "unrestricted",
) -> dict[str, Any]:
    services_out: list[dict[str, Any]] = []
    for name, svc in (plan.get("services") or {}).items():
        if not isinstance(svc, dict):
            continue
        role = "app" if name == plan.get("x_loadline_app") else "dependency"
        services_out.append(
            {
                "name": name,
                "role": role,
                "spec": _redact_service_env(svc),
            }
        )
    return {
        "services": services_out,
        "network": {"name": run_network, "internal": True},
        "build_egress": build_egress,
        "provenance": [
            {"rule": d.rule, "summary": d.summary, "before": d.before, "after": d.after} for d in diffs
        ],
    }
