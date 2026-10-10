"""Loadline custom attributes on neatlogs TOOL spans (tech_doc.md §14)."""

from __future__ import annotations

from typing import Any


def annotate_tool_span(
    result: dict[str, Any],
    *,
    adapter: str | None = None,
    experiment_kind: str | None = None,
) -> dict[str, Any]:
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span is None or not span.is_recording():
            return result
        status = result.get("status")
        ok = status not in ("rejected",) and "error" not in result
        span.set_attribute("loadline.ok", ok)
        if adapter:
            span.set_attribute("loadline.adapter", adapter)
        if experiment_kind:
            span.set_attribute("loadline.experiment_kind", experiment_kind)
        rid = result.get("evidence_id")
        if not rid:
            evs = result.get("evidence_ids")
            if isinstance(evs, list) and evs:
                rid = evs[0]
        if rid:
            span.set_attribute("loadline.result_id", str(rid))
    except Exception:
        pass
    return result
