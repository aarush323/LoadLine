"""Compose runtime boot on an internal per-run network (S3)."""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import yaml

from loadline.core.hints import LoadlineHints
from loadline.core.readiness import (
    BootEvidence,
    HealthWaitResult,
    ProbeResult,
    compose_up_with_retries,
    compute_readiness_budget_s,
    depends_on_closure,
    depends_on_service_names,
    direct_depends_on,
    duration_seconds,
    health_timeout_blocker,
    healthcheck_budget_s,
    wait_until_http_ready,
)
from loadline.core.env_policy import load_repo_dotenv
from loadline.core.sandbox_policy import apply_sandbox_policy
from loadline.discovery.intake import discover_capabilities, discover_profile, load_compose
from loadline.adapters.runtime.docker_runner import (
    create_internal_network,
    docker_cmd,
    egress_check,
    probe_image,
    remove_labeled,
    tag_compose_labels,
)
from loadline.adapters.runtime.launch_plan import export_launch_plan, redact_compose_doc
from loadline.adapters.observability.postgres import PostgresTarget, postgres_target_from_spec
from loadline.core.data_readiness import DatasetMeasurement
from loadline.adapters.runtime.run_cleanup import RunCleanupState, register_run_cleanup, unregister_run_cleanup
from loadline.paths import allocate_run_dir
from loadline.ui.run_console import BootProgress


def _persist_discovery_artifacts(run_dir: Path, profile: dict[str, Any], capabilities: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "profile.json").write_text(json.dumps(profile, indent=2))
    (run_dir / "capabilities.json").write_text(json.dumps(capabilities, indent=2))


AttemptResult = Literal["success", "boot_failed", "egress_not_enforced", "policy_refused"]


@dataclass
class BootAttempt:
    n: int
    signature: str
    result: AttemptResult
    unblock: str | None = None
    detail: str | None = None


@dataclass
class BootOutcome:
    status: Literal["booted", "blocked", "needs_input"]
    exit_code: int
    blocker: dict[str, Any] | None = None
    attempts: list[BootAttempt] = field(default_factory=list)
    capabilities: dict[str, Any] | None = None
    launch_plan: dict[str, Any] | None = None
    boot: dict[str, Any] | None = None
    run_id: str | None = None


def _anchor_build_contexts(compose: dict[str, Any], repo: Path) -> None:
    services = compose.get("services") or {}
    if not isinstance(services, dict):
        return
    for svc in services.values():
        if not isinstance(svc, dict):
            continue
        build = svc.get("build")
        if isinstance(build, str):
            svc["build"] = str((repo / build).resolve())
        elif isinstance(build, dict):
            ctx = build.get("context", ".")
            build["context"] = str((repo / ctx).resolve())


_HTTP_IN_HEALTHCHECK = re.compile(r"https?://[^:/\s]+:(\d+)(/[^\s'\"\]]*)?", re.I)
_UVICORN_PORT = re.compile(r"--port(?:=|\s+)(\d+)", re.I)

_DB_IMAGE_MARKERS = ("postgres", "mysql", "mariadb", "mongo", "redis", "memcached", "clickhouse")


def _is_dependency_db_image(image: str) -> bool:
    lower = (image or "").lower()
    return any(marker in lower for marker in _DB_IMAGE_MARKERS)


def _service_has_http_port(svc: dict[str, Any]) -> bool:
    return bool(svc.get("ports") or svc.get("expose"))


def _parse_healthcheck_http(svc: dict[str, Any]) -> tuple[int, str] | None:
    hc = svc.get("healthcheck") or {}
    test = hc.get("test")
    if isinstance(test, str):
        parts = [test]
    elif isinstance(test, list):
        parts = [str(x) for x in test]
    else:
        return None
    blob = " ".join(parts)
    match = _HTTP_IN_HEALTHCHECK.search(blob)
    if not match:
        return None
    port = int(match.group(1))
    path = match.group(2) or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    return port, path


def _command_text(svc: dict[str, Any]) -> str:
    cmd = svc.get("command")
    if cmd is None:
        return ""
    if isinstance(cmd, list):
        return " ".join(str(x) for x in cmd)
    return str(cmd)


