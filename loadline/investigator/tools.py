"""Investigator tools: repo, read_file, run_k6."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from loadline.investigator.deps import InvestigationDeps, ReadRange
from loadline.investigator.k6_tool import run_k6 as execute_run_k6
from loadline.investigator.repo_routes import discover_routes

FORBIDDEN_READ = re.compile(r"(\.env|\.pem|credentials|id_rsa)", re.I)


class EndpointSpec(BaseModel):
    id: str | None = None
    method: str = "GET"
    path: str
    weight: int | None = Field(default=None, ge=1)
    body: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    use_auth: bool | None = None


class K6AuthSpec(BaseModel):
    profile: str = "default_user"
    method: str = "POST"
    path: str
    body_encoding: Literal["form", "json"] = "form"
    token_field: str = "access_token"


class RunK6Input(BaseModel):
    endpoints: list[EndpointSpec] = Field(min_length=1)
    rate: float = Field(gt=0)
    duration_s: int = Field(gt=0, le=120)
    auth: K6AuthSpec | None = None


def _deny_path(path: str) -> bool:
    return bool(FORBIDDEN_READ.search(path))


def repo(
    ctx: RunContext[InvestigationDeps],
    action: Literal["search", "def", "neighbors", "impact", "routes"],
    query: str = "",
    symbol: str = "",
) -> dict[str, Any]:
    if action == "routes":
        return discover_routes(ctx.deps)
    if action == "search":
        if not query.strip():
            return {"error": "query is required for action=search"}
        return search_code(ctx, query)
    if not symbol.strip():
        return {"error": "symbol is required for graph actions"}
    return code_graph(ctx, action, symbol)


def search_code(ctx: RunContext[InvestigationDeps], query: str) -> dict[str, Any]:
    deps = ctx.deps
    hits: list[dict[str, Any]] = []
    coverage = "entire"
    if deps.graph is not None:
        try:
            cmd = deps.graph.ranked_command()
            args = [
                cmd,
                "--repo",
                str(deps.repo_root),
                "--query",
                query,
                "--format",
                "json",
                "--top-k",
                "8",
                "--profile",
                "full",
            ]
            out = deps.graph.run(args)
            if out.ok:
                hits.append({"source": "entire_graph", "command": cmd, "text": out.text[:6000]})
            else:
                coverage = "degraded"
        except Exception as exc:
            coverage = "degraded"
            hits.append({"source": "entire_graph", "error": str(exc)})
    try:
        proc = subprocess.run(
            ["rg", "-n", "--max-count", "20", query, str(deps.repo_root)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError:
        proc = None
    if proc and proc.stdout:
        hits.append({"source": "ripgrep", "text": proc.stdout[:4000]})
    if not hits:
        return {"hits": [], "coverage": coverage, "note": "empty result; try another query"}
    return {"hits": hits, "coverage": coverage}


def code_graph(
    ctx: RunContext[InvestigationDeps],
    mode: Literal["def", "neighbors", "impact"],
    symbol: str,
) -> dict[str, Any]:
    deps = ctx.deps
    if deps.graph is None:
        return {"error": "code graph unavailable", "degraded": True}
    if mode == "neighbors":
        args = ["neighbors", "--repo", str(deps.repo_root), "--symbol", symbol]
    elif mode == "impact":
        args = ["impact", "--repo", str(deps.repo_root), "--symbol", symbol]
    else:
        args = ["def", "--repo", str(deps.repo_root), "--symbol", symbol]
    if deps.dirty_worktree and deps.graph.edges_supports_worktree():
        args.append("--worktree")
    out = deps.graph.run(args)
    return {
        "mode": mode,
        "symbol": symbol,
        "text": out.text[:6000],
        "ok": out.ok,
    }


def read_file(
    ctx: RunContext[InvestigationDeps],
    path: str,
    start_line: int,
    end_line: int,
) -> dict[str, Any]:
    deps = ctx.deps
    if end_line - start_line > 200:
        return {"error": "range too large; use at most 200 lines per call"}
    if Path(path).is_absolute() or "loadline/runs" in path.replace("\\", "/"):
        return {
            "error": (
                "read_file is for repo-relative application source only; "
                "use run_k6 return values for experiment metrics (not run-dir k6 logs)."
            )
        }
    target = (deps.repo_root / path).resolve()
    if not str(target).startswith(str(deps.repo_root.resolve())):
        return {
            "error": (
                "path outside repository; read_file is for application source under the analyzed repo only."
            )
        }
    if _deny_path(path):
        return {"error": "path denied by policy"}
    if not target.is_file():
        return {"error": "file not found"}
    if end_line < start_line:
        return {"error": "end_line must be >= start_line"}
    lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
    start = max(1, start_line)
    end = min(len(lines), end_line)
    snippet = "\n".join(f"{i + 1}:{lines[i]}" for i in range(start - 1, end))
    deps.read_ranges.append(ReadRange(path=path, start_line=start, end_line=end))
    evidence_id = f"ev-read-{len(deps.read_ranges)}"
    return {"path": path, "start_line": start, "end_line": end, "snippet": snippet[:6000], "evidence_id": evidence_id}


def run_k6_tool(ctx: RunContext[InvestigationDeps], payload: RunK6Input) -> dict[str, Any]:
    endpoints = [ep.model_dump(exclude_none=True) for ep in payload.endpoints]
    auth = payload.auth.model_dump(exclude_none=True) if payload.auth else None
    return execute_run_k6(ctx.deps, endpoints, payload.rate, payload.duration_s, auth=auth)
