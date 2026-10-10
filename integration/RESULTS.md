# Integration results log

Append-only record of reference-target and held-out runs (`implementation.md` §15).

---

## 2026-10-10 — S8 reference: full-stack-fastapi-template (pinned)

| Field | Value |
| --- | --- |
| Loadline tree | `/home/aarush_linux/projects/neathacks` (working tree; local `main` may have no commits — use file timestamps for reproducibility) |
| Target SHA | `7257e606cb94eada1dca40173e2b7f99dd549bc6` (`integration/targets.lock.json`) |
| `LOADLINE_HOME` | `/tmp/loadline-s8-ref-*` (ephemeral) |
| Paid model | **none** (boot blocked before run/investigator) |

### Commands

```bash
cd /home/aarush_linux/projects/neathacks
export LOADLINE_HOME=/tmp/loadline-s8-ref-<pid>
# OPENROUTER_API_KEY + LOADLINE_MODEL loaded from .env for auth preflight only
uv run loadline analyze integration/targets/full-stack-fastapi-template --json
uv run loadline analyze integration/targets/full-stack-fastapi-template --boot --json
uv run loadline doctor --cleanup
```

### Stage results

| Stage | Result | Notes |
| --- | --- | --- |
| 1. Discovery (`analyze --json`) | **pass** | `profile.json` fields emitted: languages `python`, `typescript`; `compose_files`: `compose.yml`; `dockerfiles`: `backend/Dockerfile`; VCS SHA matches pin; dirty=false. `capabilities.runtime.level`: `ready` (compose adapter). Workload OpenAPI **degraded** (no on-disk OpenAPI until app serves `/openapi.json`). |
| 2. Boot (`analyze --boot --json`) | **blocked** | `status`: `blocked`. `blocker.code`: `policy_refused`. `blocker.summary`: `service proxy has a host bind mount` (`/var/run/docker.sock` on Traefik `proxy` in upstream `compose.yml`). `retryable`: false, `security`: true. `launch_plan`: null, `boot`: null. Exit code **10**. Policy not weakened. |
| 3. Smoke / baseline | **skip** | No boot. |
| 4. Investigator / `loadline run` | **skip** | No model call per S8 budget rules. |
| 5. Teardown | **pass** | `loadline doctor --cleanup` removed 4 labelled objects (leftover from prior runs). |

### Diagnosis

The pinned template’s documented stack requires Traefik with a Docker socket bind. Loadline `SandboxPolicy` correctly refuses that mount (`loadline/core/sandbox_policy.py` rule 3). This is an honest **named blocker**, not a fabricated success. A full-stack load investigation on this pin would need a different upstream layout or a future hint-driven compose variant **outside** the pinned checkout (out of scope for S8 — clone not patched).

### Artifacts

- Discovery/capabilities JSON: captured in command stdout (no run directory created).
- Boot JSON: same (blocked before `run_dir` allocation).
- Report: **not produced**.

### Deterministic S8 unit gate (same session)

```bash
uv run pytest tests/unit -q --tb=line
# 62 passed
```

Sealed oracles under `tests/oracles/*.sealed.yaml`; hidden-cause and git-history checks in `tests/unit/test_s8_*.py`.

---

## 2026-10-10 — Product `loadline run` (pinned FastAPI template)

| Field | Value |
| --- | --- |
| Command | `uv run loadline run --repo integration/targets/full-stack-fastapi-template --fast` |
| `LOADLINE_MODEL` | `openrouter:deepseek/deepseek-v4.1-flash` (shell default when unset in `.env`) |
| Target SHA | `7257e606cb94eada1dca40173e2b7f99dd549bc6` |
| Exit code | **10** |
| Report | **not written** (boot blocked before `run_dir`) |
| Investigator / OpenRouter | **not invoked** (boot never healthy) |
| Teardown | `uv run loadline doctor --cleanup` (removed 2 labelled objects) |

### CLI output (stderr JSON)

```json
{
  "status": "blocked",
  "blocker": {
    "code": "policy_refused",
    "summary": "service proxy has a host bind mount",
    "retryable": false,
    "security": true,
    "user_can_provide": [],
    "remediation": []
  }
}
```

### Diagnosis

Same honest blocker as S8 `analyze --boot --json`: Traefik `proxy` requires `/var/run/docker.sock`. `SandboxPolicy` was not weakened; the clone was not modified. `--fast` would use baseline warmup **5s** / measure **15s** (`FAST_WARMUP_S` / `FAST_MEASURE_S`) once boot succeeds.

---

## 2026-10-10 — Product `loadline run` (fixture `fx-pyhttp-pg`)

| Field | Value |
| --- | --- |
| Command | `uv run loadline run --repo tests/fixtures/fx-pyhttp-pg --fast` |
| `LOADLINE_MODEL` | `openrouter:deepseek/deepseek-v4.1-flash` |
| Exit code | **0** |
| Status | `investigation_incomplete` — `UsageLimitExceeded` at `total_tokens_limit=80000` (`total_tokens=90018`) |
| Report | `/tmp/loadline-s8-ref-125335/runs/bbad1e518c65/report.md` |
| `run_dir` | `/tmp/loadline-s8-ref-125335/runs/bbad1e518c65` |
| Teardown | `uv run loadline doctor --cleanup` |

Boot, calibration, baseline, and post-baseline ladder completed before the investigator stopped on the token budget (tool `request_limit` 60 was not the limiting factor). No retry per integration policy.
