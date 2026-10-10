"""Boot analysis JSON (tech_doc.md §16.1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loadline.adapters.runtime.compose_boot import attempts_to_json, boot_repository, persist_blocked_attempts
from loadline.core.auth import require_model_auth
from loadline.core.hints import load_hints
from loadline.discovery.intake import discover_capabilities, discover_profile
from loadline.paths import loadline_home
from loadline.ui.phases import Phase
from loadline.ui.run_console import RunConsole

CONFIG_SCHEMA = "loadline-hints/1"


def _auth_blocker_doc() -> tuple[dict[str, Any], int]:
    auth_err = require_model_auth()
    if not auth_err:
        return {}, 0
    return (
        {
            "status": "needs_input",
            "blocker": {
                "code": "needs_input",
                "summary": auth_err.message,
                "retryable": False,
                "security": False,
                "user_can_provide": [],
                "remediation": [],
            },
            "attempts": [],
            "config_schema": CONFIG_SCHEMA,
            "capabilities": None,
            "launch_plan": None,
            "boot": None,
        },
        2,
    )


def analyze_boot_json(
    repo: Path,
    *,
    require_auth: bool = True,
    teardown: bool = True,
    console: RunConsole | None = None,
) -> tuple[dict[str, Any], int]:
    if require_auth:
        doc, code = _auth_blocker_doc()
        if code:
            return doc, code

    hints_path = repo / ".loadline.yaml"
    hints, err = load_hints(hints_path)
    if err:
        profile = discover_profile(repo)
        capabilities = discover_capabilities(profile)
        return (
            {
                "status": "blocked",
                "blocker": {
                    "code": "policy_refused",
                    "summary": err,
                    "retryable": True,
                    "security": False,
                    "user_can_provide": [],
                    "remediation": [],
                },
                "attempts": [],
                "config_schema": CONFIG_SCHEMA,
                "capabilities": capabilities,
                "launch_plan": None,
                "boot": None,
            },
            10,
        )

    ui = console if console is not None else RunConsole.disabled()
    boot_progress = ui.boot_progress() if ui.enabled() else None
    if ui.enabled():
        ui.phase_start(Phase.BOOT)
    outcome = boot_repository(
        repo, hints=hints, teardown=teardown, require_auth=False, progress=boot_progress
    )
    if outcome.status != "booted" and outcome.run_id:
        run_dir = loadline_home() / "runs" / outcome.run_id
        if run_dir.is_dir():
            persist_blocked_attempts(run_dir, outcome.attempts, outcome.blocker)
    if ui.enabled():
        if outcome.status == "booted":
            ui.phase_done(Phase.BOOT, "healthy")
        else:
            detail = ""
            if outcome.attempts:
                detail = outcome.attempts[-1].detail or ""
            ui.print_blocker(outcome.blocker, None)
            ui.phase_fail(
                Phase.BOOT,
                detail or (outcome.blocker or {}).get("summary", "boot failed"),
            )
    doc: dict[str, Any] = {
        "status": outcome.status,
        "blocker": outcome.blocker,
        "attempts": attempts_to_json(outcome.attempts),
        "config_schema": CONFIG_SCHEMA,
        "capabilities": outcome.capabilities,
        "launch_plan": outcome.launch_plan,
        "boot": outcome.boot,
    }
    return doc, outcome.exit_code
