"""Docker stats sampling for app and generator containers."""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from loadline.adapters.observability.engine_caps import detect_throttle_field
from loadline.adapters.runtime.docker_runner import docker_cmd
from loadline.core.metrics import NOT_MEASURED, MetricPoint, MetricSeries


@dataclass
class ContainerSample:
    container_id: str
    name: str
    cpu_percent: float | None
    memory_bytes: int | None
    pids: int | None
    oom_killed: bool | None
    throttle_field: str | None = None
    throttle_value: Any = None
    role: str = "unknown"


def _service_roles_from_launch_plan(launch_plan: dict[str, Any] | None) -> dict[str, str]:
    if not launch_plan:
        return {}
    roles: dict[str, str] = {}
    for entry in launch_plan.get("services") or []:
        if isinstance(entry, dict) and entry.get("name") and entry.get("role"):
            roles[str(entry["name"])] = str(entry["role"])
    return roles


@dataclass
class StatsCollector:
    run_id: str
    service_roles: dict[str, str] = field(default_factory=dict)
    samples: list[ContainerSample] = field(default_factory=list)
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None
    fields_seen: set[str] = field(default_factory=set)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._poll()
            time.sleep(0.5)

    def _poll(self) -> None:
        proc = docker_cmd(["ps", "-q", "--filter", f"label=loadline.run={self.run_id}"])
        ids = [x for x in (proc.stdout or "").split() if x]
        if not ids:
            return
        stats = docker_cmd(
            ["stats", "--no-stream", "--format", "{{json .}}", *ids],
            timeout=30,
        )
        if stats.returncode != 0:
            return
        for line in (stats.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            cid = row.get("ID") or row.get("Container") or ""
            name = row.get("Name") or ""
            cpu = _parse_cpu_percent(row.get("CPUPerc"))
            mem = _parse_mem_usage(row.get("MemUsage"))
            pids = _parse_int(row.get("PIDs"))
            if "CPUPerc" in row:
                self.fields_seen.add("CPUPerc")
            if "MemUsage" in row:
                self.fields_seen.add("MemUsage")
            if "PIDs" in row:
                self.fields_seen.add("PIDs")
            if "ThrottlingData" in row:
                self.fields_seen.add("ThrottlingData")
            throttle_field, throttle_value = detect_throttle_field(cid) if cid else (None, None)
            oom = _inspect_oom(cid) if cid else None
            role = _role_for_container(name, self.service_roles)
            self.samples.append(
                ContainerSample(
                    container_id=cid,
                    name=name,
                    cpu_percent=cpu,
                    memory_bytes=mem,
                    pids=pids,
                    oom_killed=oom,
                    throttle_field=throttle_field,
                    throttle_value=throttle_value,
                    role=role,
                )
            )


def _role_for_container(name: str, service_roles: dict[str, str]) -> str:
    lower = name.lower()
    if "k6" in lower or "grafana" in lower:
        return "generator"
    for svc_name, role in service_roles.items():
        if svc_name in lower or f"-{svc_name}-" in lower or lower.endswith(f"_{svc_name}_1"):
            return role
    return "unknown"


def _guess_role(name: str) -> str:
    """Legacy name-based guess when launch plan roles are unavailable."""
    lower = name.lower()
    if "k6" in lower or "grafana" in lower:
        return "generator"
    if "db" in lower or "postgres" in lower:
        return "dependency"
    return "app"


def _parse_cpu_percent(raw: Any) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().rstrip("%")
    try:
        return float(text)
    except ValueError:
        return None


def _parse_mem_usage(raw: Any) -> int | None:
    if not raw:
        return None
    part = str(raw).split("/")[0].strip()
    match = re.match(r"([\d.]+)\s*([KMG]i?B)", part, re.I)
    if not match:
        return None
    val = float(match.group(1))
    unit = match.group(2).upper()
    mult = {"B": 1, "KIB": 1024, "KB": 1000, "MIB": 1024**2, "MB": 1000**2, "GIB": 1024**3, "GB": 1000**3}
    for key, m in mult.items():
        if unit.startswith(key[:2]):
            return int(val * m)
    return int(val)


def _parse_int(raw: Any) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _inspect_oom(container_id: str) -> bool | None:
    proc = docker_cmd(["inspect", container_id, "--format", "{{.State.OOMKilled}}"], timeout=20)
    if proc.returncode != 0:
        return None
    text = (proc.stdout or "").strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    return None


def aggregate_role(samples: list[ContainerSample], role: str) -> dict[str, Any]:
    role_samples = [s for s in samples if s.role == role]
    if not role_samples:
        return {}
    cpus = [s.cpu_percent for s in role_samples if s.cpu_percent is not None]
    mems = [s.memory_bytes for s in role_samples if s.memory_bytes is not None]
    throttle_fields = [s.throttle_field for s in role_samples if s.throttle_field]
    throttle_vals = [s.throttle_value for s in role_samples if s.throttle_value is not None]
    ooms = [s.oom_killed for s in role_samples if s.oom_killed is not None]
    return {
        "cpu_percent_max": max(cpus) if cpus else None,
        "memory_bytes_max": max(mems) if mems else None,
        "throttle_field": throttle_fields[-1] if throttle_fields else None,
        "throttle_value": throttle_vals[-1] if throttle_vals else NOT_MEASURED,
        "oom_killed": any(ooms) if ooms else None,
        "sample_count": len(role_samples),
    }


def container_stats_series(
    samples: list[ContainerSample],
    *,
    window_s: float,
    evidence_prefix: str,
) -> list[MetricSeries]:
    series: list[MetricSeries] = []
    for role in ("app", "generator", "dependency"):
        role_samples = [s for s in samples if s.role == role]
        if not role_samples:
            continue
        coverage = min(1.0, len(role_samples) * 0.5 / max(window_s, 1.0))
        cpus = [s.cpu_percent for s in role_samples if s.cpu_percent is not None]
        if cpus:
            series.append(
                MetricSeries(
                    name="cpu_percent",
                    unit="percent",
                    entity=role,
                    kind="gauge",
                    points=[MetricPoint(t=i * 0.5, value=v) for i, v in enumerate(cpus)],
                    coverage=coverage,
                    evidence_id=f"{evidence_prefix}-{role}-cpu",
                )
            )
        throttle = role_samples[-1].throttle_value if role_samples else None
        throttle_field = role_samples[-1].throttle_field if role_samples else None
        throttle_point = throttle if throttle_field else NOT_MEASURED
        series.append(
            MetricSeries(
                name="throttle",
                unit="engine",
                entity=role,
                kind="gauge",
                points=[MetricPoint(t=window_s, value=throttle_point)],
                coverage=1.0 if throttle_field else 0.0,
                evidence_id=f"{evidence_prefix}-{role}-throttle",
            )
        )
    return series
