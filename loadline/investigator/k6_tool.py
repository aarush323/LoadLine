"""run_k6 investigator tool — execute plan and return agent-facing metrics."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loadline.adapters.generator.k6_compiler import CompileError, compile_plan
from loadline.adapters.generator.k6_runner import run_k6_plan
from loadline.investigator.deps import InvestigationDeps

_PATH_TEMPLATE = re.compile(r"\{[^}]+\}")
_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_MAX_DURATION_S = 120
_DOCKER_TIMEOUT_GRACE_S = 90


def _app_target(boot: dict[str, Any]) -> tuple[str, int]:
    health = boot.get("health") or {}
    url = health.get("url") or ""
    if url:
        parsed = urlparse(url)
        host = parsed.hostname or "app"
        port = parsed.port or 8000
        return host, port
    services = boot.get("services") or []
    if services:
        name = services[0].get("name") or "app"
        port = int(services[0].get("port") or 8000)
        return name, port
    return "app", 8000


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
    service, port = _app_target(boot)
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
        count = int(row.get("count") or row.get("http_reqs") or 0)
        w = weights[idx] if idx < len(weights) else 1
        offered_op = offered_rps * (w / total_w)
        achieved = float(row.get("achieved_rps") or (count / duration_s if duration_s else 0))
        operations_out[str(op_id)] = {
            "count": count,
            "error_count": int(row.get("error_count") or 0),
            "error_rate": float(row.get("error_rate") or row.get("http_req_failed") or 0),
            "p50_ms": row.get("p50_ms"),
            "p95_ms": row.get("p95_ms"),
            "offered_rps": round(offered_op, 4),
            "achieved_rps": achieved,
            "status_counts": {str(k): int(v) for k, v in (row.get("status_counts") or {}).items()},
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
    if profile != "default_user":
        return None, f"unknown auth profile: {profile}"
    sealed = deps.auth_profiles.get("default_user") or {}
    username = sealed.get("username") or ""
    password = sealed.get("password") or ""
    if not username or not password:
        return None, "default_user credentials are not in the boot env"
    return {"username": username, "password": password}, None


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
    if duration_s > _MAX_DURATION_S:
        duration_s = _MAX_DURATION_S
    for ep in endpoints:
        err = validate_endpoint(ep)
        if err:
            return {"error": err}
    auth_secrets, auth_err = _resolve_auth_secrets(deps, auth)
    if auth_err:
        return {"error": auth_err}
    allowed = deps.allowed_hosts
    network = deps.network
    if not allowed or not network:
        return {"error": "sandbox network not configured"}
    plan = build_plan_from_endpoints(
        endpoints, rate=rate, duration_s=duration_s, boot=deps.boot, auth=auth
    )
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
    result = run_k6_plan(
        plan=persist_plan,
        allowed_hosts=allowed,
        network=network,
        run_id=deps.run_id,
        run_dir=deps.run_dir,
        wave_name=wave,
        timeout_s=docker_timeout,
        auth_secrets=auth_secrets,
    )
    if not result.summary.parse_ok:
        excerpt = (result.stderr or result.summary.error or "k6 failed")[:2000]
        return {"error": excerpt, "experiment_id": experiment_id}
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
    out["artifacts"] = artifacts
    deps.ledger.append(
        "k6_run",
        evidence_ids=[experiment_id],
        experiment_id=experiment_id,
        wave=wave,
        plan=persist_plan,
        result=out,
    )
    return out
