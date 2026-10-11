"""loadline load: trial-boot a repository and save the hints that worked."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

from loadline.adapters.runtime.compose_boot import BootOutcome, boot_repository
from loadline.core.auth import require_model_auth
from loadline.core.hints import load_hints
from loadline.setup_agent import hints_from_boot, run_setup_agent
from loadline.ui.run_console import RunConsole


def _security_stop(outcome: BootOutcome) -> bool:
    blocker = outcome.blocker or {}
    if blocker.get("security"):
        return True
    return blocker.get("code") == "policy_refused"


def _maybe_write_hints(repo: Path, outcome: BootOutcome) -> Path | None:
    hint_path = repo / ".loadline.yaml"
    if hint_path.is_file() or not outcome.boot:
        return hint_path if hint_path.is_file() else None
    doc = hints_from_boot(outcome.boot)
    if "env" in doc:
        del doc["env"]
    text = yaml.safe_dump(doc, sort_keys=False)
    hint_path.write_text(text, encoding="utf-8")
    parsed, err = load_hints(hint_path)
    if err or parsed is None:
        hint_path.unlink(missing_ok=True)
        print(f"error: refused to write hints ({err})", file=sys.stderr)
        return None
    return hint_path


def _print_blocker(outcome: BootOutcome) -> None:
    print(json.dumps({"status": outcome.status, "blocker": outcome.blocker}, indent=2), file=sys.stderr)


def load_repository(
    repo: Path,
    *,
    require_auth: bool = True,
    setup_runner: Any | None = None,
) -> int:
    repo = repo.resolve()
    if require_auth:
        auth_err = require_model_auth()
        if auth_err:
            print(f"error: {auth_err.message}", file=sys.stderr)
            print(f"Set {auth_err.env_var}.", file=sys.stderr)
            return 2

    _hints, hint_err = load_hints(repo / ".loadline.yaml")
    if hint_err:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "blocker": {
                        "code": "boot_failed",
                        "summary": hint_err,
                        "retryable": True,
                        "security": False,
                    },
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 10

    console = RunConsole(json_mode=False, quiet=False, verbose=True, no_color=False)
    progress = console.boot_progress() if console.enabled() else None
    outcome = boot_repository(repo, teardown=True, require_auth=False, progress=progress)
    if outcome.status != "booted" and _security_stop(outcome):
        _print_blocker(outcome)
        return outcome.exit_code or 10

    blocker = outcome.blocker or {}
    if outcome.status != "booted" and blocker.get("retryable") and not blocker.get("security"):
        runner = setup_runner if setup_runner is not None else run_setup_agent
        outcome = runner(repo, outcome)

    if outcome.status == "booted":
        hint_path = _maybe_write_hints(repo, outcome)
        boot = outcome.boot or {}
        health = boot.get("health") if isinstance(boot.get("health"), dict) else {}
        print("status: booted")
        if hint_path:
            print(f"hints: {hint_path}")
        if boot.get("app_service"):
            print(f"app_service: {boot['app_service']}")
        if isinstance(health, dict) and health.get("path"):
            print(f"health_path: {health['path']}")
        return 0

    _print_blocker(outcome)
    return outcome.exit_code or 10
