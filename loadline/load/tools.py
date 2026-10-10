"""Load tools, no shell (Phase 8)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import difflib

import yaml


class LoadToolError(Exception):
    pass


def check_config(data: dict[str, Any]) -> dict[str, Any]:
    """Schema only, no boot, no shell."""
    from loadline.config.schema import LoadlineHints

    try:
        LoadlineHints.model_validate(data)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


class TryBootCap:
    def __init__(self, limit: int = 5):
        self.limit = limit
        self.calls = 0

    def try_boot(
        self,
        repo: Path,
        hints: Any | None,
        *,
        progress: Any | None = None,
        config: Any | None = None,
    ) -> dict[str, Any]:
        from loadline.adapters.runtime.boot_and_prepare import boot_and_prepare

        if self.calls >= self.limit:
            return {"capped": True, "limitations": [f"try_boot capped at {self.limit}"]}
        self.calls += 1
        outcome = boot_and_prepare(
            repo,
            hints=hints,
            teardown=True,
            require_auth=False,
            progress=progress,
            config=config,
        )
        return {"status": outcome.status, "blocker": outcome.blocker, "run_id": outcome.run_id}


def write_config(
    data: dict[str, Any],
    repo: Path,
    *,
    refresh: bool = False,
) -> dict[str, Any]:
    """Write home config, or proposed on --refresh (with diff, no overwrite)."""
    from loadline.config.fingerprint import config_dir_for_repo

    repo = repo.resolve()
    if not refresh:
        out_dir = config_dir_for_repo(repo)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "loadline.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
        return {"path": str(out_dir / "loadline.yaml")}
    # --refresh: write proposed, print diff, do not overwrite user-edited yaml.
    home_path = config_dir_for_repo(repo) / "loadline.yaml"
    proposed = repo / "loadline.proposed.yaml"
    new_text = yaml.safe_dump(data, sort_keys=False)
    old_text = home_path.read_text() if home_path.is_file() else ""
    # Do not overwrite home when user edited (exists and differs and refresh requested).
    proposed.write_text(new_text)
    diff = "\n".join(difflib.unified_diff(old_text.splitlines(), new_text.splitlines(), lineterm=""))
    print(diff if diff else "(no diff)")
    return {"path": str(proposed), "diff": diff}