def _listen_port_from_service(svc: dict[str, Any]) -> int | None:
    match = _UVICORN_PORT.search(_command_text(svc))
    if match:
        return int(match.group(1))
    return None


def _score_app_service_candidate(name: str, svc: dict[str, Any], services: dict[str, Any]) -> int:
    image = str(svc.get("image") or "")
    if _is_dependency_db_image(image):
        return -1
    if not (svc.get("build") or _service_has_http_port(svc)):
        return -1
    score = 0
    for dep in depends_on_service_names(svc):
        dep_svc = services.get(dep)
        if isinstance(dep_svc, dict) and _is_dependency_db_image(str(dep_svc.get("image") or "")):
            score += 40
    cmd = _command_text(svc).lower()
    lname = name.lower()
    if "downstream" in lname or "downstream." in cmd:
        score -= 50
    if "app.main" in cmd or (":app" in cmd and "downstream" not in cmd):
        score += 25
    if lname in ("app", "api", "backend", "web", "server"):
        score += 15
    if lname in ("downstream", "worker", "sidecar", "stub"):
        score -= 20
    return score


def _infer_app_service(compose: dict[str, Any], hints: LoadlineHints | None) -> str | None:
    if hints and hints.app_service:
        return hints.app_service
    services = compose.get("services") or {}
    if not isinstance(services, dict):
        return None
    for name, svc in services.items():
        if isinstance(svc, dict) and _parse_healthcheck_http(svc):
            return name
    ranked: list[tuple[int, str]] = []
    for name, svc in services.items():
        if not isinstance(svc, dict):
            continue
        score = _score_app_service_candidate(name, svc, services)
        if score >= 0:
            ranked.append((score, name))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked[0][1]


def _health_path_candidates(primary: str) -> list[str]:
    paths: list[str] = []
    for candidate in (primary, "/healthz", "/readyz", "/health"):
        if candidate and candidate not in paths:
            paths.append(candidate)
    return paths


def _resolve_compose_path(repo: Path, profile: dict[str, Any], hints: LoadlineHints | None) -> Path | None:
    if hints and hints.compose_file:
        p = repo / hints.compose_file
        return p if p.is_file() else None
    files = profile.get("compose_files") or []
    if files:
        p = repo / files[0]
        return p if p.is_file() else None
    return None


def _health_url(
    app: str,
    hints: LoadlineHints | None,
    service_spec: dict[str, Any] | None = None,
) -> tuple[int, str]:
    parsed = _parse_healthcheck_http(service_spec or {}) if service_spec else None
    if hints and hints.container_port is not None:
        port = hints.container_port
    elif parsed:
        port = parsed[0]
    elif service_spec:
        port_from_cmd = _listen_port_from_service(service_spec)
        port = port_from_cmd if port_from_cmd is not None else 8000
    else:
        port = 8000
    if hints and hints.health_path:
        path = hints.health_path
    elif parsed:
        path = parsed[1]
    else:
        path = "/health"
    return port, path


def _compose_cmd(
    project: str, compose_file: Path, repo: Path, sub: list[str], *, timeout: int = 600
) -> Any:
    import subprocess

    return subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            project,
            "--project-directory",
            str(repo),
            "-f",
            str(compose_file),
            *sub,
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _service_container_id(project: str, compose_file: Path, repo: Path, service: str) -> str | None:
    proc = _compose_cmd(project, compose_file, repo, ["ps", "-q", service], timeout=60)
    cid = (proc.stdout or "").strip().split("\n")[0].strip()
    return cid or None


def _duration_seconds(value: Any) -> float:
    return duration_seconds(value)


def _depends_on_service_names(svc: dict[str, Any]) -> list[str]:
    return depends_on_service_names(svc)


def _healthcheck_budget_s(svc: dict[str, Any]) -> float:
    return healthcheck_budget_s(svc)


def _readiness_budget_s(plan: dict[str, Any], app_service: str) -> float:
    return compute_readiness_budget_s(plan, app_service)


def _depends_on_closure(plan: dict[str, Any], app_service: str) -> list[str]:
    return depends_on_closure(plan, app_service)


