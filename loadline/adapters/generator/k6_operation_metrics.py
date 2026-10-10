"""Aggregate per-operation k6 summary metrics in Python (not only handleSummary)."""

from __future__ import annotations

import re
from typing import Any

_TAG_RE = re.compile(r"^[^{]+\{(.+)\}$")


def parse_metric_tags(metric_name: str) -> dict[str, str] | None:
    m = _TAG_RE.match(metric_name.strip())
    if not m:
        return None
    tags: dict[str, str] = {}
    for part in m.group(1).split(","):
        if ":" not in part:
            continue
        k, v = part.split(":", 1)
        tags[k.strip()] = v.strip()
    return tags or None


def _metric_values(metrics: dict[str, Any], name: str) -> dict[str, Any]:
    block = metrics.get(name) or {}
    values = block.get("values") or {}
    return values if isinstance(values, dict) else {}


def aggregate_operations_from_metrics(metrics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build per-operation counts, status breakdown, error rate, and latency percentiles."""
    ops: dict[str, dict[str, Any]] = {}

    for name, block in metrics.items():
        if not isinstance(block, dict):
            continue
        tags = parse_metric_tags(name)
        if not tags or "operation" not in tags:
            continue
        op_id = tags["operation"]
        row = ops.setdefault(
            op_id,
            {
                "status_counts": {},
                "count": 0,
                "error_count": 0,
                "http_req_failed_rate": None,
                "p50_ms": None,
                "p95_ms": None,
                "duration_samples": 0,
            },
        )
        values = block.get("values") or {}
        if not isinstance(values, dict):
            continue

        if name.startswith("http_reqs"):
            status = tags.get("status", "0")
            c = int(values.get("count") or 0)
            row["count"] += c
            row["status_counts"][status] = row["status_counts"].get(status, 0) + c
            if status and not status.startswith("2"):
                row["error_count"] += c
        elif name.startswith("http_req_failed"):
            rate = values.get("rate")
            if rate is not None:
                row["http_req_failed_rate"] = float(rate)
        elif name.startswith("http_req_duration"):
            med = values.get("med")
            p95 = values.get("p(95)")
            cnt = int(values.get("count") or row["count"] or 0)
            if med is not None:
                row["p50_ms"] = float(med)
            if p95 is not None:
                row["p95_ms"] = float(p95)
            if cnt:
                row["duration_samples"] = max(row["duration_samples"], cnt)

    for row in ops.values():
        total = int(row["count"] or 0)
        if row["http_req_failed_rate"] is not None:
            row["error_rate"] = float(row["http_req_failed_rate"])
        elif total:
            row["error_rate"] = float(row["error_count"]) / total
        else:
            row["error_rate"] = 0.0
        if row["error_count"] == 0 and row["status_counts"]:
            row["error_count"] = sum(
                c for st, c in row["status_counts"].items() if not str(st).startswith("2")
            )
    return ops


def merge_operation_stats(
    from_metrics: dict[str, dict[str, Any]],
    from_payload: dict[str, Any] | None,
    *,
    duration_s: int,
) -> dict[str, dict[str, Any]]:
    """Prefer parser aggregation; fill gaps from handleSummary operations blob."""
    merged: dict[str, dict[str, Any]] = {}
    for op_id, row in from_metrics.items():
        count = int(row.get("count") or 0)
        merged[op_id] = {
            "count": count,
            "error_count": int(row.get("error_count") or 0),
            "error_rate": float(row.get("error_rate") or 0),
            "p50_ms": row.get("p50_ms"),
            "p95_ms": row.get("p95_ms"),
            "status_counts": dict(row.get("status_counts") or {}),
            "achieved_rps": count / duration_s if duration_s else 0.0,
        }
    if from_payload:
        for op_id, row in from_payload.items():
            if not isinstance(row, dict):
                continue
            op_id = str(op_id)
            base = merged.setdefault(
                op_id,
                {
                    "count": 0,
                    "error_count": 0,
                    "error_rate": 0.0,
                    "p50_ms": None,
                    "p95_ms": None,
                    "status_counts": {},
                    "achieved_rps": 0.0,
                },
            )
            if not base["count"]:
                base["count"] = int(row.get("count") or row.get("http_reqs") or 0)
            if not base["status_counts"]:
                base["status_counts"] = dict(row.get("status_counts") or {})
            if base["p50_ms"] is None:
                base["p50_ms"] = row.get("p50_ms")
            if base["p95_ms"] is None:
                base["p95_ms"] = row.get("p95_ms")
            if base["error_rate"] == 0 and row.get("http_req_failed") is not None:
                base["error_rate"] = float(row.get("http_req_failed") or 0)
            if duration_s and base["count"]:
                base["achieved_rps"] = base["count"] / duration_s
    return merged
