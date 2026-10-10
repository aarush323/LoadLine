"""End-to-end `loadline run` lifecycle (boot → investigator → teardown)."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loadline.adapters.runtime.boot_teardown import teardown_boot_outcome
from loadline.adapters.runtime.compose_boot import boot_repository, persist_blocked_attempts
from loadline.adapters.runtime.run_cleanup import RunCleanupState, register_run_cleanup, unregister_run_cleanup
from loadline.core.ledger import Ledger
from loadline.discovery.intake import discover_capabilities, discover_profile
from loadline.investigator.agent_factory import default_usage_limits
from loadline.investigator.run import run_investigation_sync, write_agent_report
from loadline.neatlogs_setup import shutdown_neatlogs
from loadline.paths import loadline_home
from loadline.ui.phases import Phase
from loadline.ui.run_console import RunConsole

logger = logging.getLogger(__name__)


@dataclass
class RunPipelineResult:
    exit_code: int
    run_id: str | None = None
    run_dir: Path | None = None
    report_md: Path | None = None
    status: str = ""
    blocker: dict[str, Any] | None = None
    phases: list[dict[str, str]] = field(default_factory=list)


def _init_neatlogs_if_configured(
    run_id: str | None, fast_baseline: bool, console: RunConsole
) -> None:
    from loadline.settings import get_settings

    if not (get_settings().neatlogs_api_key or "").strip():
        return
    try:
        from loadline.neatlogs_setup import LOADLINE_WORKFLOW, init_neatlogs, neatlogs_initialized

        init_neatlogs(
            workflow_name=LOADLINE_WORKFLOW,
            run_id=run_id,
            fast=fast_baseline,
            require_api_key=True,
        )
        if neatlogs_initialized() and run_id:
            console.trace(f"neatlogs workflow {LOADLINE_WORKFLOW} tag run_id:{run_id}")
    except Exception as exc:
        console.warn(f"neatlogs not exporting ({type(exc).__name__})")
        logger.warning("neatlogs initialization failed (%s)", type(exc).__name__)


def _run_dir_for_boot(boot: Any) -> Path | None:
    if boot.boot and boot.boot.get("run_dir"):
        return Path(boot.boot["run_dir"])
    if boot.run_id:
        return loadline_home() / "runs" / boot.run_id
    return None


def _ensure_blocked_artifacts(repo: Path, boot: Any) -> Path | None:
    run_dir = _run_dir_for_boot(boot)
    if run_dir is None:
        return None
    if (run_dir / "profile.json").is_file() and (run_dir / "capabilities.json").is_file():
        return run_dir
    profile = discover_profile(repo)
    capabilities = boot.capabilities or discover_capabilities(profile)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "profile.json").write_text(json.dumps(profile, indent=2))
    (run_dir / "capabilities.json").write_text(json.dumps(capabilities, indent=2))
    return run_dir


def _result_payload(result: RunPipelineResult) -> dict[str, Any]:
    return {
        "exit_code": result.exit_code,
        "status": result.status,
        "run_id": result.run_id,
        "run_dir": str(result.run_dir) if result.run_dir else None,
        "report_md": str(result.report_md) if result.report_md else None,
        "blocker": result.blocker,
        "phases": result.phases,
    }


def run_loadline(
    repo: Path,
    *,
    skip_investigator: bool | None = None,
    fast_baseline: bool = False,
    require_auth: bool = True,
    console: RunConsole | None = None,
) -> RunPipelineResult:
    repo = repo.resolve()
    ui = console if console is not None else RunConsole.disabled()
    ui.run_header(run_id=None, repo=repo)

    if skip_investigator is None:
        skip_investigator = os.environ.get("LOADLINE_SKIP_INVESTIGATOR", "").lower() in ("1", "true", "yes")

    ui.phase_start(Phase.PREFLIGHT)
    if require_auth:
        from loadline.core.auth import require_model_auth

        auth_err = require_model_auth()
        if auth_err:
            if not ui.json_mode:
                print(f"error: {auth_err.message}", file=sys.stderr)
                print(f"Set {auth_err.env_var}.", file=sys.stderr)
            ui.phase_fail(Phase.PREFLIGHT, auth_err.message)
            return RunPipelineResult(exit_code=2, status="auth_missing", phases=ui.timeline())
    ui.phase_done(Phase.PREFLIGHT)

    ui.phase_start(Phase.BOOT)
    boot_progress = ui.boot_progress() if ui.enabled() else None
    boot = boot_repository(repo, teardown=False, require_auth=False, progress=boot_progress)
    run_dir_early = _ensure_blocked_artifacts(repo, boot)
    if run_dir_early:
        ui.set_run_dir(run_dir_early)
        ui.run_header(run_id=boot.run_id, repo=repo)
    _init_neatlogs_if_configured(boot.run_id, fast_baseline, ui)

    if boot.status != "booted" or not boot.boot or not boot.run_id:
        code = boot.exit_code if boot.exit_code else 10
        run_dir = run_dir_early
        if run_dir is not None:
            persist_blocked_attempts(run_dir, boot.attempts, boot.blocker)
        if ui.json_mode and boot.blocker:
            print(json.dumps({"status": boot.status, "blocker": boot.blocker}, indent=2), file=sys.stderr)
        else:
            ui.print_blocker(boot.blocker, run_dir)
        return RunPipelineResult(
            exit_code=code,
            status=boot.status,
            blocker=boot.blocker,
            run_id=boot.run_id,
            run_dir=run_dir,
            phases=ui.timeline(),
        )

    ui.phase_done(Phase.BOOT, "healthy")
    run_id = boot.run_id
    run_dir = Path(boot.boot["run_dir"])
    ui.set_run_dir(run_dir)
    network = boot.boot["network"]
    hosts = frozenset(s["name"] for s in boot.boot["services"])

    def _teardown() -> None:
        teardown_boot_outcome(boot, repo)

    register_run_cleanup(RunCleanupState(run_id=run_id, extra=_teardown))
    try:
        if skip_investigator:
            ledger = Ledger.open(run_dir, run_id)
            ledger.append(
                "investigation_incomplete",
                evidence_ids=[],
                reason="investigator not run (skip flag)",
            )
            md_path = write_agent_report(
                run_dir,
                run_id,
                "# Loadline\n\nInvestigator skipped (`LOADLINE_SKIP_INVESTIGATOR`).\n",
                run_state="investigation_incomplete",
            )
            ui.phase_start(Phase.REPORT)
            ui.phase_done(Phase.REPORT, str(md_path.name))
            return RunPipelineResult(
                exit_code=0,
                run_id=run_id,
                run_dir=run_dir,
                report_md=md_path,
                status="investigation_skipped",
                phases=ui.timeline(),
            )

        ui.phase_start(Phase.INVESTIGATE)
        inv = run_investigation_sync(
            repo_root=repo,
            run_dir=run_dir,
            run_id=run_id,
            model=None,
            boot=boot.boot,
            fast=fast_baseline,
            usage_limits=default_usage_limits(),
            console=ui,
            allowed_hosts=hosts,
            network=network,
        )
        ui.phase_done(Phase.INVESTIGATE, inv.status)

        md_path = run_dir / "report.md"
        ui.phase_start(Phase.REPORT)
        ui.phase_done(Phase.REPORT, str(md_path.name) if md_path.is_file() else "missing")

        exit_code = 0 if inv.status in ("completed", "investigation_incomplete") else 3
        return RunPipelineResult(
            exit_code=exit_code,
            run_id=run_id,
            run_dir=run_dir,
            report_md=md_path if md_path.is_file() else None,
            status=inv.status,
            phases=ui.timeline(),
        )
    finally:
        if ui.verbose:
            ui.phase_start(Phase.TEARDOWN)
        try:
            shutdown_neatlogs()
        except Exception as exc:
            logger.warning("neatlogs shutdown failed (%s)", type(exc).__name__)
        unregister_run_cleanup()
        _teardown()
        if ui.verbose:
            ui.phase_done(Phase.TEARDOWN)


def emit_run_result(result: RunPipelineResult, console: RunConsole, *, print_report: bool = True) -> None:
    if console.json_mode:
        print(json.dumps(_result_payload(result), indent=2))
        return
    if result.blocker and not result.report_md and result.exit_code != 0:
        return
    if result.report_md and print_report and result.report_md.is_file():
        print("--- report ---")
        print(result.report_md.read_text())
    if result.run_dir:
        print(f"run_dir: {result.run_dir}", file=sys.stderr)
    if result.report_md:
        print(f"report: {result.report_md}", file=sys.stderr)
