"""Compare a cited measurement with a replay. Numbers come from experiment files."""

from __future__ import annotations

import re
from typing import Any

_DIFF_PATH = re.compile(r"^(?:diff --git a/(\S+)|--- a/(\S+)|\+\+\+ b/(\S+))", re.M)

_FORBIDDEN_NAMES = frozenset(
    {
        "dockerfile",
        "dockerfile.dev",
        ".env",
        ".loadline.yaml",
    }
)


def metrics_from_experiment(experiment: dict[str, Any], operation_id: str) -> dict[str, Any]:
    """Copy measured numbers. A digit in model prose is not a measurement."""
    ops = (experiment.get("output") or {}).get("operations") or {}
    row = ops.get(operation_id) if isinstance(ops, dict) else None
    if not isinstance(row, dict):
        row = {}
    return {
        "p95_ms": row.get("p95_ms"),
        "error_rate": row.get("error_rate"),
        "achieved_rps": row.get("achieved_rps"),
    }


def p95_improved(before: float, after: float) -> bool:
    return after <= before * 0.75 and after <= before - 20


def error_rate_improved(before: float, after: float) -> bool:
    return after <= before - 0.05


def achieved_rps_improved(before: dict[str, Any], after: dict[str, Any]) -> bool:
    b = before.get("achieved_rps")
    a = after.get("achieved_rps")
    bp = before.get("p95_ms")
    ap = after.get("p95_ms")
    if b is None or a is None or bp is None or ap is None:
        return False
    if float(a) < float(b) * 1.25:
        return False
    return float(ap) <= float(bp) * 1.10


def _cited_moved(metric: str, before: dict[str, Any], after: dict[str, Any]) -> bool:
    if metric == "p95_ms":
        b, a = before.get("p95_ms"), after.get("p95_ms")
        if b is None or a is None:
            return False
        return p95_improved(float(b), float(a))
    if metric == "error_rate":
        b, a = before.get("error_rate"), after.get("error_rate")
        if b is None or a is None:
            return False
        return error_rate_improved(float(b), float(a))
    if metric == "achieved_rps":
        return achieved_rps_improved(before, after)
    return False


def control_regressed(before: dict[str, Any] | None, after: dict[str, Any] | None) -> bool:
    if not before or not after:
        return False
    bp, ap = before.get("p95_ms"), after.get("p95_ms")
    if bp is not None and ap is not None and float(ap) > float(bp) * 1.20:
        return True
    be = float(before.get("error_rate") or 0)
    ae = float(after.get("error_rate") or 0)
    return ae > be + 0.02


def judge_replay(
    *,
    metric: str,
    cited_before: dict[str, Any],
    cited_after: dict[str, Any],
    control_before: dict[str, Any] | None,
    control_after: dict[str, Any] | None,
) -> str:
    """Verdict for one cited metric. Another route getting faster does not count."""
    if not _cited_moved(metric, cited_before, cited_after):
        return "hypothesis_failed"
    if control_before is None or control_after is None:
        return "hypothesis_failed"
    if control_regressed(control_before, control_after):
        return "regressed_control"
    return "improved"


def range_covered(path: str, start_line: int, end_line: int, reads: list[dict[str, Any]]) -> bool:
    for rec in reads:
        if rec.get("path") != path:
            continue
        try:
            lo = int(rec["start_line"])
            hi = int(rec["end_line"])
        except (KeyError, TypeError, ValueError):
            continue
        if lo <= start_line and hi >= end_line:
            return True
    return False


def path_rejected(path: str) -> str | None:
    name = path.replace("\\", "/").split("/")[-1]
    lowered = name.lower()
    if lowered in _FORBIDDEN_NAMES or lowered.startswith(".env"):
        return "path is not application source"
    if lowered.startswith("dockerfile"):
        return "path is not application source"
    if lowered.startswith("compose") or lowered.startswith("docker-compose"):
        return "path is not application source"
    if lowered.endswith(".lock"):
        return "path is not application source"
    norm = path.replace("\\", "/")
    parts = [part for part in norm.split("/") if part]
    if "loadline" in parts and parts[0] == "loadline":
        return "path is not application source"
    if "tests" in parts and "oracles" in parts:
        return "path is not application source"
    return None


def changed_line_count(diff_text: str) -> int:
    count = 0
    for line in (diff_text or "").splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith(("+", "-")):
            count += 1
    return count


def changed_paths(diff_text: str) -> list[str]:
    found: list[str] = []
    for match in _DIFF_PATH.finditer(diff_text or ""):
        path = next(group for group in match.groups() if group)
        if path.startswith("b/") or path.startswith("a/"):
            path = path[2:]
        if path not in found:
            found.append(path)
    return found


def patch_rejection(diff_text: str, contract_path: str) -> str | None:
    """Refuse a diff that is not exactly the contract source file."""
    if changed_line_count(diff_text) > 80:
        return "diff changes more than 80 lines"
    paths = changed_paths(diff_text)
    if not paths:
        return "diff has no files"
    for path in paths:
        if path_rejected(path):
            return path_rejected(path)
        if path != contract_path:
            return f"diff touches {path}"
    return None
