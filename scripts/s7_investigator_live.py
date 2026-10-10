#!/usr/bin/env python3
"""S7 gate: one live Investigator run on a fixture (paid OpenRouter call)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "fx-pyhttp-pg"


def main() -> int:
    load_dotenv(REPO_ROOT / ".env")
    os.environ.setdefault("LOADLINE_SKIP_OPERATION_PROPOSER", "1")
    os.environ.setdefault("LOADLINE_MODEL", "openrouter:deepseek/deepseek-v4.1-flash")

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY missing", file=sys.stderr)
        return 2

    from loadline.adapters.runtime.boot_teardown import teardown_boot_outcome
    from loadline.adapters.runtime.compose_boot import boot_repository
    from loadline.investigator.agent_factory import default_usage_limits
    from loadline.investigator.run import run_investigation_sync

    boot = boot_repository(FIXTURE, teardown=False, require_auth=False)
    if boot.status != "booted" or not boot.boot or not boot.run_id:
        print(f"boot failed: {boot.status}", file=sys.stderr)
        return 1

    run_dir = Path(boot.boot["run_dir"])
    run_id = boot.run_id
    network = boot.boot["network"]
    hosts = frozenset(s["name"] for s in boot.boot["services"])

    try:
        result = run_investigation_sync(
            repo_root=FIXTURE,
            run_dir=run_dir,
            run_id=run_id,
            model=None,
            boot=boot.boot,
            allowed_hosts=hosts,
            network=network,
            usage_limits=default_usage_limits(),
        )
        print("status:", result.status)
        if result.reason:
            print("reason:", result.reason)
        return 0 if result.status in ("completed", "investigation_incomplete") else 1
    finally:
        teardown_boot_outcome(boot, FIXTURE)


if __name__ == "__main__":
    raise SystemExit(main())
