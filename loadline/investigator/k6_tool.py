"""run_k6 investigator tool — execute plan and return agent-facing metrics."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loadline.adapters.generator.k6_compiler import CompileError, compile_plan
from loadline.adapters.generator.k6_operation_metrics import sanitize_operation_metrics
from loadline.adapters.generator.k6_runner import run_k6_plan
from loadline.core.hints import slo_from_hints
from loadline.investigator.deps import InvestigationDeps
from loadline.investigator.limits import investigator_k6_limits

_PATH_TEMPLATE = re.compile(r"\{[^}]+\}")
_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_MAX_DURATION_S = 120
_DOCKER_TIMEOUT_GRACE_S = 90


def _app_target(boot: dict[str, Any]) -> tuple[str, int] | None:
    health = boot.get("health") or {}
    url = (health.get("url") or "").strip()
    if not url:
        return None
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return None
    port = parsed.port or 8000
    return host, port


def _slug(path: str, method: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", path.strip("/")) or "root"
    return f"{method.lower()}_{clean}"[:64]


def validate_endpoint(ep: dict[str, Any]) -> str | None:
    path = str(ep.get("path") or "").strip()
    if not path:
        return "each endpoint needs a concrete path"
    if _PATH_TEMPLATE.search(path):
        return f"path must be concrete (no route templates): {path}"
    method = str(ep.get("method") or "GET").upper()
    if method not in _ALLOWED_METHODS:
        return f"unsupported method: {method}"
    headers = ep.get("headers")
    if headers is not None:
        if not isinstance(headers, dict):
            return "headers must be an object of string keys and values"
        for k, v in headers.items():
            if not isinstance(k, str) or not isinstance(v, str):
                return "headers must be string key/value pairs"
    body = ep.get("body")
    if body is not None:
        try:
            json.dumps(body)
        except (TypeError, ValueError):
            return "body must be JSON-serializable"
    weight = ep.get("weight")
    if weight is not None:
        try:
            w = int(weight)
        except (TypeError, ValueError):
            return "weight must be a positive integer"
        if w < 1:
            return "weight must be a positive integer"
    return None


def _sanitize_plan_for_persist(plan: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(plan))
    auth = out.get("auth")
    if isinstance(auth, dict):
        auth.pop("username", None)
        auth.pop("password", None)
        if auth.get("profile"):
            out["auth"] = {"profile": auth["profile"]}
    return out


def build_plan_from_endpoints(
    endpoints: list[dict[str, Any]],
    *,
    rate: float,
    duration_s: int,
    boot: dict[str, Any],
    auth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target = _app_target(boot)
    if target is None:
        raise ValueError("origin_unknown: boot health URL is missing")
    service, port = target
    mix: list[dict[str, Any]] = []
    weights = [max(1, int(ep.get("weight") or 1)) for ep in endpoints]
    for ep, weight in zip(endpoints, weights):
        path = str(ep.get("path") or "/")
        if not path.startswith("/"):
            path = f"/{path}"
        op_id = str(ep.get("id") or _slug(path, str(ep.get("method") or "GET")))
        op: dict[str, Any] = {
            "id": op_id,
            "service": service,
            "port": port,
            "selector": {"method": str(ep.get("method") or "GET").upper(), "path": path},
        }
        if ep.get("body") is not None:
            op["body"] = ep["body"]
        if ep.get("headers"):
            op["headers"] = ep["headers"]
        if ep.get("use_auth"):
            op["use_auth"] = True
        mix.append({"weight": weight, "op": op})
    plan: dict[str, Any] = {"mix": mix, "shape": {"rate": int(rate), "duration": int(duration_s)}}
    if auth:
        plan["auth"] = {
            "profile": auth.get("profile", "default_user"),
            "method": auth.get("method", "POST"),
            "path": auth.get("path"),
            "body_encoding": auth.get("body_encoding", "form"),
            "token_field": auth.get("token_field", "access_token"),
            "service": service,
            "port": port,
        }
    return plan


def _aggregate_metrics_note(metrics: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(metrics, dict):
        return None
    reqs = (metrics.get("http_reqs") or {}).get("values") or {}
    dur = (metrics.get("http_req_duration") or {}).get("values") or {}
    count = int(reqs.get("count") or 0)
    if count <= 0:
        return None
    note: dict[str, Any] = {"http_reqs_count": count}
    if reqs.get("rate") is not None:
        note["http_reqs_rate"] = float(reqs["rate"])
    if dur.get("p(95)") is not None:
        note["aggregate_p95_ms"] = float(dur["p(95)"])
    if dur.get("med") is not None:
        note["aggregate_p50_ms"] = float(dur["med"])
    return note


def _status_counts_imply_http(status_counts: dict[str, int]) -> bool:
    if not status_counts:
        return False
    return all(re.fullmatch(r"\d{3}", str(k)) for k in status_counts)


def format_run_k6_result(
    summary_raw: dict[str, Any],
    *,
    offered_rps: float,
    duration_s: int,
    endpoint_ids: list[str],
    weights: list[int],
) -> dict[str, Any]:
    vu_ceiling = int(summary_raw.get("vu_ceiling") or 50)
    vus_max = summary_raw.get("vus_max")
    vus_max_reached = bool(summary_raw.get("vus_max_reached"))
    dropped = int(summary_raw.get("dropped_iterations") or 0)
    total_w = float(sum(weights) or 1)
    operations_out: dict[str, Any] = {}
    raw_ops = summary_raw.get("operations") or {}
    metrics = summary_raw.get("metrics") or {}
    for idx, op_id in enumerate(endpoint_ids):
        row = raw_ops.get(op_id) if isinstance(raw_ops, dict) else None
        if not isinstance(row, dict):
            row = {}
        row = sanitize_operation_metrics(row)
        count = int(row.get("count") or row.get("http_reqs") or 0)
        w = weights[idx] if idx < len(weights) else 1
        offered_op = offered_rps * (w / total_w)
        achieved = float(row.get("achieved_rps") or (count / duration_s if duration_s else 0))
        status_counts = {str(k): int(v) for k, v in (row.get("status_counts") or {}).items()}
        http_status_known = bool(row.get("http_status_known")) or _status_counts_imply_http(status_counts)
        status_counts_reliable = bool(row.get("status_counts_reliable")) or http_status_known
        notes: list[str] = []
        if not status_counts_reliable:
            notes.append(
                "HTTP status codes were not tagged in k6 summary; do not treat status_counts as application errors."
            )
        operations_out[str(op_id)] = {
            "count": count,
            "error_count": int(row.get("error_count") or 0),
            "error_rate": float(row.get("error_rate") or row.get("http_req_failed") or 0),
            "p50_ms": row.get("p50_ms"),
            "p95_ms": row.get("p95_ms"),
            "offered_rps": round(offered_op, 4),
            "achieved_rps": achieved,
            "status_counts": status_counts,
            "http_status_known": http_status_known,
            "status_counts_reliable": status_counts_reliable,
            "measurement_notes": notes,
        }
    out: dict[str, Any] = {
        "offered_rps": float(offered_rps),
        "duration_s": int(duration_s),
        "dropped_iterations": dropped,
        "vus_max": vus_max,
        "vu_ceiling": vu_ceiling,
        "vus_max_reached": vus_max_reached,
        "operations": operations_out,
    }
    all_zero = all(int(v.get("count") or 0) == 0 for v in operations_out.values())
    if all_zero and endpoint_ids:
        agg = _aggregate_metrics_note(metrics if isinstance(metrics, dict) else {})
        if agg:
            out["metrics_note"] = (
                "per-operation tags missing in k6 summary; aggregate traffic was recorded — "
                "see metrics_note for totals"
            )
            out["aggregate"] = agg
    return out


def _persist_experiment(
    deps: InvestigationDeps,
    *,
    experiment_id: str,
    wave: str,
    tool_input: dict[str, Any],
    tool_output: dict[str, Any],
) -> dict[str, str]:
    wave_dir = deps.run_dir / "waves" / wave
    summary_path = wave_dir / "k6.summary.json"
    stdout_path = wave_dir / "k6.stdout"
    artifacts = {
        "k6_summary": str(summary_path) if summary_path.is_file() else "",
        "k6_stdout": str(stdout_path) if stdout_path.is_file() else "",
    }
    record = {
        "experiment_id": experiment_id,
        "wave": wave,
        "input": tool_input,
        "output": tool_output,
        "artifacts": artifacts,
    }
    exp_dir = deps.run_dir / "experiments"
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / f"{experiment_id}.json").write_text(json.dumps(record, indent=2))
    (wave_dir / "experiment.json").write_text(json.dumps(record, indent=2))
    return artifacts


def _resolve_auth_secrets(deps: InvestigationDeps, auth: dict[str, Any] | None) -> tuple[dict[str, str] | None, str | None]:
    if not auth:
        return None, None
    profile = str(auth.get("profile") or "default_user")
    # New map first: if requested profile present, use it.
    present = deps.auth_profiles.get(profile) or {}
    username = present.get("username") or ""
    password = present.get("password") or ""
    if username and password:
        return {"username": username, "password": password}, None
    # Fallback for default_user keeps current template runs working.
    if profile == "default_user":
        sealed = deps.auth_profiles.get("default_user") or {}
        username = sealed.get("username") or ""
        password = sealed.get("password") or ""
        if username and password:
            return {"username": username, "password": password}, None
        return None, "default_user credentials are not in the boot env"
    return None, f"unknown auth profile: {profile}"


def run_k6(
    deps: InvestigationDeps,
    endpoints: list[dict[str, Any]],
    rate: float,
    duration_s: int,
    auth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not endpoints:
        return {"error": "endpoints must not be empty"}
    if rate <= 0 or duration_s <= 0:
        return {"error": "rate and duration_s must be positive"}

    limits = investigator_k6_limits(deps.fast)
    if deps.k6_wave_index >= limits.max_waves:
        return {
            "error": (
                f"run_k6 experiment limit reached ({limits.max_waves} calls). "
                "Write the report from experiments already recorded in this run."
            ),
            "experiment_limit_reached": True,
            "max_waves": limits.max_waves,
        }
    if rate > limits.max_offered_rps:
        return {
            "error": (
                f"offered rate {rate} exceeds investigator limit {limits.max_offered_rps} rps. "
                "Use a lower rate or finish the report from prior run_k6 results."
            ),
            "max_offered_rps": limits.max_offered_rps,
        }

    duration_requested = int(duration_s)
    if duration_s > _MAX_DURATION_S:
        duration_s = _MAX_DURATION_S
    if duration_s > limits.max_duration_s:
        duration_s = limits.max_duration_s
    for ep in endpoints:
        err = validate_endpoint(ep)
        if err:
            return {"error": err}
    auth_secrets, auth_err = _resolve_auth_secrets(deps, auth)
    if auth_err:
        if auth is not None:
            return {"error": auth_err, "code": "auth_failed"}
        return {"error": auth_err}
    allowed = deps.allowed_hosts
    network = deps.network
    if not allowed or not network:
        return {"error": "sandbox network not configured"}
    if _app_target(deps.boot) is None:
        return {"error": "origin_unknown: boot health URL is missing", "code": "origin_unknown"}
    try:
        plan = build_plan_from_endpoints(
            endpoints, rate=rate, duration_s=duration_s, boot=deps.boot, auth=auth
        )
    except ValueError as exc:
        if "origin_unknown" in str(exc):
            return {"error": str(exc), "code": "origin_unknown"}
        raise
    compiled = compile_plan(plan, allowed, auth_secrets=auth_secrets)
    if isinstance(compiled, CompileError):
        return {"error": compiled.message}
    deps.k6_wave_index += 1
    wave = f"agent-k6-{deps.k6_wave_index}"
    experiment_id = f"exp-k6-{deps.k6_wave_index:04d}"
    weights = [max(1, int(ep.get("weight") or 1)) for ep in endpoints]
    endpoint_ids = [
        str(ep.get("id") or _slug(str(ep.get("path") or "/"), str(ep.get("method") or "GET")))
        for ep in endpoints
    ]
    op_labels = ",".join(endpoint_ids[:6])
    if len(endpoint_ids) > 6:
        op_labels += f",+{len(endpoint_ids) - 6}"
    tool_input: dict[str, Any] = {
        "endpoints": endpoints,
        "rate": rate,
        "duration_s": duration_s,
    }
    if auth:
        tool_input["auth"] = {
            "profile": auth.get("profile", "default_user"),
            "method": auth.get("method"),
            "path": auth.get("path"),
            "body_encoding": auth.get("body_encoding"),
            "token_field": auth.get("token_field"),
        }
    console = deps.console
    if console is not None and hasattr(console, "investigate_event"):
        console.investigate_event(
            "k6",
            f"docker {wave} offered={rate}rps duration={duration_s}s ops={op_labels}",
        )
    docker_timeout = int(duration_s) + _DOCKER_TIMEOUT_GRACE_S
    persist_plan = _sanitize_plan_for_persist(plan)
    slo_p95_ms, slo_err_rate = slo_from_hints(deps.repo_root)
    result = run_k6_plan(
        plan=persist_plan,
        allowed_hosts=allowed,
        network=network,
        run_id=deps.run_id,
        run_dir=deps.run_dir,
        wave_name=wave,
        timeout_s=docker_timeout,
        auth_secrets=auth_secrets,
        slo_p95_ms=slo_p95_ms,
        slo_err_rate=slo_err_rate,
    )
    if not result.summary.parse_ok:
        excerpt = (result.stderr or result.summary.error or "k6 failed")[:2000]
        if auth is not None and ("login failed" in excerpt.lower() or "missing token" in excerpt.lower()):
            return {"error": f"auth_failed: {excerpt}", "code": "auth_failed", "experiment_id": experiment_id}
        return {"error": excerpt, "experiment_id": experiment_id}
    # k6 setup() login throw surfaces in stderr even when summary parses.
    _stderr_low = (result.stderr or "").lower()
    if auth is not None and ("login failed" in _stderr_low or "missing token" in _stderr_low):
        return {"error": f"auth_failed: {(result.stderr or '')[:2000]}", "code": "auth_failed", "experiment_id": experiment_id}
    raw = dict(result.summary.raw_json or {})
    raw["operations"] = result.summary.operations
    out = format_run_k6_result(
        raw,
        offered_rps=rate,
        duration_s=duration_s,
        endpoint_ids=endpoint_ids,
        weights=weights,
    )
    artifacts = _persist_experiment(
        deps,
        experiment_id=experiment_id,
        wave=wave,
        tool_input=tool_input,
        tool_output=out,
    )
    out["experiment_id"] = experiment_id
    if duration_requested != duration_s:
        out["duration_s_requested"] = duration_requested
        out["duration_clamped"] = True
    deps.ledger.append(
        "k6_run",
        evidence_ids=[experiment_id],
        experiment_id=experiment_id,
        wave=wave,
        plan=persist_plan,
        result=out,
    )
    return out