def _compose_app_ps_state(
    project: str, compose_file: Path, repo: Path, app_service: str
) -> Literal["running", "exited", "missing"]:
    proc = _compose_cmd(project, compose_file, repo, ["ps", "-a", app_service], timeout=60)
    text = (proc.stdout or proc.stderr or "").strip()
    if not text:
        return "missing"
    body = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("NAME")]
    if not body:
        return "missing"
    joined = "\n".join(body).lower()
    if "exited" in joined:
        return "exited"
    if "up" in joined or "starting" in joined or "restarting" in joined:
        return "running"
    return "missing"


def _wait_http(
    network: str,
    urls: list[str],
    budget_s: float,
    poll_s: float = 2.0,
    progress: BootProgress | None = None,
    *,
    project: str | None = None,
    compose_file: Path | None = None,
    repo: Path | None = None,
    app_service: str | None = None,
) -> tuple[HealthWaitResult, str]:
    primary = urls[0] if urls else ""
    if progress is not None:
        progress.boot_note(f"boot: waiting for {primary} (budget {int(budget_s)}s)")

    def _on_poll(elapsed_s: float, total_s: float) -> None:
        if progress is not None:
            progress.health_tick(elapsed_s, total_s)

    def _abort_app_dead() -> bool:
        if not (project and compose_file and repo and app_service):
            return False
        state = _compose_app_ps_state(project, compose_file, repo, app_service)
        if state == "exited":
            if progress is not None:
                progress.boot_note(f"boot: {app_service} container exited; collecting evidence")
            return True
        if state == "missing":
            if progress is not None:
                progress.boot_note(f"boot: {app_service} container missing; collecting evidence")
            return True
        return False

    successful_url = primary

    def _probe() -> ProbeResult:
        nonlocal successful_url
        last: ProbeResult | None = None
        for url in urls:
            last = _probe_http_result(network, url)
            if last.ok:
                successful_url = url
                return last
        return last if last is not None else ProbeResult(ok=False, exit_code=7, http_code=0, detail="no probe")

    waited = wait_until_http_ready(
        _probe,
        budget_s,
        poll_s=poll_s,
        on_poll=_on_poll,
        abort_check=_abort_app_dead if app_service else None,
    )
    return waited, successful_url if waited.ready else primary


def _compose_cmd_with_ticks(
    project: str,
    compose_file: Path,
    repo: Path,
    sub: list[str],
    *,
    progress: BootProgress | None,
    timeout: int = 600,
) -> Any:
    if progress is None:
        return _compose_cmd(project, compose_file, repo, sub, timeout=timeout)

    start = time.monotonic()
    done = threading.Event()

    def ticker() -> None:
        while not done.wait(15):
            progress.compose_tick(time.monotonic() - start)

    thread = threading.Thread(target=ticker, daemon=True)
    thread.start()
    try:
        return _compose_cmd(project, compose_file, repo, sub, timeout=timeout)
    finally:
        done.set()


def _collect_boot_evidence(
    project: str,
    compose_file: Path,
    repo: Path,
    plan: dict[str, Any],
    app_service: str,
    health_url: str,
    budget_s: float,
    elapsed_s: float,
    last_probe: ProbeResult | None,
) -> BootEvidence:
    ps = _compose_cmd(project, compose_file, repo, ["ps", "-a"], timeout=60)
    ps_text = (ps.stdout or ps.stderr or "").strip()
    logs: dict[str, str] = {}
    for svc in [app_service, *direct_depends_on(plan, app_service)]:
        if svc in logs:
            continue
        proc = _compose_cmd(project, compose_file, repo, ["logs", "--tail=40", svc], timeout=120)
        logs[svc] = (proc.stdout or proc.stderr or "").strip()
    return BootEvidence(
        health_url=health_url,
        budget_s=budget_s,
        elapsed_s=elapsed_s,
        ps_text=ps_text,
        logs=logs,
        last_probe=last_probe,
    )


def _health_failure_detail(
    project: str,
    compose_file: Path,
    repo: Path,
    plan: dict[str, Any],
    app_service: str,
    health_url: str,
    budget_s: float = 0.0,
    elapsed_s: float = 0.0,
    last_probe: ProbeResult | None = None,
) -> str:
    return _collect_boot_evidence(
        project,
        compose_file,
        repo,
        plan,
        app_service,
        health_url,
        budget_s,
        elapsed_s,
        last_probe,
    ).summary_text()


