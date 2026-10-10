"""One-time neatlogs initialization for Loadline (see tech_doc.md §14)."""

from __future__ import annotations

import subprocess
from typing import Any

import neatlogs

from loadline.neatlogs_workflows import CAPACITY_INVESTIGATION
from loadline.settings import LoadlineSettings, get_settings

LOADLINE_WORKFLOW = CAPACITY_INVESTIGATION

_INITIALIZED = False
_LAST_INIT_WORKFLOW: str | None = None


def git_short_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip() or "unknown"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def build_tags(
    *,
    run_id: str | None = None,
    fast: bool = False,
    extra: list[str] | None = None,
) -> list[str]:
    tags = ["neatHack", f"loadline_rev:{git_short_sha()}", f"fast:{fast}"]
    if run_id:
        tags.append(f"run_id:{run_id}")
    if extra:
        tags.extend(extra)
    return tags


def init_neatlogs(
    settings: LoadlineSettings | None = None,
    *,
    workflow_name: str | None = None,
    run_id: str | None = None,
    fast: bool = False,
    extra_tags: list[str] | None = None,
    require_api_key: bool = True,
) -> None:
    """Call once per process before wrapping agents or clients.

    API key: set ``NEATLOGS_API_KEY`` in the environment or ``.env`` (never commit).
    If unset and ``require_api_key`` is false, spans are captured locally but not exported.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return

    cfg = settings or get_settings()
    api_key = (cfg.neatlogs_api_key or "").strip()
    if require_api_key and not api_key:
        raise RuntimeError(
            "NEATLOGS_API_KEY is unset. This is not the hackathon placeholder "
            "<your-project-api-key>. Create a real ingest key in the browser: "
            "https://app.neatlogs.com → select project → Settings → API Keys. "
            "Then add NEATLOGS_API_KEY=... to .env (see docs/NEATLOGS-SETUP.md)."
        )

    kwargs: dict[str, Any] = {
        "workflow_name": workflow_name or cfg.neatlogs_workflow_name or CAPACITY_INVESTIGATION,
        "endpoint": cfg.neatlogs_endpoint,
        "tags": build_tags(run_id=run_id, fast=fast, extra=extra_tags),
    }
    if api_key:
        kwargs["api_key"] = api_key

    neatlogs.init(**kwargs)
    global _LAST_INIT_WORKFLOW
    _INITIALIZED = True
    _LAST_INIT_WORKFLOW = kwargs.get("workflow_name")


def neatlogs_initialized() -> bool:
    return _INITIALIZED


def neatlogs_workflow_name() -> str | None:
    return _LAST_INIT_WORKFLOW


def shutdown_neatlogs() -> None:
    global _INITIALIZED
    if not _INITIALIZED:
        return
    neatlogs.flush()
    neatlogs.shutdown()
    _INITIALIZED = False
