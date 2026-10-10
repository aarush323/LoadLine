"""Format Pydantic AI stream events for investigate-phase terminal lines."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
)

_SECRET_KEY_RE = re.compile(r"(password|secret|token|authorization|api[_-]?key)", re.I)


def _redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in data.items():
        if _SECRET_KEY_RE.search(str(key)):
            out[key] = "<redacted>"
        elif isinstance(val, dict):
            out[key] = _redact_mapping(val)
        else:
            out[key] = val
    return out


def _parse_tool_args(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return _redact_mapping(raw)
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return _redact_mapping(parsed) if isinstance(parsed, dict) else {}


def format_tool_call(event: FunctionToolCallEvent, *, verbose: bool = False) -> str:
    part = event.part
    name = part.tool_name or "tool"
    args = _parse_tool_args(part.args)
    if name == "repo":
        action = args.get("action", "")
        if action == "routes":
            return "→ repo routes"
        if action == "search":
            q = str(args.get("query", ""))[:80]
            return f"→ repo search {q!r}"
        sym = str(args.get("symbol", ""))[:60]
        return f"→ repo {action} {sym}"
    if name == "read_file":
        path = str(args.get("path", ""))[:120]
        start = args.get("start_line", "?")
        end = args.get("end_line", "?")
        return f"→ read_file {path} L{start}-L{end}"
    if name == "run_k6":
        eps = args.get("endpoints") or []
        n_ops = len(eps) if isinstance(eps, list) else 0
        op_ids: list[str] = []
        if isinstance(eps, list):
            for ep in eps[:6]:
                if isinstance(ep, dict):
                    op_ids.append(str(ep.get("id") or ep.get("path", "?"))[:32])
        ops_s = ",".join(op_ids) if op_ids else str(n_ops)
        rate = args.get("rate", "?")
        dur = args.get("duration_s", "?")
        line = f"→ run_k6 rate={rate} duration={dur}s ops={ops_s}"
        if verbose and args.get("auth"):
            line += " auth=default_user"
        return line
    if verbose:
        return f"→ {name} {json.dumps(args)[:120]}"
    return f"→ {name}"


def _summarize_run_k6_result(data: dict[str, Any]) -> str:
    if data.get("error"):
        return f"error {str(data['error'])[:100]}"
    exp = data.get("experiment_id", "")
    dropped = data.get("dropped_iterations", 0)
    parts = [f"exp {exp}".strip()]
    ops = data.get("operations") or {}
    if isinstance(ops, dict):
        for op_id, row in list(ops.items())[:3]:
            if not isinstance(row, dict):
                continue
            p95 = row.get("p95_ms")
            if p95 is not None:
                parts.append(f"p95_{op_id}={int(round(float(p95)))}ms")
            err = int(row.get("error_count") or 0)
            if err:
                parts.append(f"err_{op_id}={err}")
    if dropped:
        parts.append(f"dropped={dropped}")
    return " ".join(parts)


def _tool_result_data(event: FunctionToolResultEvent) -> dict[str, Any]:
    content = event.content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return _redact_mapping(parsed)
        except json.JSONDecodeError:
            pass
    elif isinstance(content, dict):
        return _redact_mapping(content)
    part_content = getattr(event.part, "content", None)
    if isinstance(part_content, dict):
        return _redact_mapping(part_content)
    if isinstance(part_content, str):
        try:
            parsed = json.loads(part_content)
            if isinstance(parsed, dict):
                return _redact_mapping(parsed)
        except json.JSONDecodeError:
            pass
    return {}


def _read_file_line_count(data: dict[str, Any]) -> int:
    start = data.get("start_line")
    end = data.get("end_line")
    if isinstance(start, int) and isinstance(end, int) and end >= start:
        return end - start + 1
    snippet = data.get("snippet") or ""
    if snippet:
        return snippet.count("\n") + 1
    return 0


def format_tool_result(event: FunctionToolResultEvent, *, verbose: bool = False) -> str:
    part = event.part
    tool_name = getattr(part, "tool_name", None) or "tool"
    data = _tool_result_data(event)
    if tool_name == "repo":
        if data.get("error"):
            return f"← repo error {str(data['error'])[:80]}"
        routes = data.get("routes")
        if isinstance(routes, list):
            return f"← repo {len(routes)} routes"
        hits = data.get("hits")
        if isinstance(hits, list):
            return f"← repo {len(hits)} hits"
        return "← repo ok"
    if tool_name == "read_file":
        if data.get("error"):
            return f"← read_file error {str(data['error'])[:60]}"
        lines = _read_file_line_count(data)
        return f"← read_file {lines} lines"
    if tool_name == "run_k6":
        return f"← run_k6 {_summarize_run_k6_result(data)}"
    if data.get("error"):
        return f"← {tool_name} error {str(data['error'])[:80]}"
    if verbose:
        return f"← {tool_name} ok"
    return f"← {tool_name}"


def format_stream_event(event: Any, *, verbose: bool = False) -> str | None:
    if isinstance(event, FunctionToolCallEvent):
        return format_tool_call(event, verbose=verbose)
    if isinstance(event, FunctionToolResultEvent):
        return format_tool_result(event, verbose=verbose)
    if isinstance(event, PartStartEvent):
        return "model request" if verbose else None
    if isinstance(event, PartDeltaEvent):
        return None
    event_kind = getattr(event, "event_kind", None)
    if event_kind == "function_tool_call":
        return format_tool_call(event, verbose=verbose)
    if event_kind == "function_tool_result":
        return format_tool_result(event, verbose=verbose)
    return None
