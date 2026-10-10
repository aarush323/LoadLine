"""Dockerfile-only runtime boot (tech_doc.md §7.5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loadline.constants import DEFAULT_APP_CPUS, DEFAULT_APP_MEM, DEFAULT_PIDS
from loadline.core.data_readiness import DatasetMeasurement, ReadOperation, evaluate_data_readiness
from loadline.core.hints import LoadlineHints
from loadline.core.readiness import (
    BootEvidence,
    dockerfile_readiness_budget_s,
    health_timeout_blocker,
    wait_until_http_ready,
)
from loadline.adapters.runtime.compose_boot import (
    BootAttempt,
    BootOutcome,
    _capability_blocker,
    _egress_from_container,
    _health_url,
    _probe_http_result,
    attempts_to_json,
    labeled_objects_remaining,
    persist_blocked_attempts,
)
from loadline.adapters.runtime.docker_runner import (
    create_internal_network,
    docker_cmd,
    egress_check,
    probe_image,
    remove_labeled,
)
from loadline.adapters.runtime.launch_plan import export_launch_plan
from loadline.adapters.runtime.run_cleanup import register_run_cleanup, teardown_run, unregister_run_cleanup
from loadline.adapters.runtime.run_cleanup import RunCleanupState
from loadline.paths import allocate_run_dir

APP_NAME = "app"


def _resolve_dockerfile(repo: Path, profile: dict[str, Any], hints: LoadlineHints | None) -> Path | None:
    if hints and hints.dockerfile:
        p = repo / hints.dockerfile
        return p if p.is_file() else None
    dockerfiles = profile.get("dockerfiles") or []
    if dockerfiles:
        p = repo / dockerfiles[0]
        return p if p.is_file() else None
    return None


def _dockerfile_launch_plan(image: str, run_network: str, service: str) -> dict[str, Any]:
    return export_launch_plan(
        {
            "x_loadline_app": service,
            "services": {
                service: {
                    "image": image,
                    "networks": [run_network],
                }
            },
        },
        run_network=run_network,
        diffs=[],
        build_egress="unrestricted",
    )


def _teardown_container(container: str, image: str, run_id: str, run_network: str) -> None:
    docker_cmd(["rm", "-f", container], timeout=120)
    docker_cmd(["rmi", "-f", image], timeout=120)
    remove_labeled(run_id)
    docker_cmd(["network", "rm", run_network], timeout=60)


def _dockerfile_evidence(
    container: str,
    health_url: str,
    budget_s: float,
    elapsed_s: float,
    last_probe: Any,
) -> BootEvidence:
    ps = docker_cmd(["ps", "-a", "--filter", f"name={container}"], timeout=60)
    logs = docker_cmd(["logs", "--tail", "40", container], timeout=120)
    return BootEvidence(
        health_url=health_url,
        budget_s=budget_s,
        elapsed_s=elapsed_s,
        ps_text=(ps.stdout or ps.stderr or "").strip(),
        ps_heading="docker ps",
        logs={container: (logs.stdout or logs.stderr or "").strip()},
        last_probe=last_probe,
    )


def _blocked(run_dir: Path | None, outcome: BootOutcome) -> BootOutcome:
    if run_dir is not None and outcome.run_id and outcome.status != "booted":
        persist_blocked_attempts(run_dir, outcome.attempts, outcome.blocker)
    return outcome


def boot_dockerfile_repository(
    repo: Path,
    *,
    profile: dict[str, Any],
    capabilities: dict[str, Any],
    hints: LoadlineHints | None = None,
    teardown: bool = True,
) -> BootOutcome:
    dockerfile = _resolve_dockerfile(repo, profile, hints)
    if dockerfile is None:
        return BootOutcome(
            status="blocked",
            exit_code=10,
            blocker={
                "code": "no_entrypoint",
                "summary": "No compose file or Dockerfile was found.",
                "retryable": True,
                "security": False,
                "user_can_provide": ["compose_file", "dockerfile"],
                "remediation": [],
            },
            capabilities=capabilities,
        )

    run_id, run_dir = allocate_run_dir(repo)
    run_network = f"loadline_net_{run_id}"
    service = hints.app_service if hints and hints.app_service else APP_NAME
    image = f"loadline_{run_id}_app:latest"
    container = f"loadline_{run_id}_{service}"
    port, health_path = _health_url(service, hints)
    health_url = f"http://{service}:{port}{health_path}"
    launch_plan = _dockerfile_launch_plan(image, run_network, service)
    (run_dir / "launch_plan.json").write_text(json.dumps(launch_plan, indent=2))

    net_err = create_internal_network(run_network, run_id=run_id)
    if net_err:
        return _blocked(
            run_dir,
            BootOutcome(
                status="blocked",
                exit_code=7,
                blocker={"code": "boot_failed", "summary": net_err.message, "retryable": True, "security": False, "user_can_provide": [], "remediation": []},
                capabilities=capabilities,
                launch_plan=launch_plan,
                run_id=run_id,
            ),
        )

    def _extra_teardown() -> None:
        _teardown_container(container, image, run_id, run_network)

    register_run_cleanup(RunCleanupState(run_id=run_id, extra=_extra_teardown))
    attempts: list[BootAttempt] = []
    try:
        build = docker_cmd(
            [
                "build",
                "-t",
                image,
                "-f",
                str(dockerfile.resolve()),
                "--label",
                f"loadline.run={run_id}",
                str(repo.resolve()),
            ],
            timeout=900,
        )
        if build.returncode != 0:
            detail = (build.stderr or build.stdout or "image build failed")[:2000]
            attempts.append(BootAttempt(1, "docker_build", "boot_failed", detail=detail[:500]))
            return _blocked(
                run_dir,
                BootOutcome(
                    status="blocked",
                    exit_code=7,
                    blocker={
                        "code": "build_failed",
                        "summary": detail,
                        "retryable": False,
                        "security": False,
                        "user_can_provide": [],
                        "remediation": [],
                    },
                    attempts=attempts,
                    capabilities=capabilities,
                    launch_plan=launch_plan,
                    run_id=run_id,
                ),
            )

        run = docker_cmd(
            [
                "run",
                "-d",
                "--name",
                container,
                "--hostname",
                service,
                "--network",
                run_network,
                "--label",
                f"loadline.run={run_id}",
                "--cpus",
                str(DEFAULT_APP_CPUS),
                "--memory",
                DEFAULT_APP_MEM,
                "--pids-limit",
                str(DEFAULT_PIDS),
                image,
            ],
            timeout=120,
        )
        if run.returncode != 0:
            attempts.append(BootAttempt(1, "docker_run", "boot_failed", detail=(run.stderr or "")[:500]))
            return _blocked(
                run_dir,
                BootOutcome(
                    status="blocked",
                    exit_code=7,
                    blocker={"code": "boot_failed", "summary": "container start failed", "retryable": True, "security": False, "user_can_provide": [], "remediation": []},
                    attempts=attempts,
                    capabilities=capabilities,
                    launch_plan=launch_plan,
                    run_id=run_id,
                ),
            )

        cid = (docker_cmd(["ps", "-q", "-f", f"name={container}"]).stdout or "").strip()
        if not egress_check(probe_image(), run_network) or not cid or not _egress_from_container(cid):
            attempts.append(BootAttempt(1, "docker_run", "egress_not_enforced", detail="egress"))
            return _blocked(
                run_dir,
                BootOutcome(
                    status="blocked",
                    exit_code=4,
                    blocker={"code": "egress_not_enforced", "summary": "egress check failed", "retryable": False, "security": False, "user_can_provide": [], "remediation": []},
                    attempts=attempts,
                    capabilities=capabilities,
                    launch_plan=launch_plan,
                    run_id=run_id,
                ),
            )

        budget_s = dockerfile_readiness_budget_s()
        waited = wait_until_http_ready(lambda: _probe_http_result(run_network, health_url), budget_s)
        if not waited.ready:
            evidence = _dockerfile_evidence(
                container, health_url, budget_s, waited.elapsed_s, waited.last_probe
            )
            attempts.append(BootAttempt(1, "health", "boot_failed", detail=evidence.summary_text()))
            return _blocked(
                run_dir,
                BootOutcome(
                    status="blocked",
                    exit_code=7,
                    blocker=health_timeout_blocker(evidence),
                    attempts=attempts,
                    capabilities=capabilities,
                    launch_plan=launch_plan,
                    run_id=run_id,
                ),
            )

        readiness = evaluate_data_readiness(
            [ReadOperation(id="health", needs_harvested_ids=False)],
            DatasetMeasurement(size=None, source="not_measured"),
        )
        if readiness.blocker_code == "data_missing":
            return _blocked(
                run_dir,
                BootOutcome(
                    status="blocked",
                    exit_code=10,
                    blocker={"code": "data_missing", "summary": readiness.blocker_summary or "data_missing", "retryable": False, "security": False, "user_can_provide": [], "remediation": []},
                    attempts=attempts,
                    capabilities=capabilities,
                    launch_plan=launch_plan,
                    run_id=run_id,
                ),
            )

        attempts.append(BootAttempt(1, "docker_run", "success"))
        outcome = BootOutcome(
            status="booted",
            exit_code=0,
            attempts=attempts,
            capabilities=capabilities,
            launch_plan=launch_plan,
            boot={
                "health": {"status": "ok", "url": health_url, "path": health_path},
                "services": [{"name": service, "role": "app"}],
                "run_id": run_id,
                "run_dir": str(run_dir),
                "network": run_network,
            },
            run_id=run_id,
        )
        return outcome
    finally:
        unregister_run_cleanup()
        if teardown:
            _extra_teardown()


# Re-export for tests
__all__ = ["boot_dockerfile_repository", "labeled_objects_remaining", "attempts_to_json"]
