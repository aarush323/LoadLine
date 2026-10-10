"""Parse k6 handleSummary JSON (tech_doc.md §9)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from loadline.adapters.generator.k6_operation_metrics import (
    aggregate_operations_from_metrics,
    merge_operation_stats,
)
from loadline.constants import MIN_SAMPLES, MIN_SAMPLES_P99
from loadline.core.verdict import percentile_allowed

PercentileLabel = Literal["p50", "p95", "p99"]


@dataclass
class K6Summary:
    parse_ok: bool
    throughput_rps: float | None = None
    p50_ms: float | None = None
    p95_ms: float | None = None
    p99_ms: float | None = None
    err_rate: float | None = None
    dropped_iterations: int = 0
    vus_max: int | None = None
    operations: dict[str, dict[str, Any]] = field(default_factory=dict)
    raw_json: dict[str, Any] | None = None
    error: str | None = None


def _extract_summary_json(stdout: str) -> dict[str, Any] | None:
    text = stdout.strip()
    if not text:
        return None
    # handleSummary prints JSON; scan from the last line that looks like a full object.
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    match = re.search(r"\{.*\}\s*$", text, re.S)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _metric_values(data: dict[str, Any], name: str) -> dict[str, Any]:
    metrics = data.get("metrics") or {}
    block = metrics.get(name) or {}
    values = block.get("values") or {}
    return values if isinstance(values, dict) else {}


def parse_handle_summary(stdout: str) -> K6Summary:
    try:
        payload = _extract_summary_json(stdout)
        if not payload:
            return K6Summary(parse_ok=False, error="no summary json in stdout")
        reqs = _metric_values(payload, "http_reqs")
        dur = _metric_values(payload, "http_req_duration")
        failed = _metric_values(payload, "http_req_failed")
        dropped = _metric_values(payload, "dropped_iterations")
        vus = _metric_values(payload, "vus")
        metrics = payload.get("metrics") or {}
        duration_s = int(payload.get("duration_s") or 0)
        if not duration_s:
            dur_ms = (payload.get("state") or {}).get("testRunDurationMs")
            if isinstance(dur_ms, (int, float)) and dur_ms > 0:
                duration_s = max(1, int(round(dur_ms / 1000)))
        from_metrics = aggregate_operations_from_metrics(metrics if isinstance(metrics, dict) else {})
        merged_ops = merge_operation_stats(
            from_metrics,
            payload.get("operations") if isinstance(payload.get("operations"), dict) else None,
            duration_s=duration_s or 1,
        )
        return K6Summary(
            parse_ok=True,
            throughput_rps=float(reqs.get("rate")) if reqs.get("rate") is not None else None,
            p50_ms=float(dur.get("med")) if dur.get("med") is not None else None,
            p95_ms=float(dur.get("p(95)")) if dur.get("p(95)") is not None else None,
            p99_ms=float(dur.get("p(99)")) if dur.get("p(99)") is not None else None,
            err_rate=float(failed.get("rate")) if failed.get("rate") is not None else None,
            dropped_iterations=int(dropped.get("count") or 0),
            vus_max=int(vus.get("max") or 0) if vus.get("max") is not None else None,
            operations=merged_ops,
            raw_json=payload,
        )
    except (TypeError, ValueError) as exc:
        return K6Summary(parse_ok=False, error=str(exc))


def successful_request_count(summary: K6Summary) -> int:
    if not summary.parse_ok or not summary.raw_json:
        return 0
    checks = (summary.raw_json.get("root_group") or {}).get("checks") or []
    check_passes = sum(int(c.get("passes") or 0) for c in checks if isinstance(c, dict))
    if check_passes:
        return check_passes
    reqs = _metric_values(summary.raw_json, "http_reqs")
    count = int(reqs.get("count") or 0)
    failed = _metric_values(summary.raw_json, "http_req_failed")
    rate = float(failed.get("rate") or 0)
    return max(0, int(round(count * (1.0 - rate))))


def format_percentile(samples: int, which: PercentileLabel, value: float | None) -> str:
    if value is None:
        return f"not measured (samples={samples})"
    if not percentile_allowed(samples, which):
        return f"not measured (samples={samples})"
    return str(value)
