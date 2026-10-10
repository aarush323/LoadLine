"""SandboxPolicy on launch plans (tech_doc.md §7.4)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Literal

from loadline.constants import (
    CPU_SAFETY_CEILING,
    DEFAULT_APP_CPUS,
    DEFAULT_APP_MEM,
    DEFAULT_DEP_CPUS,
    DEFAULT_DEP_MEM,
    DEFAULT_PIDS,
)
from loadline.core.env_policy import apply_env_policy

Action = Literal["allow", "rewrite", "refuse"]


@dataclass
class PolicyDiff:
    rule: int
    summary: str
    before: Any = None
    after: Any = None


@dataclass
class PolicyResult:
    action: Action
    plan: dict[str, Any] | None = None
    diffs: list[PolicyDiff] = field(default_factory=list)
    blocker_code: str | None = None
    blocker_summary: str | None = None


def _service_resources(service: dict[str, Any], role: str) -> None:
    deploy = service.setdefault("deploy", {})
    resources = deploy.setdefault("resources", {})
    limits = resources.setdefault("limits", {})
    cpus = limits.get("cpus")
    if cpus is None:
        limits["cpus"] = str(DEFAULT_APP_CPUS if role == "app" else DEFAULT_DEP_CPUS)
    else:
        try:
            val = float(cpus)
            if val > CPU_SAFETY_CEILING:
                limits["cpus"] = str(CPU_SAFETY_CEILING)
        except (TypeError, ValueError):
            limits["cpus"] = str(DEFAULT_APP_CPUS)
    if "memory" not in limits:
        limits["memory"] = DEFAULT_APP_MEM if role == "app" else DEFAULT_DEP_MEM
    if "pids" not in limits:
        limits["pids"] = DEFAULT_PIDS


def _volume_is_host_bind(vol: Any) -> bool:
    if isinstance(vol, str):
        src = vol.split(":")[0]
        return bool(src.startswith("/"))
    return False


def _service_has_host_bind(svc: dict[str, Any]) -> bool:
    for vol in svc.get("volumes") or []:
        if _volume_is_host_bind(vol):
            return True
    return False


def _strip_depends_on(depends_on: Any, removed: set[str]) -> Any:
    if depends_on is None:
        return None
    if isinstance(depends_on, list):
        kept = [d for d in depends_on if d not in removed]
        return kept if kept else None
    if isinstance(depends_on, dict):
        kept = {k: v for k, v in depends_on.items() if k not in removed}
        return kept if kept else None
    return depends_on


def _drop_unsandboxable_host_bind_services(
    plan: dict[str, Any], diffs: list[PolicyDiff]
) -> PolicyResult | None:
    """Remove auxiliary services with host bind mounts; refuse if app or nothing remains."""
    services = plan.get("services") or {}
    if not isinstance(services, dict):
        return PolicyResult(action="refuse", blocker_code="policy_refused", blocker_summary="services must be a mapping")

    app_name = plan.get("x_loadline_app")
    unsafe = {name for name, svc in services.items() if isinstance(svc, dict) and _service_has_host_bind(svc)}
    if not unsafe:
        return None

    if app_name in unsafe:
        return PolicyResult(
            action="refuse",
            blocker_code="policy_refused",
            blocker_summary=f"service {app_name} has a host bind mount",
        )

    safe_names = [n for n in services if n not in unsafe]
    if not safe_names:
        first = next(iter(unsafe))
        return PolicyResult(
            action="refuse",
            blocker_code="policy_refused",
            blocker_summary=f"service {first} has a host bind mount",
        )

    for name in unsafe:
        diffs.append(PolicyDiff(2, f"dropped service {name} (host bind mount)", name, None))
        services.pop(name, None)

    for name, svc in list(services.items()):
        if not isinstance(svc, dict):
            continue
        if "depends_on" in svc:
            updated = _strip_depends_on(svc.get("depends_on"), unsafe)
            if updated is None:
                svc.pop("depends_on", None)
            else:
                svc["depends_on"] = updated

    return None


def apply_sandbox_policy(
    compose: dict[str, Any],
    *,
    run_network: str,
    repo_dotenv: dict[str, str] | None = None,
) -> PolicyResult:
    """Mutate a compose dict in place conceptually; returns validated copy."""
    plan = deepcopy(compose)
    diffs: list[PolicyDiff] = []
    shared_generated: dict[str, str] = {}
    services = plan.get("services") or {}
    if not isinstance(services, dict):
        return PolicyResult(action="refuse", blocker_code="policy_refused", blocker_summary="services must be a mapping")

    drop_outcome = _drop_unsandboxable_host_bind_services(plan, diffs)
    if drop_outcome is not None:
        return drop_outcome

    services = plan.get("services") or {}

    for name, svc in services.items():
        if not isinstance(svc, dict):
            continue
        if svc.get("privileged"):
            return PolicyResult(
                action="refuse",
                blocker_code="policy_refused",
                blocker_summary=f"service {name} requests privileged mode",
            )
        if svc.get("devices"):
            return PolicyResult(
                action="refuse",
                blocker_code="policy_refused",
                blocker_summary=f"service {name} requests devices",
            )
        cap_add = svc.get("cap_add") or []
        if cap_add:
            return PolicyResult(
                action="refuse",
                blocker_code="policy_refused",
                blocker_summary=f"service {name} adds capabilities",
            )
        for forbidden in ("pid", "ipc", "network_mode"):
            if forbidden in svc and svc[forbidden] in ("host", "container:host"):
                return PolicyResult(
                    action="refuse",
                    blocker_code="policy_refused",
                    blocker_summary=f"service {name} uses host {forbidden}",
                )
        ports = svc.get("ports") or []
        if ports:
            diffs.append(PolicyDiff(3, f"removed published ports on {name}", ports, []))
            svc["ports"] = []
        extra = svc.get("extra_hosts") or []
        if any("host-gateway" in str(x) for x in extra):
            return PolicyResult(
                action="refuse",
                blocker_code="policy_refused",
                blocker_summary=f"service {name} uses host-gateway",
            )
        if svc.get("network_mode"):
            return PolicyResult(
                action="refuse",
                blocker_code="policy_refused",
                blocker_summary=f"service {name} sets network_mode",
            )
        svc["networks"] = [run_network]
        role = "app" if name == plan.get("x_loadline_app") else "dependency"
        _service_resources(svc, role)
        if "environment" in svc:
            env_outcome = apply_env_policy(
                svc.get("environment"),
                repo_dotenv=repo_dotenv,
                generated=shared_generated,
            )
            if env_outcome.needs_input:
                return PolicyResult(
                    action="refuse",
                    blocker_code="needs_input",
                    blocker_summary=env_outcome.needs_input_summary or "credential requires user input",
                )
            for key in env_outcome.generated_secrets:
                diffs.append(PolicyDiff(7, f"generated local secret {key} on {name}", "[redacted]", "[redacted]"))
            if env_outcome.replacements:
                for key, old, new in env_outcome.replacements:
                    if key in env_outcome.generated_secrets:
                        continue
                    if new == "" and old:
                        summary = f"cleared literal credential env {key} on {name}"
                    else:
                        summary = f"rewrote env {key} on {name}"
                    diffs.append(PolicyDiff(7, summary, old, new))
            if env_outcome.env and svc.get("environment") is not None:
                svc["environment"] = (
                    env_outcome.env
                    if isinstance(svc.get("environment"), dict)
                    else [f"{k}={v}" for k, v in env_outcome.env.items()]
                )

    networks = plan.setdefault("networks", {})
    for key, net in list(networks.items()):
        if key == run_network:
            continue
        if isinstance(net, dict) and net.get("external"):
            return PolicyResult(
                action="refuse",
                blocker_code="policy_refused",
                blocker_summary=f"external network {key} is not allowed",
            )
        if key != run_network:
            diffs.append(PolicyDiff(4, f"dropped network {key}", key, None))
    networks[run_network] = {"internal": True}
    plan["networks"] = {run_network: networks[run_network]}

    return PolicyResult(action="rewrite", plan=plan, diffs=diffs)