def _parse_http_code(stdout: str) -> int | None:
    lines = (stdout or "").strip().splitlines()
    if not lines:
        return None
    token = lines[-1].strip()
    if token.isdigit():
        return int(token)
    return None


def _probe_http_result(network: str, url: str) -> ProbeResult:
    proc = docker_cmd(
        [
            "run",
            "--rm",
            "--network",
            network,
            probe_image(),
            "curl",
            "-sS",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            "--max-time",
            "5",
            url,
        ],
        timeout=60,
    )
    http_code = _parse_http_code(proc.stdout or "")
    ok = http_code is not None and 200 <= http_code < 300
    return ProbeResult(
        ok=ok,
        exit_code=int(proc.returncode),
        http_code=http_code,
        detail=(proc.stderr or "")[:500],
    )


def _probe_http(network: str, url: str) -> bool:
    return _probe_http_result(network, url).ok


def _egress_from_container(container_id: str) -> bool:
    """True when outbound connect fails (egress denied)."""
    proc = docker_cmd(
        [
            "run",
            "--rm",
            "--network",
            f"container:{container_id}",
            probe_image(),
            "curl",
            "-sf",
            "--max-time",
            "2",
            "http://1.1.1.1",
        ],
        timeout=30,
    )
    return proc.returncode != 0


def _finalize_network_external(plan: dict[str, Any], run_network: str) -> None:
    plan["networks"] = {run_network: {"external": True, "name": run_network}}


def _write_compose(path: Path, plan: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(plan, sort_keys=False))


def _compose_down(project: str, compose_file: Path, repo: Path) -> None:
    _compose_cmd(project, compose_file, repo, ["down", "-v", "--remove-orphans"], timeout=300)


def _teardown(project: str, compose_file: Path, repo: Path, run_id: str) -> None:
    if compose_file.is_file():
        _compose_down(project, compose_file, repo)
    remove_labeled(run_id)
    docker_cmd(["network", "rm", f"loadline_net_{run_id}"], timeout=60)
    if compose_file.is_file():
        compose_file.unlink(missing_ok=True)


def _first_postgres_target(plan: dict[str, Any]) -> PostgresTarget | None:
    for name, spec in (plan.get("services") or {}).items():
        if isinstance(spec, dict):
            target = postgres_target_from_spec(name, spec)
            if target:
                return target
    return None


def _try_measure_postgres_rows(
    project: str, compose_file: Path, repo: Path, target: PostgresTarget
) -> DatasetMeasurement:
    proc = _compose_cmd(
        project,
        compose_file,
        repo,
        [
            "exec",
            "-T",
            target.service,
            "psql",
            "-U",
            target.user,
            "-d",
            target.database,
            "-tAc",
            "SELECT COALESCE(SUM(n_live_tup),0)::bigint FROM pg_stat_user_tables;",
        ],
        timeout=60,
    )
    if proc.returncode != 0:
        return DatasetMeasurement(size=None, source="postgres")
    try:
        return DatasetMeasurement(size=int((proc.stdout or "0").strip() or "0"), source="postgres")
    except ValueError:
        return DatasetMeasurement(size=None, source="postgres")


def labeled_objects_remaining(run_id: str) -> int:
    total = 0
    label = f"loadline.run={run_id}"
    for kind in ("container", "network", "volume"):
        sub = "ps" if kind == "container" else kind
        proc = docker_cmd([sub, "-aq", "--filter", f"label={label}"])
        total += len([x for x in (proc.stdout or "").split() if x])
    return total


