# Desired Loadline outcome — full-stack-fastapi-template (pinned)

This document defines what a **correct** Loadline e2e against the reference target should look like, so a later run can be scored against `integration/RESULTS.md`. It is derived from `tech_doc.md`, `integration/TARGET.md`, and read-only inspection of the pinned checkout.

| Item | Value |
| --- | --- |
| Target repository | https://github.com/fastapi/full-stack-fastapi-template |
| Pinned commit | `7257e606cb94eada1dca40173e2b7f99dd549bc6` (`integration/targets.lock.json`) |
| Clone path (read-only for Loadline) | `integration/targets/full-stack-fastapi-template/` |
| Verified at authoring | `git -C integration/targets/full-stack-fastapi-template rev-parse HEAD` → `7257e606cb94eada1dca40173e2b7f99dd549bc6` |

**Constraint for scorers:** Loadline must not modify the clone, must not embed this app’s routes or handler names in `loadline/` product code, and must not treat a `policy_refused` boot as a product failure when the upstream compose legitimately requires a forbidden mount.

---

## 1. Contract: what a correct run must do

Per `tech_doc.md`, `loadline run` (or the staged e2e: `analyze`, `analyze --boot`, optional full `run`) must:

1. **Discover from the repository only** — stack, `compose.yml` (and merged override when the adapter loads it), Dockerfiles, languages, VCS SHA, and HTTP operation candidates from specs/tests/code adapters. No assumption that the app is FastAPI, PostgreSQL, or Traefik; those labels must appear as **discovered evidence**, not baked-in product knowledge (rules R1, R2).
2. **Reuse the repo’s launch artifacts** — `compose` adapter when compose files exist; honour profiles only if the repo declares them. Do not invent a substitute stack when compose is present (`no_entrypoint` / `boot_failed` only when the repo truly has no runnable path).
3. **Apply `SandboxPolicy` before boot** — refuse privileged mode, extra capabilities, host bind mounts (including `docker.sock`, `/proc`, `/sys`, `/`), host networking, published ports (rewrite to internal network), and external egress. Store original vs validated launch plan and the diff. Do not weaken policy for this target.
4. **Never target URLs outside the isolated run** — `TargetGuard` (R6); repository URLs are data, not load targets.
5. **Never patch the pin** — no commits, merges, or compose edits inside `integration/targets/full-stack-fastapi-template/`. Hints in `.loadline.yaml` (if used later) must not override sandbox policy (`tech_doc.md` §16.3).
6. **End in a named outcome** — evidence-backed `report.md` / `report.json` after a successful boot, **or** a named blocker (`policy_refused`, `boot_failed`, etc.) with evidence. “Blocked: Traefik docker socket” is a **valid, honest** finish for the default compose path on this pin.
7. **Separate measured vs hypothesis** — any number in a report traces to ledger/k6/cgroup evidence (R3). Missing data is `not measured (reason)`, not invented.

**Discovery expectations (observation, not oracle leakage):** upstream documents FastAPI + PostgreSQL + optional Mailpit; default compose includes a `proxy` (Traefik) service. Loadline should record `compose_files` including `compose.yml`, runtime capability `ready` for compose, and workload/OpenAPI support **degraded** until a live `/openapi.json` (or equivalent) is reachable inside the sandbox.

---

## 2. Default Compose boot: expect `policy_refused` (valid outcome)

Docker Compose loads `compose.yml` and, for local dev, automatically merges `compose.override.yml`. The **base** file defines Traefik `proxy` with a host bind mount to the Docker socket. Loadline rule 2 (`tech_doc.md` §7.4) refuses host bind mounts and `docker.sock`.

**Upstream service and volume (quoted from pinned `compose.yml`):**

```yaml
  proxy:
    image: traefik:v3.7
    volumes:
      # Add Docker as a mounted volume, so that Traefik can read the labels of other services
      - /var/run/docker.sock:/var/run/docker.sock:ro
```

**Expected boot JSON (or equivalent run status):**

- `status`: `blocked`
- `blocker.code`: `policy_refused`
- `blocker.summary`: references the `proxy` service and the `/var/run/docker.sock` bind mount
- `retryable`: `false` when the refusal is security/policy (as in prior S8 reference run)
- `launch_plan` / `boot`: null or absent — no smoke, baseline, k6, or Investigator on an unbooted plan

This is **not** a failed product test. It demonstrates that sandbox policy is enforced against a real-world template that assumes Traefik-with-Docker-provider.

**Note:** `compose.override.yml` adds published ports and Traefik dashboard flags but does **not** remove the socket volume; the mount remains from `compose.yml`.

---

## 3. Upstream socket-free / API-only observation (not a Loadline patch)

Upstream documents a **hybrid** workflow that avoids running the full Traefik stack while still using containers for dependencies. This is an **observation** for investigators and future hint design; Loadline must not create a patched compose file in the pin.

**Supporting services only (from `development.md` and `backend/README.md`):**

```bash
docker compose up -d db mailpit
```

**API on the host (from `backend/`, after `uv sync` and migrate/seed):**

```bash
uv run bash scripts/prestart.sh
uv run fastapi dev
```

Documented API base: `http://localhost:8000` (Swagger at `/docs`).

**CI analogue:** `.github/workflows/test-backend.yml` runs `docker compose up -d --wait db mailpit` then backend tests with `uv` on the runner — not the full `proxy`+`watch` stack.

