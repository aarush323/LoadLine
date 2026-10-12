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
    notes: list[str] = field(default_factory=list)
    not_started: list[str] = field(default_factory=list)


def _env_values_of_service(svc: dict[str, Any]) -> list[str]:
    env = svc.get("environment")
    if isinstance(env, dict):
        return [str(v) for v in env.values() if isinstance(v, (str, int, float))]
    if isinstance(env, list):
        out: list[str] = []
        for item in env:
            if isinstance(item, str) and "=" in item:
                out.append(item.split("=", 1)[1])
            elif isinstance(item, str):
                out.append(item)
        return out
    return []


def _hostname_tokens(text: str) -> set[str]:
    import re
    from urllib.parse import urlparse

    tokens: set[str] = set()
    # URL hostnames.
    for m in re.finditer(r"https?://([^:/\s'\"]+)", text):
        host = m.group(1).strip()
        if host:
            tokens.add(host)
            # Also add without port? Already host only.
    # Whole tokens split by non-alphanumeric (keep - _ . for splitting? Must not substring-match).
    # Split on anything except alnum, -, _; then compare whole token equality by caller.
    for tok in re.split(r"[^A-Za-z0-9_-]+", text):
        if tok:
            tokens.add(tok)
    # Also try urlparse for each whitespace piece.
    for piece in text.split():
        try:
            p = urlparse(piece if "://" in piece else f"http://{piece}")
            if p.hostname:
                tokens.add(p.hostname)
        except (ValueError, AttributeError):
            pass
    return tokens


def closure_started_set(compose: dict[str, Any], target: str) -> set[str]:
    """Target + transitive depends_on + whole-hostname-token env matches. No command scan."""
    from loadline.core.readiness import depends_on_service_names

    services = compose.get("services") or {}
    if not isinstance(services, dict) or target not in services:
        return {target} if target else set()
    started: set[str] = {target}
    # Transitive depends_on.
    queue = [target]
    while queue:
        cur = queue.pop()
        svc = services.get(cur)
        if not isinstance(svc, dict):
            continue
        for dep in depends_on_service_names(svc):
            if dep not in started and dep in services:
                started.add(dep)
                queue.append(dep)
    # Hostname tokens from target env only (not command, not config files).
    tgt_svc = services.get(target)
    env_texts = _env_values_of_service(tgt_svc) if isinstance(tgt_svc, dict) else []
    combined = "\n".join(env_texts)
    tokens = _hostname_tokens(combined)
    for name in services:
        if name in started:
            continue
        # Whole-token match only; "app" must not match inside another token.
        if name in tokens:
            started.add(name)
            # Add its transitive deps as well.
            queue = [name]
            while queue:
                cur = queue.pop()
                svc = services.get(cur)
                if not isinstance(svc, dict):
                    continue
                for dep in depends_on_service_names(svc):
                    if dep not in started and dep in services:
                        started.add(dep)
                        queue.append(dep)
    return started


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
    started_services: set[str] | None = None,
) -> PolicyResult:
    """Mutate a compose dict in place conceptually; returns validated copy."""
    # Golden path: None or all behaves as today.
    if started_services is not None and len(started_services) == 0:
        started_services = set()
    plan = deepcopy(compose)
    diffs: list[PolicyDiff] = []
    notes: list[str] = []
    shared_generated: dict[str, str] = {}
    services = plan.get("services") or {}
    if not isinstance(services, dict):
        return PolicyResult(action="refuse", blocker_code="policy_refused", blocker_summary="services must be a mapping")

    if started_services is None:
        # Today's refuse/drop behavior unchanged.
        drop_outcome = _drop_unsandboxable_host_bind_services(plan, diffs)
        if drop_outcome is not None:
            return drop_outcome

        services = plan.get("services") or {}

    else:
        # Closure: outside started set violations become notes, not refuses.
        all_names = set((plan.get("services") or {}).keys())
        started = set(started_services) & all_names
        not_started = sorted(all_names - started)
        # Record not_started and drop them from plan (they will not start).
        for ns in not_started:
            svc = (plan.get("services") or {}).get(ns)
            # Violation outside → note (including ipc:host and docker socket).
            note = None
            if isinstance(svc, dict):
                if svc.get("privileged"):
                    note = f"service {ns} requests privileged mode"
                elif svc.get("devices"):
                    note = f"service {ns} requests devices"
                elif svc.get("cap_add"):
                    note = f"service {ns} adds capabilities"
                elif any(k in svc and svc[k] in ("host", "container:host") for k in ("pid", "ipc", "network_mode")):
                    for k in ("pid", "ipc", "network_mode"):
                        if k in svc and svc[k] in ("host", "container:host"):
                            note = f"service {ns} uses host {k}"
                            break
                elif _service_has_host_bind(svc):
                    # Docker socket (/var/run/docker.sock) follows same rule.
                    note = f"service {ns} has a host bind mount"
                elif svc.get("network_mode"):
                    note = f"service {ns} sets network_mode"
                elif any("host-gateway" in str(x) for x in (svc.get("extra_hosts") or [])):
                    note = f"service {ns} uses host-gateway"
            if note:
                notes.append(f"note (not started): {note}")
                diffs.append(PolicyDiff(2, f"note (not started): {note}", ns, None))
            else:
                diffs.append(PolicyDiff(2, f"not started: {ns}", ns, None))
            (plan.get("services") or {}).pop(ns, None)
        # Strip depends_on refs to not_started.
        for _name, _svc in list((plan.get("services") or {}).items()):
            if not isinstance(_svc, dict):
                continue
            if "depends_on" in _svc:
                updated = _strip_depends_on(_svc.get("depends_on"), set(not_started))
                if updated is None:
                    _svc.pop("depends_on", None)
                else:
                    _svc["depends_on"] = updated
        services = plan.get("services") or {}
        # Continue to per-service checks below (inside set still refuses).
        # Attach not_started for return.
        plan["_loadline_not_started"] = not_started

    for name, svc in list(services.items()):
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
        if "container_name" in svc:
            diffs.append(
                PolicyDiff(3, f"dropped container_name on {name}", svc.get("container_name"), None)
            )
            svc.pop("container_name", None)
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

    not_started_out = list(plan.pop("_loadline_not_started", [])) if isinstance(plan, dict) else []
    if started_services is None:
        return PolicyResult(action="rewrite", plan=plan, diffs=diffs)
    return PolicyResult(action="rewrite", plan=plan, diffs=diffs, notes=notes, not_started=not_started_out)