def boot_repository(
    repo: Path,
    *,
    hints: LoadlineHints | None = None,
    teardown: bool = True,
    require_auth: bool = True,
    progress: BootProgress | None = None,
) -> BootOutcome:
    if require_auth:
        from loadline.core.auth import require_model_auth

        auth_err = require_model_auth()
        if auth_err:
            return BootOutcome(
                status="needs_input",
                exit_code=2,
                blocker={
                    "code": "needs_input",
                    "summary": auth_err.message,
                    "retryable": False,
                    "security": False,
                    "user_can_provide": [],
                    "remediation": [],
                },
            )

    repo = repo.resolve()
    if hints is None:
        from loadline.core.hints import load_hints as _load_hints

        hints, _ = _load_hints(repo / ".loadline.yaml")
    profile = discover_profile(repo)
    capabilities = discover_capabilities(profile)

    if capabilities.get("blockers"):
        b = capabilities["blockers"][0]
        run_id, run_dir = allocate_run_dir(repo)
        _persist_discovery_artifacts(run_dir, profile, capabilities)
        return _finish_blocked(
            run_dir,
            BootOutcome(
                status="blocked",
                exit_code=10,
                blocker=_capability_blocker(b),
                capabilities=capabilities,
                run_id=run_id,
            ),
        )

    compose_path = _resolve_compose_path(repo, profile, hints)
    if compose_path is None:
        from loadline.adapters.runtime.dockerfile_boot import boot_dockerfile_repository

        return boot_dockerfile_repository(
            repo,
            profile=profile,
            capabilities=capabilities,
            hints=hints,
            teardown=teardown,
        )

    raw = load_compose(compose_path)
    _anchor_build_contexts(raw, repo)
    app_service = _infer_app_service(raw, hints)
    if not app_service:
        run_id, run_dir = allocate_run_dir(repo)
        _persist_discovery_artifacts(run_dir, profile, capabilities)
        return _finish_blocked(
            run_dir,
            BootOutcome(
                status="needs_input",
                exit_code=9,
                blocker={
                    "code": "needs_input",
                    "summary": "No application service found in compose.",
                    "retryable": False,
                    "security": False,
                    "user_can_provide": ["app_service"],
                    "remediation": [{"kind": "hint", "field": "app_service", "reason": "Name the HTTP app service"}],
                },
                capabilities=capabilities,
                run_id=run_id,
            ),
        )

    run_id, run_dir = allocate_run_dir(repo)
    run_network = f"loadline_net_{run_id}"
    project = f"loadline_{run_id}"
    label_key = run_id

    policy_input = dict(raw)
    policy_input["x_loadline_app"] = app_service
    # Phase 9: closure uses started_services; default stays all.
    _start_set = "all"
    try:
        if hints is not None:
            if isinstance(hints, dict):
                _cs = (hints.get("compose") or {})
                _start_set = _cs.get("start_set", "all") if isinstance(_cs, dict) else "all"
            else:
                _cs = getattr(hints, "compose", None)
                _start_set = getattr(_cs, "start_set", "all") or "all"
    except Exception:
        _start_set = "all"
    if _start_set == "closure":
        try:
            from loadline.core.sandbox_policy import closure_started_set

            _started = closure_started_set(raw, app_service)
        except Exception:
            _started = None
        if _started is None:
            policy = apply_sandbox_policy(
                policy_input,
                run_network=run_network,
                repo_dotenv=load_repo_dotenv(repo),
            )
        else:
            policy = apply_sandbox_policy(
                policy_input,
                run_network=run_network,
                repo_dotenv=load_repo_dotenv(repo),
                started_services=set(_started),
            )
    else:
        policy = apply_sandbox_policy(
            policy_input,
            run_network=run_network,
            repo_dotenv=load_repo_dotenv(repo),
        )
    if progress is not None:
        if policy.action == "refuse":
            progress.boot_note(f"boot: sandbox policy refused ({policy.blocker_code})")
        else:
            progress.boot_note("boot: sandbox policy ok")
    if policy.action == "refuse":
        needs = policy.blocker_code == "needs_input"
        _persist_discovery_artifacts(run_dir, profile, capabilities)
        return _finish_blocked(
            run_dir,
            BootOutcome(
                status="needs_input" if needs else "blocked",
                exit_code=9 if needs else 10,
                blocker={
                    "code": policy.blocker_code or "policy_refused",
                    "summary": policy.blocker_summary or "Sandbox policy refused the plan.",
                    "retryable": False,
                    "security": not needs and (policy.blocker_code == "policy_refused"),
                    "user_can_provide": [] if not needs else ["env"],
                    "remediation": [],
                },
                capabilities=capabilities,
                run_id=run_id,
            ),
        )

    plan = tag_compose_labels(dict(policy.plan or {}), label_key)
    _finalize_network_external(plan, run_network)
    app_marker = plan.pop("x_loadline_app", app_service)
    compose_doc = {k: v for k, v in plan.items() if k in ("services", "networks", "volumes", "name")}
    validated_path = run_dir / "launch_plan.validated.yaml"
    runtime_compose_path = run_dir / "compose.runtime.yaml"
    _write_compose(runtime_compose_path, compose_doc)
    _write_compose(validated_path, redact_compose_doc(compose_doc))
    plan["x_loadline_app"] = app_marker
    launch_plan = export_launch_plan(plan, run_network=run_network, diffs=policy.diffs)
    (run_dir / "launch_plan.json").write_text(json.dumps(launch_plan, indent=2))
    (run_dir / "profile.json").write_text(json.dumps(profile, indent=2))
    (run_dir / "capabilities.json").write_text(json.dumps(capabilities, indent=2))

    if progress is not None:
        progress.boot_note(f"boot: internal network {run_network}")
    net_err = create_internal_network(run_network, run_id=label_key)
    if net_err:
        return _finish_blocked(
            run_dir,
            BootOutcome(
                status="blocked",
                exit_code=7,
                blocker={
                    "code": "boot_failed",
                    "summary": net_err.message,
                    "retryable": True,
                    "security": False,
                    "user_can_provide": [],
                    "remediation": [],
                },
                capabilities=capabilities,
                launch_plan=launch_plan,
                run_id=run_id,
            ),
        )

    attempts: list[BootAttempt] = []
    app_spec = (raw.get("services") or {}).get(app_service) if isinstance(raw.get("services"), dict) else None
    app_spec = app_spec if isinstance(app_spec, dict) else {}
    port, health_path = _health_url(app_service, hints, app_spec)
    health_urls = [f"http://{app_service}:{port}{path}" for path in _health_path_candidates(health_path)]
    health_url = health_urls[0]
    readiness_budget_s = _readiness_budget_s(plan, app_service)
    sig = f"compose_up:{compose_path.name}"

    register_run_cleanup(
        RunCleanupState(
            run_id=run_id,
            extra=lambda: _teardown(project, runtime_compose_path, repo, run_id),
        )
    )
    try:
        if progress is not None:
            progress.boot_note("boot: compose up --build")

        def _run_up() -> Any:
            return _compose_cmd_with_ticks(
                project,
                runtime_compose_path,
                repo,
                ["up", "-d", "--build"],
                progress=progress,
                timeout=900,
            )

        up, up_failures = compose_up_with_retries(_run_up, sleep=time.sleep)
        compose_class = up_failures[-1].failure_class if up_failures else None
        for failure in up_failures:
            attempts.append(
                BootAttempt(
                    n=failure.n,
                    signature=sig,
                    result="boot_failed",
                    detail=failure.output[:500],
                )
            )

        health_evidence: BootEvidence | None = None
        if getattr(up, "returncode", 1) == 0:
            next_n = len(attempts) + 1
            if not egress_check(probe_image(), run_network):
                if progress is not None:
                    progress.boot_note("boot: egress check failed (probe)")
                attempts.append(
                    BootAttempt(n=next_n, signature=sig, result="egress_not_enforced", detail="probe egress")
                )
            else:
                app_cid = _service_container_id(project, runtime_compose_path, repo, app_service)
                egress_failed = not app_cid or not _egress_from_container(app_cid)
                if egress_failed:
                    attempts.append(
                        BootAttempt(n=next_n, signature=sig, result="egress_not_enforced", detail="app egress")
                    )
                else:
                    for dep in _depends_on_closure(plan, app_service):
                        if dep == app_service:
                            continue
                        dep_cid = _service_container_id(project, runtime_compose_path, repo, dep)
                        if dep_cid and not _egress_from_container(dep_cid):
                            attempts.append(
                                BootAttempt(
                                    n=next_n,
                                    signature=sig,
                                    result="egress_not_enforced",
                                    detail=f"dependency egress {dep}",
                                )
                            )
                            egress_failed = True
                            break
                    if not egress_failed:
                        waited, health_url = _wait_http(
                            run_network,
                            health_urls,
                            readiness_budget_s,
                            progress=progress,
                            project=project,
                            compose_file=runtime_compose_path,
                            repo=repo,
                            app_service=app_service,
                        )
                        health_path = urlparse(health_url).path or health_path
                        if not waited.ready:
                            health_evidence = _collect_boot_evidence(
                                project,
                                runtime_compose_path,
                                repo,
                                plan,
                                app_service,
                                health_url,
                                readiness_budget_s,
                                waited.elapsed_s,
                                waited.last_probe,
                            )
                            attempts.append(
                                BootAttempt(
                                    n=next_n,
                                    signature=sig,
                                    result="boot_failed",
                                    detail=health_evidence.summary_text(),
                                )
                            )
                        else:
                            if progress is not None:
                                progress.boot_note("boot: healthy")
                            pg_target = _first_postgres_target(plan)
                            if pg_target:
                                _try_measure_postgres_rows(project, runtime_compose_path, repo, pg_target)
                            attempts.append(BootAttempt(n=next_n, signature=sig, result="success"))
                            boot_info = {
                                "health": {"status": "ok", "url": health_url, "path": health_path},
                                "services": [
                                    {"name": name, "role": "app" if name == app_service else "dependency"}
                                    for name in (plan.get("services") or {})
                                ],
                                "run_id": run_id,
                                "run_dir": str(run_dir),
                                "network": run_network,
                            }
                            # Phase 9: list not_started when closure filtered the plan.
                            try:
                                _ns = list(getattr(policy, "not_started", []) or [])
                                if _ns:
                                    boot_info["not_started"] = _ns
                            except Exception:
                                pass
                            return BootOutcome(
                                status="booted",
                                exit_code=0,
                                attempts=attempts,
                                capabilities=capabilities,
                                launch_plan=launch_plan,
                                boot=boot_info,
                                run_id=run_id,
                            )

        last = attempts[-1] if attempts else BootAttempt(1, "compose_up", "boot_failed")
        if health_evidence is not None:
            blocker = health_timeout_blocker(health_evidence)
            exit_code = 7
        elif last.result == "boot_failed":
            blocker = {
                "code": "boot_failed",
                "summary": last.detail or last.result,
                "retryable": compose_class == "transient",
                "security": False,
                "user_can_provide": [],
                "remediation": [],
            }
            exit_code = 7
        else:
            blocker = {
                "code": last.result,
                "summary": last.detail or last.result,
                "retryable": False,
                "security": last.result == "policy_refused",
                "user_can_provide": [],
                "remediation": [],
            }
            exit_code = 4
        return _finish_blocked(
            run_dir,
            BootOutcome(
                status="blocked",
                exit_code=exit_code,
                blocker=blocker,
                attempts=attempts,
                capabilities=capabilities,
                launch_plan=launch_plan,
                run_id=run_id,
            ),
        )
    finally:
        unregister_run_cleanup()
        if teardown:
            _teardown(project, runtime_compose_path, repo, run_id)


def _capability_blocker(b: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": b["code"],
        "summary": b["summary"],
        "retryable": b["code"] not in ("policy_refused",),
        "security": False,
        "user_can_provide": b.get("user_can_provide", []),
        "remediation": [
            {"kind": "hint", "field": "compose_file", "reason": b["summary"]}
        ]
        if "compose_file" in b.get("user_can_provide", [])
        else [],
    }


def persist_blocked_attempts(
    run_dir: Path, attempts: list[BootAttempt], blocker: dict[str, Any] | None
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {"attempts": attempts_to_json(attempts), "blocker": blocker}
    (run_dir / "attempts.json").write_text(json.dumps(payload, indent=2))


def _finish_blocked(run_dir: Path | None, outcome: BootOutcome) -> BootOutcome:
    if run_dir is not None and outcome.run_id and outcome.status != "booted":
        persist_blocked_attempts(run_dir, outcome.attempts, outcome.blocker)
    return outcome


def attempts_to_json(attempts: list[BootAttempt]) -> list[dict[str, Any]]:
    return [
        {
            "n": a.n,
            "signature": a.signature,
            "result": a.result,
            "unblock": a.unblock,
            **({"detail": a.detail} if a.detail else {}),
        }
        for a in attempts
    ]
