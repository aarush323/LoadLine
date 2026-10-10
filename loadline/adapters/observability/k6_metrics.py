"""k6 summary → MetricSeries (tech_doc.md §10.2)."""

from __future__ import annotations

from loadline.adapters.generator.k6_summary import K6Summary, format_percentile, successful_request_count
from loadline.core.metrics import MetricSeries, MetricPoint


def k6_summary_to_series(summary: K6Summary, *, evidence_prefix: str = "ev-k6") -> list[MetricSeries]:
    if not summary.parse_ok:
        return []
    samples = successful_request_count(summary)
    series: list[MetricSeries] = [
        MetricSeries(
            name="throughput_rps",
            unit="req/s",
            entity="generator",
            kind="rate",
            points=[MetricPoint(t=0.0, value=summary.throughput_rps or 0.0)],
            coverage=1.0,
            evidence_id=f"{evidence_prefix}-throughput",
        ),
        MetricSeries(
            name="err_rate",
            unit="ratio",
            entity="generator",
            kind="gauge",
            points=[MetricPoint(t=0.0, value=summary.err_rate or 0.0)],
            coverage=1.0,
            evidence_id=f"{evidence_prefix}-err-rate",
        ),
        MetricSeries(
            name="dropped_iterations",
            unit="count",
            entity="generator",
            kind="counter",
            points=[MetricPoint(t=0.0, value=float(summary.dropped_iterations))],
            coverage=1.0,
            evidence_id=f"{evidence_prefix}-dropped",
        ),
        MetricSeries(
            name="vus_max",
            unit="count",
            entity="generator",
            kind="gauge",
            points=[MetricPoint(t=0.0, value=float(summary.vus_max or 0))],
            coverage=1.0 if summary.vus_max is not None else 0.0,
            evidence_id=f"{evidence_prefix}-vus",
        ),
    ]
    p50 = format_percentile(samples, "p50", summary.p50_ms)
    p95 = format_percentile(samples, "p95", summary.p95_ms)
    series.append(
        MetricSeries(
            name="p50_ms",
            unit="ms",
            entity="client",
            kind="gauge",
            points=[MetricPoint(t=0.0, value=p50)],
            coverage=1.0 if isinstance(p50, str) and p50.startswith("not measured") else 1.0,
            evidence_id=f"{evidence_prefix}-p50",
        )
    )
    series.append(
        MetricSeries(
            name="p95_ms",
            unit="ms",
            entity="client",
            kind="gauge",
            points=[MetricPoint(t=0.0, value=p95)],
            coverage=1.0 if samples >= 200 else samples / 200.0,
            evidence_id=f"{evidence_prefix}-p95",
        )
    )
    for op_id, op_data in (summary.operations or {}).items():
        series.append(
            MetricSeries(
                name="http_reqs",
                unit="count",
                entity=f"operation:{op_id}",
                kind="counter",
                points=[MetricPoint(t=0.0, value=float(op_data.get("http_reqs", 0)))],
                coverage=1.0,
                evidence_id=f"{evidence_prefix}-op-{op_id}",
            )
        )
    return series
