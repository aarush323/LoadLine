"""Workload operation discovery (tech_doc.md §8.1)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from loadline.adapters.runtime.docker_runner import docker_cmd, probe_image
from loadline.core.hints import load_hints
from loadline.discovery.intake import _find_openapi


@dataclass(frozen=True)
class Operation:
    id: str
    service: str
    port: int
    method: str
    path: str
    provenance: str
    read_safe: bool = True


def _app_target(boot: dict[str, Any]) -> tuple[str, int]:
    health = boot.get("health") or {}
    url = health.get("url") or ""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or 8000
    return host, port


def _allowed_hosts(boot: dict[str, Any]) -> frozenset[str]:
    services = boot.get("services") or []
    return frozenset(str(s["name"]) for s in services if isinstance(s, dict) and s.get("name"))


def _live_openapi_paths(repo: Path) -> list[str]:
    catalog = [
        "/openapi.json",
        "/swagger.json",
        "/api/openapi.json",
        "/api/v1/openapi.json",
        "/v3/api-docs",
    ]
    seen = set(catalog)
    for rel in _find_openapi(repo):
        candidate = rel if rel.startswith("/") else f"/{rel.lstrip('/')}"
        if candidate not in seen and (
            candidate.endswith("openapi.json") or candidate.endswith("swagger.json")
        ):
            catalog.append(candidate)
            seen.add(candidate)
    return catalog


def _fetch_live_openapi(network: str, host: str, port: int, repo: Path) -> dict[str, Any] | None:
    for path in _live_openapi_paths(repo):
        url = f"http://{host}:{port}{path}"
        proc = docker_cmd(
            [
                "run",
                "--rm",
                "--network",
                network,
                probe_image(),
                "curl",
                "-sf",
                "--max-time",
                "5",
                url,
            ],
            timeout=60,
        )
        if proc.returncode != 0:
            continue
        try:
            data = json.loads(proc.stdout or "{}")
            if isinstance(data, dict) and data.get("paths"):
                return data
        except json.JSONDecodeError:
            continue
    return None


def _ops_from_openapi(spec: dict[str, Any], service: str, port: int, provenance: str) -> list[Operation]:
    paths = spec.get("paths") or {}
    ops: list[Operation] = []
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, _detail in methods.items():
            if method.upper() != "GET":
                continue
            op_id = re.sub(r"[^a-zA-Z0-9_]+", "_", path.strip("/") or "root")
            ops.append(
                Operation(
                    id=op_id,
                    service=service,
                    port=port,
                    method="GET",
                    path=path if path.startswith("/") else f"/{path}",
                    provenance=provenance,
                )
            )
    return ops


def _load_repo_openapi(repo: Path) -> dict[str, Any] | None:
    for rel in _find_openapi(repo):
        path = repo / rel
        try:
            if path.suffix == ".json":
                data = json.loads(path.read_text())
            else:
                data = yaml.safe_load(path.read_text())
            if isinstance(data, dict) and data.get("paths"):
                return data
        except (OSError, json.JSONDecodeError, yaml.YAMLError):
            continue
    return None


def _smoke_operation(network: str, op: Operation) -> bool:
    url = f"http://{op.service}:{op.port}{op.path}"
    proc = docker_cmd(
        [
            "run",
            "--rm",
            "--network",
            network,
            probe_image(),
            "curl",
            "-sf",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            "--max-time",
            "5",
            url,
        ],
        timeout=60,
    )
    if proc.returncode != 0:
        return False
    code = (proc.stdout or "").strip()
    return code.isdigit() and int(code) < 500


def discover_workload_operations(
    repo: Path,
    boot: dict[str, Any],
    network: str,
) -> list[Operation]:
    service, port = _app_target(boot)
    if not service:
        return []
    spec = _fetch_live_openapi(network, service, port, repo.resolve())
    provenance = "runtime_observation"
    if spec is None:
        spec = _load_repo_openapi(repo.resolve())
        provenance = "api_spec"
    if spec is None:
        # Fall back to the boot health endpoint only (from live probe URL, not a hardcoded route).
        health = boot.get("health") or {}
        path = health.get("path") or "/"
        candidates = [
            Operation(
                id="health",
                service=service,
                port=port,
                method="GET",
                path=path,
                provenance="runtime_observation",
            )
        ]
    else:
        candidates = _ops_from_openapi(spec, service, port, provenance)
    passing = [op for op in candidates if _smoke_operation(network, op)]
    hints, _ = load_hints(repo / ".loadline.yaml")
    if hints and hints.exclude_operations:
        skip = set(hints.exclude_operations)
        passing = [op for op in passing if op.id not in skip]
    return passing


def operations_to_mix(operations: list[Operation]) -> list[dict[str, Any]]:
    if not operations:
        return []
    weight = max(1, 100 // len(operations))
    mix: list[dict[str, Any]] = []
    for op in operations:
        mix.append(
            {
                "weight": weight,
                "op": {
                    "id": op.id,
                    "service": op.service,
                    "port": op.port,
                    "selector": {"method": op.method, "path": op.path},
                },
            }
        )
    return mix
