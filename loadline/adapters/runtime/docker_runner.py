"""Docker engine helpers for sandbox runs."""

from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loadline.constants import PROBE_IMAGE_DIGEST


@dataclass
class DockerError:
    message: str


def run_id() -> str:
    return uuid.uuid4().hex[:12]


def docker_cmd(args: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def create_internal_network(name: str, *, run_id: str | None = None) -> DockerError | None:
    args = ["network", "create", "--internal"]
    if run_id:
        args.extend(["--label", f"loadline.run={run_id}"])
    args.append(name)
    proc = docker_cmd(args)
    if proc.returncode != 0 and "already exists" not in (proc.stderr or ""):
        return DockerError(proc.stderr or proc.stdout or "network create failed")
    return None


def remove_labeled(run_id: str) -> None:
    label_filter = f"loadline.run={run_id}"
    for kind in ("container", "network", "volume"):
        subcmd = "ps" if kind == "container" else kind
        proc = docker_cmd([subcmd, "-aq", "--filter", f"label={label_filter}"])
        ids = [x for x in (proc.stdout or "").split() if x]
        if not ids:
            continue
        docker_cmd(["rm", "-f", *ids] if kind == "container" else ["rm", *ids])


def egress_check(container_image: str, network: str) -> bool:
    """Return True if outbound connect fails (egress denied)."""
    proc = docker_cmd(
        [
            "run",
            "--rm",
            "--network",
            network,
            container_image,
            "wget",
            "-q",
            "-T",
            "2",
            "http://1.1.1.1",
        ],
        timeout=30,
    )
    return proc.returncode != 0


def engine_info() -> dict[str, Any]:
    proc = docker_cmd(["info", "--format", "{{json .}}"], timeout=30)
    if proc.returncode != 0:
        return {}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


_RUN_LABEL = "loadline.run"


def _apply_run_label(labels: Any, run_id: str) -> Any:
    """Compose labels may be a map or a list of key=value strings."""
    if isinstance(labels, list):
        kept = [
            item
            for item in labels
            if not (isinstance(item, str) and item.split("=", 1)[0].strip() == _RUN_LABEL)
        ]
        kept.append(f"{_RUN_LABEL}={run_id}")
        return kept
    if isinstance(labels, dict):
        updated = dict(labels)
        updated[_RUN_LABEL] = run_id
        return updated
    return {_RUN_LABEL: run_id}


def tag_compose_labels(plan: dict[str, Any], run_id: str) -> dict[str, Any]:
    for svc in (plan.get("services") or {}).values():
        if isinstance(svc, dict):
            svc["labels"] = _apply_run_label(svc.get("labels"), run_id)
    return plan


def probe_image() -> str:
    if not PROBE_IMAGE_DIGEST:
        raise RuntimeError("PROBE_IMAGE_DIGEST is not set (S-DOCKER spike)")
    return PROBE_IMAGE_DIGEST
