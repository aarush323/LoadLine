"""Repository analysis that uses Entire Graph and does not modify the repo."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from loadline.entire_runtime.errors import GraphInvocationError
from loadline.entire_runtime.graph import GraphClient
from loadline.entire_runtime.install import Toolchain, ensure_toolchain

SECRET_NAMES = {".env", ".env.local"}


@dataclass
class Operation:
    method: str
    path: str
    provenance: str


@dataclass
class RouteEvidence:
    method: str
    path: str
    provenance: str
    handler_file: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    source_excerpt: str | None = None
    source_read: bool = False
    relation: str | None = None
    note: str = "A graph location is not a cause. Source was read only when source_read is true."


@dataclass
class Analysis:
    repo: str
    cli_version: str
    graph_version: str
    toolchain_source: str
    dirty: bool
    ranked_command: str
    handles_route: bool
    degraded: list[str] = field(default_factory=list)
    routes: list[RouteEvidence] = field(default_factory=list)
    capabilities_relations: list[str] = field(default_factory=list)


def operations_from_openapi(document: dict, *, provenance: str) -> list[Operation]:
    paths = document.get("paths") or {}
    found: list[Operation] = []
    if not isinstance(paths, dict):
        return found
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            if method in item:
                found.append(Operation(method.upper(), str(path), provenance))
    return found


def load_openapi(path: Path, *, live: bool) -> list[Operation]:
    text = path.read_text()
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not JSON OpenAPI: {exc}") from exc
    provenance = "live_openapi" if live else "openapi_file"
    return operations_from_openapi(document, provenance=provenance)


def _dirty(repo: Path) -> bool:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=repo,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return bool(out.strip())


def _read_excerpt(repo: Path, relative: str, start: int, end: int) -> str | None:
    candidate = (repo / relative).resolve()
    try:
        candidate.relative_to(repo.resolve())
    except ValueError:
        return None
    if candidate.name in SECRET_NAMES or candidate.suffix == ".pem":
        return None
    if not candidate.is_file():
        return None
    lines = candidate.read_text(errors="replace").splitlines()
    start = max(1, start)
    end = min(len(lines), max(start, end))
    if end - start > 200:
        end = start + 199
    return "\n".join(lines[start - 1 : end])


def _first_hit(payload: object) -> tuple[str, int, int] | None:
    if not isinstance(payload, dict):
        return None
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return None
    hit = results[0]
    if not isinstance(hit, dict):
        return None
    file_path = hit.get("file_path")
    start = hit.get("start_line")
    end = hit.get("end_line") or start
    if not isinstance(file_path, str) or not isinstance(start, int):
        return None
    if not isinstance(end, int):
        end = start
    return file_path, start, end


def _route_in_records(records: list[dict], path: str) -> dict | None:
    for record in records:
        blob = json.dumps(record)
        if path in blob:
            return record
    return None


def analyze_repository(
    repo: Path,
    *,
    openapi: Path | None = None,
    live_openapi: bool = False,
    toolchain: Toolchain | None = None,
    client: GraphClient | None = None,
) -> Analysis:
    """Map live or file OpenAPI operations through Entire Graph.

    Does not run ``init-agents`` and does not write into ``repo``.
    """

    repo = repo.resolve()
    toolchain = toolchain or ensure_toolchain()
    client = client or GraphClient(toolchain)
    dirty = _dirty(repo)
    degraded: list[str] = []
    try:
        ranked = client.ranked_command()
    except GraphInvocationError as exc:
        raise GraphInvocationError(str(exc)) from exc
    try:
        caps = client.capabilities()
    except GraphInvocationError as exc:
        return Analysis(
            repo=str(repo),
            cli_version=toolchain.cli_version,
            graph_version=toolchain.graph_version,
            toolchain_source=toolchain.source,
            dirty=dirty,
            ranked_command=ranked,
            handles_route=False,
            degraded=[f"capabilities unavailable: {exc}"],
        )
    relations = list(caps.get("supported_relation_types") or [])
    handles = "HANDLES_ROUTE" in relations
    if not handles:
        degraded.append("HANDLES_ROUTE is not in this build's capabilities. Route mapping uses ranked search only.")
    operations: list[Operation] = []
    if openapi is not None:
        operations = load_openapi(openapi, live=live_openapi)
    else:
        degraded.append("No live OpenAPI document was supplied. HTTP routes were not taken from a booted service.")

    route_records: list[dict] = []
    if handles and operations:
        edge_args = ["edges", "--repo", str(repo), "--format", "ndjson", "--relation", "HANDLES_ROUTE"]
        if dirty:
            if client.edges_supports_worktree():
                edge_args.append("--worktree")
            else:
                degraded.append("Working tree is dirty and this graph build cannot export edges from it. Route edges were skipped.")
                edge_args = []
        if edge_args:
            edges = client.run(edge_args)
            if edges.timed_out or not edges.ok:
                degraded.append("HANDLES_ROUTE export failed or was truncated. Coverage is degraded.")
            else:
                route_records = edges.records

    evidence: list[RouteEvidence] = []
    for operation in operations:
        item = RouteEvidence(operation.method, operation.path, operation.provenance)
        matched = _route_in_records(route_records, operation.path)
        if matched is not None:
            item.relation = "HANDLES_ROUTE"
            file_path = matched.get("file") or matched.get("file_path") or matched.get("path")
            if isinstance(file_path, str):
                item.handler_file = file_path
        search_args = [
            ranked,
            "--repo",
            str(repo),
            "--query",
            f"HTTP {operation.method} {operation.path} handler",
            "--format",
            "json",
            "--top-k",
            "3",
            "--profile",
            "full",
        ]
        found = client.run(search_args)
        if not found.ok or found.data is None:
            degraded.append(f"Ranked search failed for {operation.method} {operation.path}.")
        else:
            hit = _first_hit(found.data)
            if hit is not None and item.handler_file is None:
                item.handler_file, item.start_line, item.end_line = hit
            elif hit is not None:
                _file, item.start_line, item.end_line = hit
        if item.handler_file and item.start_line:
            excerpt = _read_excerpt(repo, item.handler_file, item.start_line, item.end_line or item.start_line)
            if excerpt is not None:
                item.source_excerpt = excerpt
                item.source_read = True
            else:
                degraded.append(f"Could not read source for {operation.method} {operation.path}. The graph hit is not evidence.")
        evidence.append(item)

    if not operations:
        search_args = [ranked, "--repo", str(repo), "--query", "HTTP route handlers", "--format", "json", "--top-k", "3", "--profile", "full"]
        overview = client.run(search_args)
        if not overview.ok:
            degraded.append("Repository search failed.")

    return Analysis(
        repo=str(repo),
        cli_version=toolchain.cli_version,
        graph_version=toolchain.graph_version,
        toolchain_source=toolchain.source,
        dirty=dirty,
        ranked_command=ranked,
        handles_route=handles,
        degraded=degraded,
        routes=evidence,
        capabilities_relations=relations,
    )
