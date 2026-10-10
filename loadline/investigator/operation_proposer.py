"""LLM operation proposals when discovery found none (S7). Skipped in unit tests."""

from __future__ import annotations

import os
from pathlib import Path


def proposer_enabled() -> bool:
    return os.environ.get("LOADLINE_SKIP_OPERATION_PROPOSER", "").lower() not in ("1", "true", "yes")


async def propose_operations_if_needed(operations: list, repo_root: Path) -> list:
    if operations or not proposer_enabled():
        return operations
    # Live proposer is only invoked from the investigator run path with a real model.
    return operations
