"""Compile WorkloadPlan to generic k6 script (stdin). No user strings in executable positions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from loadline.core.target_guard import assert_sandbox_target


@dataclass(frozen=True)
class CompileError:
    message: str


def _validate_url(url: str, allowed_hosts: frozenset[str]) -> CompileError | None:
    return assert_sandbox_target(url, allowed_hosts)


def _threshold_lines(ops: list[dict[str, Any]]) -> str:
    entries: list[str] = []
    for op in ops:
        oid = op["id"]
        entries.append(f'    "http_req_duration{{operation:{oid}}}": ["max>=0"],')
        entries.append(f'    "http_reqs{{operation:{oid}}}": ["count>=0"],')
    if not entries:
        return ""
    return "  thresholds: {\n" + "\n".join(entries) + "\n  },\n"


def _auth_setup_block(auth: dict[str, Any], allowed_hosts: frozenset[str]) -> tuple[str, str] | CompileError:
    method = str(auth.get("method") or "POST").upper()
    path = str(auth.get("path") or "")
    service = auth.get("service", "app")
    port = int(auth.get("port", 8000))
    url = f"http://{service}:{port}{path}"
    err = _validate_url(url, allowed_hosts)
    if err:
        return CompileError(err.message)
    encoding = str(auth.get("body_encoding") or "form")
    token_field = str(auth.get("token_field") or "access_token")
    username = auth.get("username")
    password = auth.get("password")
    if not username or not password:
        return CompileError("auth credentials missing for setup()")
    if encoding == "form":
        body_expr = (
            f"{{ username: {json.dumps(username)}, password: {json.dumps(password)} }}"
        )
        headers_expr = '{ "Content-Type": "application/x-www-form-urlencoded" }'
        request_body = f"Object.entries({body_expr}).map(([k,v]) => encodeURIComponent(k)+'='+encodeURIComponent(v)).join('&')"
    else:
        request_body = json.dumps({"username": username, "password": password})
        headers_expr = '{ "Content-Type": "application/json" }'
    setup = f"""
export function setup() {{
  const loginUrl = {json.dumps(url)};
  const loginRes = http.request({json.dumps(method)}, loginUrl, {request_body}, {{ headers: {headers_expr} }});
  if (loginRes.status < 200 || loginRes.status >= 300) {{
    throw new Error('login failed: ' + loginRes.status);
  }}
  const body = loginRes.json();
  const token = body[{json.dumps(token_field)}];
  if (!token) {{
    throw new Error('login response missing token field');
  }}
  return {{ token }};
}}
"""
    return setup, ""


def compile_plan(
    plan: dict[str, Any],
    allowed_hosts: frozenset[str],
    *,
    auth_secrets: dict[str, str] | None = None,
) -> tuple[str, str] | CompileError:
    """Return (script, plan_hash). auth_secrets supplies username/password for plan auth block only."""
    mix = plan.get("mix") or []
    if not mix:
        return CompileError("empty workload mix")
    ops: list[dict[str, Any]] = []
    for item in mix:
        op = item.get("op") or {}
        method = (op.get("selector") or {}).get("method", "GET").upper()
        path = (op.get("selector") or {}).get("path", "/")
        service = op.get("service", "app")
        port = op.get("port", 8000)
        url = f"http://{service}:{port}{path}"
        err = _validate_url(url, allowed_hosts)
        if err:
            return CompileError(err.message)
        body = op.get("body")
        headers = op.get("headers") or {}
        ops.append(
            {
                "id": op.get("id", "op"),
                "method": method,
                "url": url,
                "weight": item.get("weight", 1),
                "body": json.dumps(body) if body is not None else None,
                "headers": headers,
                "useAuth": bool(op.get("use_auth")),
            }
        )
    shape = plan.get("shape") or {}
    rate = int(shape.get("rate", 2))
    duration = int(shape.get("duration", 15))
    max_vus = max(50, rate * 2)
    pre_vus = min(max_vus, max(50, rate))
    threshold_block = _threshold_lines(ops)

    auth_meta = plan.get("auth")
    setup_block = ""
    default_fn_params = ""
    if auth_meta and isinstance(auth_meta, dict):
        auth_full = dict(auth_meta)
        if auth_secrets:
            auth_full["username"] = auth_secrets.get("username") or auth_full.get("username")
            auth_full["password"] = auth_secrets.get("password") or auth_full.get("password")
        setup_result = _auth_setup_block(auth_full, allowed_hosts)
        if isinstance(setup_result, CompileError):
            return setup_result
        setup_block = setup_result[0]
        default_fn_params = "data"

    script = f"""import http from 'k6/http';

