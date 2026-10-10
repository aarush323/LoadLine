"""Extract prediction readouts from an instrumented load step."""

from __future__ import annotations

from typing import Any

from loadline.adapters.observability.step_telemetry import InstrumentedStepResult
from loadline.core.verdict import moves_bracket


def readouts_from_step(result: InstrumentedStepResult) -> dict[str, dict[str, Any]]:
    summary = result.k6.summary
    samples = result.k6.successful_samples
    valid = moves_bracket(result.k6.verdict)  # type: ignore[arg-type]
    out: dict[str, dict[str, Any]] = {}
    if summary.p95_ms is not None:
        out["p95_ms"] = {"value": float(summary.p95_ms), "unit": "ms", "samples": samples, "valid_verdict": valid}
    if summary.p50_ms is not None:
        out["p50_ms"] = {"value": float(summary.p50_ms), "unit": "ms", "samples": samples, "valid_verdict": valid}
    if summary.throughput_rps is not None:
        out["throughput_rps"] = {
            "value": float(summary.throughput_rps),
            "unit": "rps",
            "samples": samples,
            "valid_verdict": valid,
        }
    err = summary.err_rate if summary.err_rate is not None else 0.0
    out["err_rate"] = {"value": float(err), "unit": "ratio", "samples": samples, "valid_verdict": valid}
    if summary.p95_ms is not None and summary.throughput_rps is not None:
        implied = summary.throughput_rps * (summary.p95_ms / 1000.0)
        out["implied_concurrency"] = {
            "value": float(implied),
            "unit": "count",
            "samples": samples,
            "valid_verdict": valid,
        }
    _append_container_readouts(result, out, samples, valid)
    return out


def _append_container_readouts(
    result: InstrumentedStepResult,
    out: dict[str, dict[str, Any]],
    samples: int,
    valid: bool,
) -> None:
    for series in result.series:
        if series.entity != "app":
            continue
        if series.name == "cpu_percent" and series.points:
            last = series.points[-1].value
            if isinstance(last, (int, float)):
                out["cpu_util"] = {
                    "value": float(last),
                    "unit": "percent",
                    "samples": samples,
                    "valid_verdict": valid,
                    "evidence_id": series.evidence_id,
                }
        if series.name == "throttle" and series.points:
            last = series.points[-1].value
            if isinstance(last, (int, float)):
                out["throttle_ratio"] = {
                    "value": float(last),
                    "unit": str(series.unit or "engine"),
                    "samples": samples,
                    "valid_verdict": valid,
                    "evidence_id": series.evidence_id,
                }


def load_baseline_readouts(run_dir: Any) -> dict[str, dict[str, Any]]:
    import json
    from pathlib import Path

    path = Path(run_dir) / "waves" / "baseline" / "telemetry.json"
    if not path.is_file():
        return {}
    try:
        tele = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    series = tele.get("series") or []
    out: dict[str, dict[str, Any]] = {}
    for item in series:
        name = item.get("name")
        if not name or item.get("value") is None:
            continue
        if name in (
            "p95_ms",
            "p50_ms",
            "throughput_rps",
            "err_rate",
            "implied_concurrency",
            "cpu_util",
            "throttle_ratio",
        ):
            out[str(name)] = {
                "value": float(item["value"]),
                "unit": str(item.get("unit") or ""),
                "samples": int(item.get("samples") or 0),
                "valid_verdict": True,
            }
    return out