**Scoring note:** A later e2e that only runs `analyze --json` may still **pass** while `analyze --boot` on the **default** compose tree remains `policy_refused`. A full `loadline run` that boots only `db` (+ `mailpit`) would require a **policy-valid** launch plan derived without forbidden mounts (e.g. future `.loadline.yaml` hints or compose profile support) — **out of scope** for the pinned files as-shipped. Do not score “failure” for refusing the stock `compose.yml` that includes `proxy`.

---

## 4. If a full load test were allowed (counterfactual — unverified here)

No k6 baseline or Investigator run was executed for this document. The following describes **how to judge report quality** if boot ever succeeded under policy (e.g. after an allowed subset plan outside this pin’s default compose).

### Evidence a good report must separate

| Category | What “good” looks like |
| --- | --- |
| **Measured k6** | Throughput, latency percentiles, error rate per operation and mix; each number tied to evidence ids; bracket/calibration from `waves/` and ledger recompute (`tech_doc.md` §14.4). |
| **Resource telemetry** | cgroup CPU/memory/throttle for app and dependencies; Postgres adapter metrics when `db` is in the plan; gaps listed under Limitations, not filled with guesses. |
| **Code locations** | File paths and mechanisms cited only after `read_file` (or Entire/ripgrep hits that were read). Example of a discoverable read-safe route (upstream source actually read): `backend/app/api/routes/utils.py` defines `GET /api/v1/utils/health-check/` (prefix from app config). |
| **Hypotheses** | Labelled **hypothesis**; predictions code-scored (`confirmed` / `refuted` / `inconclusive`); causal language only with confidence rules (§12.2). |
| **Missing telemetry** | Explicit `not measured (reason)` — e.g. no replica scale test, no soak, Mailpit not on critical path for read-safe ops. |
| **Incomplete investigation** | `investigation_incomplete(reason)` with partial experiment log; report still written from ledger. |

### Rules for scorers

- **No invented bottlenecks** — do not accept findings that name a performance defect (N+1 queries, sync blocking, connection pool exhaustion, etc.) unless the report ties them to **measured** experiment outcomes **and** code read in that run.
- **Unverified** — any capacity knee, SLO breach root cause, or “primary bottleneck” stated without k6 + telemetry evidence in the ledger is **unverified** and should fail the scorecard.
- **Do not claim this target’s bugs** — this analysis did not measure the app. Generic stack facts (FastAPI, SQLModel, PostgreSQL 18 image in compose) are context only, not findings.

---

## 5. Neatlogs fields for the later e2e

Record on the integration run (see `tech_doc.md` §15 and `design/11-harness-review.md`):

| Field | Expected value |
| --- | --- |
| Workflow name | `loadline` |
| Tags | `run_id:<id>`, `agent_profile:<v0\|v1>`, `fast:<true\|false>` (implementation may also emit `neatHack` and `loadline_rev:<sha>` — do not fail solely for extra tags) |
| Investigator wrap | `neatlogs.wrap(Agent)` under one workflow trace per CLI invocation |
| TOOL attributes | `loadline.result_id`, `loadline.ok`, `loadline.experiment_kind`, `loadline.adapter` (`entire` or `ripgrep` on code-intel tools) |

**What “good” looks like in neatlogs:**

- A trace exists for the run (hosted URL in `RESULTS.md` when `NEATLOGS_API_KEY` is set).
- TOOL spans show failures explicitly (`loadline.ok=false`) — e.g. boot blocked, tool error — not silent drops.
- No fabricated metrics in span attributes; heavy series stay in the run ledger, summaries in tools/report.
- If Investigator never runs (boot blocked), the trace may be short; that is acceptable if boot/policy spans are present and honest.

---

## 6. Scorecard for `integration/RESULTS.md` (pass/fail)

Apply after the e2e. Each question is **pass** only if fully true.

1. **Pin integrity:** Target SHA in results matches `7257e606cb94eada1dca40173e2b7f99dd549bc6`, clone was not modified, and no route/handler names from this app appear in `loadline/` discovery code (only in integration docs).
2. **Discovery honesty:** `analyze --json` reports compose-based runtime discovery with evidence (e.g. `compose.yml`, backend Dockerfile, languages) without claiming a successful full-stack boot when boot was not attempted or failed.
3. **Policy outcome:** `analyze --boot --json` (or full run) records `policy_refused` for the Traefik `proxy` `/var/run/docker.sock` mount **or** documents an equally valid named blocker with evidence; policy was not weakened to force success.
4. **Evidence discipline:** Any report or investigator output distinguishes measured k6/telemetry from hypothesis; no performance bottleneck is asserted without ledger-backed measurements and read_file-grounded code paths; invented numbers fail.
5. **Observability:** neatlogs trace link (when key configured) uses workflow `loadline`, includes tags `run_id`, `agent_profile`, and `fast`, and investigator/code tools expose `loadline.result_id`, `loadline.ok`, `loadline.experiment_kind`, and `loadline.adapter` where applicable; teardown left zero labelled objects (`doctor --cleanup`).

---

## Appendix: relationship to prior S8 reference

`integration/RESULTS.md` (2026-10-10) already recorded discovery **pass**, boot **blocked** `policy_refused` on `proxy` host bind mount, and skipped smoke/baseline/investigator. A future e2e should match or explicitly supersede that row with the same expectations unless the pin or Loadline contract changes.