export const options = {{
{threshold_block}  scenarios: {{
    main: {{
      executor: 'constant-arrival-rate',
      rate: {rate},
      timeUnit: '1s',
      duration: '{duration}s',
      preAllocatedVUs: {pre_vus},
      maxVUs: {max_vus},
    }},
  }},
}};

const OPS = {json.dumps(ops)};
const VU_CEILING = {max_vus};
const DURATION_S = {duration};
{setup_block}
export default function ({default_fn_params}) {{
  const total = OPS.reduce((a, o) => a + o.weight, 0);
  let pick = Math.random() * total;
  let chosen = OPS[0];
  for (const op of OPS) {{
    pick -= op.weight;
    if (pick <= 0) {{ chosen = op; break; }}
  }}
  const hdrs = {{ ...(chosen.headers || {{}}) }};
  if (chosen.useAuth && data && data.token) {{
    hdrs['Authorization'] = 'Bearer ' + data.token;
  }}
  const params = {{ headers: hdrs, tags: {{ operation: chosen.id }} }};
  const body = chosen.body != null ? chosen.body : null;
  http.request(chosen.method, chosen.url, body, params);
}}

function _parseHttpReqTags(metricName) {{
  const m = metricName.match(/^http_reqs\\{{(.+)\\}}$/);
  if (!m) return null;
  const tags = {{}};
  for (const part of m[1].split(',')) {{
    const idx = part.indexOf(':');
    if (idx < 0) continue;
    tags[part.slice(0, idx).trim()] = part.slice(idx + 1).trim();
  }}
  return tags;
}}

function _buildOperationsFromMetrics(metrics) {{
  const ops = {{}};
  for (const [name, block] of Object.entries(metrics || {{}})) {{
    const tags = _parseHttpReqTags(name);
    if (!tags || !tags.operation) continue;
    const op = tags.operation;
    if (!ops[op]) ops[op] = {{ count: 0, status_counts: {{}}, error_count: 0 }};
    const c = (block.values && block.values.count) || 0;
    if (tags.status) {{
      ops[op].status_counts[tags.status] = (ops[op].status_counts[tags.status] || 0) + c;
      ops[op].count += c;
      if (!String(tags.status).startsWith('2')) ops[op].error_count += c;
    }}
  }}
  for (const [name, block] of Object.entries(metrics || {{}})) {{
    const m = name.match(/^http_req_duration\\{{operation:([^,}}]+)/);
    if (!m) continue;
    const op = m[1];
    if (!ops[op]) ops[op] = {{ count: 0, status_counts: {{}}, error_count: 0 }};
    const v = block.values || {{}};
    if (v.med != null) ops[op].p50_ms = v.med;
    if (v['p(95)'] != null) ops[op].p95_ms = v['p(95)'];
  }}
  return ops;
}}

export function handleSummary(data) {{
  const dropped = data.metrics.dropped_iterations?.values?.count || 0;
  const vusMax = data.metrics.vus?.values?.max || 0;
  const payload = {{
    vu_ceiling: VU_CEILING,
    duration_s: DURATION_S,
    vus_max: vusMax,
    vus_max_reached: vusMax >= VU_CEILING,
    dropped_iterations: dropped,
    metrics: data.metrics,
    state: data.state,
    operations: _buildOperationsFromMetrics(data.metrics),
  }};
  return {{ stdout: JSON.stringify(payload) }};
}}
"""
    digest = hashlib.sha256(script.encode()).hexdigest()
    return script, digest
