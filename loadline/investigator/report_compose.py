"""Compose investigator report: agent narrative + ledger-backed measurements."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loadline.core.ledger import Ledger
from loadline.investigator.deps import ReadRange

_SECTION_LOAD = "## What happened under load"
_SECTION_APPENDIX = "## Appendix"

_FENCE_RE = re.compile(r"^```", re.MULTILINE)


@dataclass
class OperationMeasurement:
    op_id: str
    method: str = ""
    path: str = ""
    count: int = 0
    error_count: int = 0
    error_rate: float = 0.0
    p50_ms: float | None = None
    p95_ms: float | None = None
    achieved_rps: float | None = None
    http_status_known: bool = False
    status_counts_reliable: bool = False
    status_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class K6ExperimentRecord:
    experiment_id: str
    wave: str
    offered_rps: float
    duration_s: int
    dropped_iterations: int = 0
    operations: list[OperationMeasurement] = field(default_factory=list)


def load_k6_experiments(run_dir: Path, run_id: str) -> list[K6ExperimentRecord]:
    """Load investigator k6 experiments from experiments/*.json and ledger."""
    by_id: dict[str, K6ExperimentRecord] = {}
    exp_dir = run_dir / "experiments"
    if exp_dir.is_dir():
        for path in sorted(exp_dir.glob("exp-k6-*.json")):
            try:
                rec = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            exp_id = str(rec.get("experiment_id") or path.stem)
            by_id[exp_id] = _record_from_persisted(exp_id, rec)

    ledger = Ledger.open(run_dir, run_id)
    for event in ledger.events():
        if event.get("kind") != "k6_run":
            continue
        exp_id = str(event.get("experiment_id") or "")
        if not exp_id:
            continue
        if exp_id not in by_id:
            by_id[exp_id] = _record_from_ledger_event(exp_id, event)
    return sorted(by_id.values(), key=lambda e: (e.offered_rps, e.experiment_id))


def _endpoint_map(tool_input: dict[str, Any]) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for ep in tool_input.get("endpoints") or []:
        if not isinstance(ep, dict):
            continue
        op_id = str(ep.get("id") or ep.get("path") or "")
        if not op_id:
            continue
        method = str(ep.get("method") or "GET").upper()
        path = str(ep.get("path") or "")
        out[op_id] = (method, path)
    return out


def _record_from_persisted(exp_id: str, rec: dict[str, Any]) -> K6ExperimentRecord:
    tool_input = rec.get("input") if isinstance(rec.get("input"), dict) else {}
    tool_output = rec.get("output") if isinstance(rec.get("output"), dict) else {}
    endpoints = _endpoint_map(tool_input)
    wave = str(rec.get("wave") or "")
    return _build_record(
        exp_id,
        wave,
        float(tool_output.get("offered_rps") or tool_input.get("rate") or 0),
        int(tool_output.get("duration_s") or tool_input.get("duration_s") or 0),
        int(tool_output.get("dropped_iterations") or 0),
        tool_output.get("operations") if isinstance(tool_output.get("operations"), dict) else {},
        endpoints,
    )


def _record_from_ledger_event(exp_id: str, event: dict[str, Any]) -> K6ExperimentRecord:
    result = event.get("result") if isinstance(event.get("result"), dict) else {}
    plan = event.get("plan") if isinstance(event.get("plan"), dict) else {}
    shape = plan.get("shape") if isinstance(plan.get("shape"), dict) else {}
    endpoints: dict[str, tuple[str, str]] = {}
    for item in plan.get("mix") or []:
        if not isinstance(item, dict):
            continue
        op = item.get("op") if isinstance(item.get("op"), dict) else {}
        sel = op.get("selector") if isinstance(op.get("selector"), dict) else {}
        op_id = str(op.get("id") or "")
        if op_id:
            endpoints[op_id] = (str(sel.get("method") or "GET").upper(), str(sel.get("path") or ""))
    return _build_record(
        exp_id,
        str(event.get("wave") or ""),
        float(result.get("offered_rps") or shape.get("rate") or 0),
        int(result.get("duration_s") or shape.get("duration") or 0),
        int(result.get("dropped_iterations") or 0),
        result.get("operations") if isinstance(result.get("operations"), dict) else {},
        endpoints,
    )


def _build_record(
    exp_id: str,
    wave: str,
    offered_rps: float,
    duration_s: int,
    dropped: int,
    operations: dict[str, Any],
    endpoints: dict[str, tuple[str, str]],
) -> K6ExperimentRecord:
    ops: list[OperationMeasurement] = []
    for op_id, row in operations.items():
        if not isinstance(row, dict):
            continue
        method, path = endpoints.get(str(op_id), ("", ""))
        ops.append(
            OperationMeasurement(
                op_id=str(op_id),
                method=method,
                path=path,
                count=int(row.get("count") or 0),
                error_count=int(row.get("error_count") or 0),
                error_rate=float(row.get("error_rate") or 0),
                p50_ms=_float_or_none(row.get("p50_ms")),
                p95_ms=_float_or_none(row.get("p95_ms")),
                achieved_rps=_float_or_none(row.get("achieved_rps")),
                http_status_known=bool(row.get("http_status_known")),
                status_counts_reliable=bool(row.get("status_counts_reliable")),
                status_counts={str(k): int(v) for k, v in (row.get("status_counts") or {}).items()},
            )
        )
    return K6ExperimentRecord(
        experiment_id=exp_id,
        wave=wave,
        offered_rps=offered_rps,
        duration_s=duration_s,
        dropped_iterations=dropped,
        operations=ops,
    )


def _float_or_none(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def render_load_evidence_markdown(experiments: list[K6ExperimentRecord]) -> str:
    if not experiments:
        return (
            "_No k6 experiments were recorded for this run._\n\n"
            "- **Observed:** No load measurements are available in the run ledger.\n"
        )

    lines: list[str] = []
    any_unreliable = any(
        not op.status_counts_reliable for exp in experiments for op in exp.operations
    )
    if any_unreliable:
        lines.append(
            "> **Measurement note:** HTTP status codes were not reliably tagged in one or more "
            "experiments. Tables below emphasize latency and throughput; do not treat missing "
            "`status_counts` as proof of application HTTP errors.\n"
        )

    op_ids = _sorted_op_ids(experiments)
    header = (
        "| Experiment | Offered (req/s) | Duration (s) | Dropped |"
        + "".join(f" {oid} p95 (ms) |" for oid in op_ids)
        + " Notes |"
    )
    sep = "|---|---:|---:|---:|" + "---:|" * len(op_ids) + "---|"
    lines.extend([header, sep])
    for exp in experiments:
        notes: list[str] = []
        if exp.dropped_iterations:
            notes.append(f"dropped={exp.dropped_iterations}")
        p95_by_op = {op.op_id: op.p95_ms for op in exp.operations}
        for op in exp.operations:
            if not op.status_counts_reliable and op.count:
                notes.append(f"{op.op_id}: no HTTP status breakdown")
        row = (
            f"| `{exp.experiment_id}` | {exp.offered_rps:g} | {exp.duration_s} | {exp.dropped_iterations} |"
            + "".join(
                f" {_fmt_ms(p95_by_op.get(oid))} |" for oid in op_ids
            )
            + f" {'; '.join(notes) or '—'} |"
        )
        lines.append(row)

    lines.append("")
    lines.append("### Observations")
    lines.extend(_observation_bullets(experiments, op_ids))
    return "\n".join(lines) + "\n"


def _sorted_op_ids(experiments: list[K6ExperimentRecord]) -> list[str]:
    seen: dict[str, None] = {}
    for exp in experiments:
        for op in exp.operations:
            seen[op.op_id] = None
    return list(seen.keys())


def _fmt_ms(val: float | None) -> str:
    if val is None:
        return "—"
    return str(int(round(val)))


def _observation_bullets(experiments: list[K6ExperimentRecord], op_ids: list[str]) -> list[str]:
    bullets: list[str] = []
    if len(experiments) >= 2 and len(op_ids) >= 2:
        primary = op_ids[0]
        control = op_ids[1]
        primary_p95 = [_op_p95(exp, primary) for exp in experiments]
        control_p95 = [_op_p95(exp, control) for exp in experiments]
        if _all_known(primary_p95) and _all_known(control_p95):
            if max(primary_p95) > min(primary_p95) * 1.5 and max(control_p95) <= min(control_p95) * 1.25:
                bullets.append(
                    f"- **Observed:** `{primary}` p95 rose across separate experiments "
                    f"({min(primary_p95):.0f}–{max(primary_p95):.0f} ms offered load steps) "
                    f"while `{control}` stayed near {min(control_p95):.0f}–{max(control_p95):.0f} ms."
                )
    if len(experiments) >= 2 and len(op_ids) == 1:
        oid = op_ids[0]
        series = [_op_p95(exp, oid) for exp in experiments]
        if _all_known(series) and max(series) > min(series) * 1.5:
            bullets.append(
                f"- **Observed:** `{oid}` p95 increased from {min(series):.0f} ms to {max(series):.0f} ms "
                f"as offered rate went from {experiments[0].offered_rps:g} to {experiments[-1].offered_rps:g} req/s "
                f"(independent experiments, not a continuous ramp)."
            )
    if not bullets:
        bullets.append(
            "- **Observed:** See the table above for per-experiment offered rate and p95 latency "
            "(each row is one run_k6 call)."
        )
    return bullets[:3]


def _op_p95(exp: K6ExperimentRecord, op_id: str) -> float | None:
    for op in exp.operations:
        if op.op_id == op_id:
            return op.p95_ms
    return None


def _all_known(values: list[float | None]) -> bool:
    return bool(values) and all(v is not None for v in values)


def render_appendix_markdown(
    experiments: list[K6ExperimentRecord],
    read_ranges: list[ReadRange],
    *,
    limitations: list[str],
) -> str:
    lines = ["### Experiments", ""]
    if not experiments:
        lines.append("- No k6 experiments recorded.")
    else:
        for exp in experiments:
            ops_desc = ", ".join(
                f"{op.method} {op.path or op.op_id}".strip() for op in exp.operations
            ) or "—"
            lines.append(
                f"- `{exp.experiment_id}` — offered {exp.offered_rps:g} req/s for {exp.duration_s}s "
                f"({ops_desc})"
            )
    lines.extend(["", "### Source reads", ""])
    if read_ranges:
        for i, rr in enumerate(read_ranges, 1):
            lines.append(f"- ev-read-{i}: `{rr.path}` L{rr.start_line}–L{rr.end_line}")
    else:
        lines.append("- None recorded via read_file.")
    if limitations:
        lines.extend(["", "### Limitations", ""])
        for item in limitations:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _replace_section(body: str, heading: str, new_content: str) -> str:
    pattern = re.compile(
        rf"^{re.escape(heading)}\s*\n(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    if pattern.search(body):
        return pattern.sub(f"{heading}\n\n{new_content}\n", body, count=1)
    return body.rstrip() + f"\n\n{heading}\n\n{new_content}\n"


def compose_investigation_report(
    agent_md: str,
    *,
    run_dir: Path,
    run_id: str,
    read_ranges: list[ReadRange],
) -> tuple[str, dict[str, Any]]:
    experiments = load_k6_experiments(run_dir, run_id)
    load_md = render_load_evidence_markdown(experiments)
    limitations: list[str] = []
    if read_ranges and not _FENCE_RE.search(agent_md):
        limitations.append(
            "No fenced code excerpt appears in the agent report despite read_file ranges recorded this run."
        )
    appendix_md = render_appendix_markdown(experiments, read_ranges, limitations=limitations)
    out = _replace_section(agent_md, _SECTION_LOAD, load_md.strip())
    out = _replace_section(out, _SECTION_APPENDIX, appendix_md.strip())
    meta = {
        "source": "investigator_agent",
        "experiments": [
            {
                "experiment_id": e.experiment_id,
                "offered_rps": e.offered_rps,
                "duration_s": e.duration_s,
                "operations": [op.op_id for op in e.operations],
            }
            for e in experiments
        ],
        "read_ranges": [
            {"path": r.path, "start_line": r.start_line, "end_line": r.end_line} for r in read_ranges
        ],
    }
    return out, meta


def render_load_charts_svg(_experiments: list[K6ExperimentRecord], _run_dir: Path) -> None:
    """Reserved for a follow-up: write SVG charts under run_dir/report/charts/."""
