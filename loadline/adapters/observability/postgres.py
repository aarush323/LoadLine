"""Postgres dependency telemetry (tech_doc.md §10.3)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from loadline.adapters.runtime.docker_runner import docker_cmd
from loadline.core.metrics import MetricSeries, MetricPoint


@dataclass(frozen=True)
class PostgresTarget:
    service: str
    user: str
    database: str


def _env_dict(spec: dict[str, Any]) -> dict[str, str]:
    env = spec.get("environment") or {}
    if isinstance(env, dict):
        return {str(k): str(v) for k, v in env.items()}
    out: dict[str, str] = {}
    if isinstance(env, list):
        for item in env:
            if isinstance(item, str) and "=" in item:
                k, v = item.split("=", 1)
                out[k] = v
    return out


def postgres_target_from_spec(name: str, spec: dict[str, Any]) -> PostgresTarget | None:
    image = str(spec.get("image") or "")
    if "postgres" not in image.lower():
        return None
    env = _env_dict(spec)
    user = env.get("POSTGRES_USER") or env.get("PGUSER")
    database = env.get("POSTGRES_DB") or env.get("PGDATABASE")
    if not user or not database:
        return None
    return PostgresTarget(service=name, user=user, database=database)


def discover_postgres_targets(run_dir: Path) -> list[PostgresTarget]:
    runtime = run_dir / "compose.runtime.yaml"
    plan_path = run_dir / "launch_plan.json"
    services: list[tuple[str, dict[str, Any]]] = []
    if runtime.is_file():
        data = yaml.safe_load(runtime.read_text()) or {}
        for name, spec in (data.get("services") or {}).items():
            if isinstance(spec, dict):
                services.append((name, spec))
    elif plan_path.is_file():
        plan = json.loads(plan_path.read_text())
        for entry in plan.get("services") or []:
            if isinstance(entry, dict) and entry.get("name") and entry.get("spec"):
                services.append((entry["name"], entry["spec"]))
    targets: list[PostgresTarget] = []
    for name, spec in services:
        target = postgres_target_from_spec(name, spec)
        if target:
            targets.append(target)
    return targets


def snapshot_postgres(
    *,
    project: str,
    compose_file: Path,
    repo: Path,
    target: PostgresTarget,
) -> tuple[MetricSeries | None, str]:
    """Return (series, status) where status is ready or degraded."""
    sql = "SELECT COALESCE(SUM(numbackends),0) FROM pg_stat_database;"
    proc = _compose_exec(project, compose_file, repo, target.service, target.user, target.database, sql)
    if proc.returncode != 0:
        return None, "degraded"
    try:
        connections = int((proc.stdout or "0").strip() or "0")
    except ValueError:
        return None, "degraded"
    series = MetricSeries(
        name="pg_numbackends",
        unit="connections",
        entity=f"dependency:{target.service}",
        kind="gauge",
        points=[MetricPoint(t=0.0, value=float(connections))],
        coverage=1.0,
        evidence_id=f"ev-pg-{target.service}-backends",
    )
    return series, "ready"


def _compose_exec(
    project: str,
    compose_file: Path,
    repo: Path,
    service: str,
    user: str,
    database: str,
    sql: str,
) -> Any:
    import subprocess

    return subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            project,
            "--project-directory",
            str(repo),
            "-f",
            str(compose_file),
            "exec",
            "-T",
            service,
            "psql",
            "-U",
            user,
            "-d",
            database,
            "-tAc",
            sql,
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
