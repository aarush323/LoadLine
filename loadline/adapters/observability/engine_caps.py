"""Docker engine capability detection (S-CGROUP / tech_doc.md §10.2)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from loadline.adapters.runtime.docker_runner import docker_cmd, engine_info


@dataclass(frozen=True)
class EnginePlacement:
    engine_ncpu: float | None
    host_logical_cores: int
    limiter: str
    measurement_ceiling_limited: bool


def host_logical_cores() -> int:
    return os.cpu_count() or 1


def detect_throttle_field(container_id: str) -> tuple[str | None, Any]:
    """Return (field_name, value) or (None, NOT_MEASURED) if absent."""
    proc = docker_cmd(["inspect", container_id, "--format", "{{json .}}"], timeout=30)
    if proc.returncode != 0:
        return None, None
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None, None
    state = data.get("State") or {}
    if state.get("OOMKilled") is not None:
        pass  # OOM is separate
    # Docker Desktop / Linux cgroup v2 paths vary; look for throttling_data shapes.
    for path in (
        ("HostStats", "cpu_stats", "throttling_data", "throttled_periods"),
        ("HostStats", "cpu_stats", "throttling_data", "throttled_time"),
    ):
        cur: Any = data
        for key in path:
            if not isinstance(cur, dict):
                cur = None
                break
            cur = cur.get(key)
        if cur is not None:
            return ".".join(path), cur
    # stats snapshot via one-shot docker stats (engine-specific keys)
    stats = docker_cmd(
        ["stats", "--no-stream", "--format", "{{json .}}", container_id],
        timeout=30,
    )
    if stats.returncode == 0 and stats.stdout:
        try:
            row = json.loads(stats.stdout.strip().splitlines()[0])
            if "ThrottlingData" in row:
                return "ThrottlingData", row["ThrottlingData"]
        except (json.JSONDecodeError, IndexError):
            pass
    return None, None


def engine_placement() -> EnginePlacement:
    info = engine_info()
    ncpu = info.get("NCPU")
    engine_ncpu = float(ncpu) if ncpu is not None else None
    host_cores = host_logical_cores()
    limited = engine_ncpu is not None and engine_ncpu < host_cores
    return EnginePlacement(
        engine_ncpu=engine_ncpu,
        host_logical_cores=host_cores,
        limiter="docker_engine" if limited else "host",
        measurement_ceiling_limited=limited,
    )
