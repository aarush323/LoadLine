"""Route inventory for repo(action=routes) — Entire HANDLES_ROUTE with fallbacks."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from loadline.entire_runtime.analyze import load_openapi
from loadline.entire_runtime.errors import GraphInvocationError
from loadline.investigator.deps import InvestigationDeps

_OPENAPI_CANDIDATES = (
    "openapi.json",
    "openapi.yaml",
    "swagger.json",
    "docs/openapi.json",
    "api/openapi.json",
)


def _normalize_path(path: str) -> str:
    p = path.strip()
    if not p.startswith("/"):
        p = f"/{p}"
    return p


def _is_http_route_path(path: str) -> bool:
    """Reject filesystem paths mistaken for HTTP routes in graph exports."""
    p = path.strip()
    if not p.startswith("/"):
        return False
    if len(p) > 200:
        return False
    lowered = p.lower()
    if lowered.startswith(("/home/", "/users/", "/var/", "/tmp/")):
        return False
    if "/projects/" in lowered or "/integration/targets/" in lowered:
        return False
    if " " in p:
        return False
    return True


def _record_route(
    routes: list[dict[str, Any]],
    seen: set[tuple[str, str]],
    *,
    method: str,
    path: str,
    handler: str | None = None,
    file: str | None = None,
    line: int | None = None,
    source: str,
) -> None:
    m = method.upper()
    p = _normalize_path(path)
    key = (m, p)
    if key in seen:
        return
    seen.add(key)
    routes.append(
        {
            "method": m,
            "path": p,
            "handler": handler,
            "file": file,
            "line": line,
            "source": source,
        }
    )


def _openapi_from_repo(repo_root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for name in _OPENAPI_CANDIDATES:
        path = repo_root / name
        if not path.is_file() or path.suffix.lower() not in (".json",):
            continue
        try:
            ops = load_openapi(path, live=False)
        except (OSError, ValueError):
            continue
        for op in ops:
            _record_route(out, seen, method=op.method, path=op.path, source="openapi_file")
    return out


def _routes_from_handles_route(deps: InvestigationDeps) -> tuple[list[dict[str, Any]], list[str]]:
    notes: list[str] = []
    routes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    client = deps.graph
    if client is None:
        return routes, ["code graph unavailable"]
    try:
        caps = client.capabilities()
    except GraphInvocationError as exc:
        return routes, [f"capabilities unavailable: {exc}"]
    relations = list(caps.get("supported_relation_types") or [])
    if "HANDLES_ROUTE" not in relations:
        return routes, ["HANDLES_ROUTE not in graph capabilities; using fallbacks only"]
    edge_args = ["edges", "--repo", str(deps.repo_root), "--format", "ndjson", "--relation", "HANDLES_ROUTE"]
    if deps.dirty_worktree:
        if client.edges_supports_worktree():
            edge_args.append("--worktree")
        else:
            notes.append("dirty worktree and graph cannot export route edges; HANDLES_ROUTE skipped")
            return routes, notes
    out = client.run(edge_args)
    if out.timed_out or not out.ok:
        notes.append("HANDLES_ROUTE export failed or was truncated")
        return routes, notes
    for record in out.records:
        method = (
            str(record.get("method") or record.get("http_method") or record.get("verb") or "GET")
        ).upper()
        path = record.get("route") or record.get("path") or record.get("url_path")
        if not isinstance(path, str) or not path.strip():
            blob = json.dumps(record)
            for m in re.finditer(r'"(/[^"]+)"', blob):
                candidate = m.group(1)
                if _is_http_route_path(candidate):
                    path = candidate
                    break
        if not path:
            continue
        path = str(path)
        if not _is_http_route_path(path):
            notes.append(f"skipped non-route HANDLES_ROUTE path: {path[:80]}")
            continue
        handler = record.get("symbol") or record.get("handler") or record.get("name")
        if handler is not None:
            handler = str(handler)
        file_path = record.get("file") or record.get("file_path")
        if isinstance(file_path, str) and file_path.startswith(str(deps.repo_root)):
            try:
                file_path = str(Path(file_path).relative_to(deps.repo_root.resolve()))
            except ValueError:
                pass
        line = record.get("line") or record.get("start_line")
        line_i = int(line) if isinstance(line, int) or (isinstance(line, str) and line.isdigit()) else None
        _record_route(
            routes,
            seen,
            method=method,
            path=str(path),
            handler=handler,
            file=file_path if isinstance(file_path, str) else None,
            line=line_i,
            source="HANDLES_ROUTE",
        )
    return routes, notes


def _routes_from_ripgrep(repo_root: Path) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    try:
        proc = subprocess.run(
            ["rg", "-n", "--no-heading", r'@(app|router)\.', str(repo_root)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return routes
    if not proc.stdout:
        return routes
    for line in proc.stdout.splitlines()[:80]:
        for pat in (
            re.compile(r'\.(get|post|put|patch|delete)\(\s*["\']([^"\']+)["\']', re.I),
            re.compile(r'@router\.(get|post|put|patch|delete)\(\s*["\']([^"\']+)["\']', re.I),
        ):
            m = pat.search(line)
            if m:
                _record_route(
                    routes,
                    seen,
                    method=m.group(1).upper(),
                    path=m.group(2),
                    source="source_search",
                )
    return routes


def discover_routes(deps: InvestigationDeps) -> dict[str, Any]:
    """Best-effort route list. Never claims exhaustiveness unless only live OpenAPI+edges merged."""
    routes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    notes: list[str] = []
    sources_used: list[str] = []

    graph_routes, graph_notes = _routes_from_handles_route(deps)
    notes.extend(graph_notes)
    if graph_routes:
        sources_used.append("HANDLES_ROUTE")
        for r in graph_routes:
            _record_route(
                routes,
                seen,
                method=r["method"],
                path=r["path"],
                handler=r.get("handler"),
                file=r.get("file"),
                line=r.get("line"),
                source=r["source"],
            )

    for r in _openapi_from_repo(deps.repo_root):
        if (r["method"], r["path"]) not in seen:
            sources_used.append("openapi_file")
        _record_route(routes, seen, method=r["method"], path=r["path"], source=r["source"])

    boot = deps.boot or {}
    health = boot.get("health") or {}
    openapi_url = health.get("openapi_url") or health.get("openapi")
    if isinstance(openapi_url, str) and openapi_url.startswith("http"):
        notes.append("live OpenAPI URL is not fetched by this tool; use repo search or committed openapi.json")

    spec_routes = _routes_from_ripgrep(deps.repo_root)
    if spec_routes:
        sources_used.append("source_search")
        for r in spec_routes:
            _record_route(routes, seen, method=r["method"], path=r["path"], source=r["source"])

    exhaustive = bool(graph_routes) and deps.graph is not None and "HANDLES_ROUTE not" not in " ".join(notes)
    if not routes:
        notes.append("no routes found; try repo(action=search) with a path or framework keyword")
    elif not exhaustive:
        notes.append("inventory is not guaranteed complete — confirm with search and read_file")

    return {
        "routes": routes,
        "count": len(routes),
        "exhaustive": exhaustive,
        "sources": sorted(set(sources_used)),
        "notes": notes,
        "coverage": "degraded" if deps.graph is None or deps.graph_degraded else "entire",
    }
