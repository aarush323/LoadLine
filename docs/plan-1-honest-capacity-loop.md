# Plan 1 — Honest capacity loop

Status: plan only. No product code in this document.
Written against the tree on 11 Oct 2026.
Deadline: Monday 12 Oct 2026, 19:00–23:55 IST.

This plan finishes the product loop the investigator already started. A run boots a containerized repo, measures it, names one failure with a ledger id, patches only that cited code, replays the same k6 call, and publishes a before/after report. A pull request exists only when the cited metric moved. A flat remeasure is a successful honest run and a failed hypothesis.

`design/08-fix-agent.md` and the pitch line “fixing is deferred” described the first build, which stopped at the report. Report generation now exists. The next build is the verification loop. The investigator in `loadline/investigator/` stays the investigator. Sandbox refusals in `loadline/core/sandbox_policy.py` stay refusals.

---

## 1. What the code does today

These are facts from the current tree, including places where older docs have drifted.

| Surface | What actually happens |
|---|---|
| `loadline run` | Auth check, `boot_repository`, then `run_investigation_sync`. On success the agent’s last message is written verbatim to `report.md`. `report.json` is `{"run_state", "source": "investigator_agent"}`. |
| Investigator tools | Registered tools are `repo`, `read_file`, `run_k6` (`loadline/investigator/agent_factory.py`). `search_code` and `code_graph` exist in `tools.py` and are not registered. |
| Measurements | Each `run_k6` call is persisted as `experiments/<experiment_id>.json` with the tool input (endpoints, rate, duration) and the parsed output, and as a `k6_run` ledger row. |
| Files the agent read | `read_file` appends `ReadRange` onto `InvestigationDeps.read_ranges`. That list is not written to the run directory. A later process cannot see it. |
| Structured report | `loadline/core/report_render.py` and `ReportModel` exist and are unit-tested. `run_pipeline.py` does not call them. |
| Ladder / experiment kinds | `build_measurement_plan` is used by `tests/unit/test_measurement_plan.py` only. The live path does not run calibration, a bracket, or kind-specific plans. `docs/implementation-status.md` overstates this. `docs/remaining-gaps.md` is closer, and it is stale on health-path inference. |
| Dashboard data | The page is real (`loadline dashboard --serve`). Charts come from `k6_run` rows. Hypothesis and finding panels look for ledger kinds `hypothesis` and `finding`. The live investigator never appends those kinds. The web test fabricates them. |
| Boot | Compose or Dockerfile. Health URL prefers `.loadline.yaml`, then an HTTP URL inside `healthcheck.test`, then port 8000 and path `/health`, and also probes `/healthz` and `/readyz`. One compose file is loaded. Override files are not merged. |
| Hints that change boot | `compose_file`, `dockerfile`, `app_service`, `container_port`, `health_path`. |
| Hints parsed and ignored | `compose_profile`, `command`, `env`, `exclude_operations`, `slo.p95_ms`, `slo.err_rate`. |
| Setup | No `loadline load`. `skills/loadline-run/SKILL.md` tells an external coding agent to run `analyze --boot --json` and edit `.loadline.yaml` only. |
| Fix / PR | No command, no branch, no comparison artifact. |
| Fixtures | `fx-pyhttp-pg` and `fx-docker-http` have no planted flaw (`tests/oracles/fx-pyhttp-pg.sealed.yaml` says `flaws: []`). They can prove boot and a report. They cannot prove a fix. |
| FastAPI pin | `integration/targets/full-stack-fastapi-template` is refused because Traefik bind-mounts `docker.sock`. That refusal is the correct demo sentence. |

`docs/remaining-gaps.md` still says health always defaults to `/health`. That was true before `_parse_healthcheck_http` and `_health_url`. A healthcheck whose `test` contains `http://localhost:<port><path>` is already used. A healthcheck that is only `CMD curl -f` with no URL, or a path that lives only in application code, still falls through to `/health`.

---

## 2. Finished means these artifacts exist

1. `uv run loadline run --repo tests/fixtures/fx-pyhttp-pg --fast` prints `report.md` and `loadline dashboard --serve` opens that run.
2. `uv run loadline load <repo>` either boots and writes `.loadline.yaml`, or stops on a security blocker with zero model calls. The FastAPI pin still exits `policy_refused`.
3. One repo with a real, local, measurable defect produces:
   - a first report whose slow operation is tied to an `experiment_id` in `experiments/*.json`
   - a patch on a new branch, limited to a file `read_file` actually returned
   - a second k6 execution with the same endpoints, the same rate, and the same duration
   - `verification.json` plus a comparison section whose numbers were copied from the two experiment files
4. A pull request exists only when `verification.json` says `improved` on the metric the contract named. The body contains that table. A flat result writes `hypothesis_failed` and does not open a pull request.
5. neatlogs shows workflow `capacity-investigation` for one real run. `entire checkpoint list` shows a checkpoint after a hackathon commit. `docs/cfo-plan.pdf` exists, produced by a human at cfo.ai, with assumed numbers labelled as assumptions.
6. `uv run pytest tests/unit -q --tb=line` is green after every chunk. The sandbox policy tests still refuse `docker.sock`, privileged mode, and host mounts.

A report that reads the same before and after is a valid product outcome. It is not a demo of a fix. The demo of a fix requires the cited metric to move for the cited operation.

---

## 3. Out of this plan

- Rewriting the investigator, its prompt structure, or its three tools.
- Driving the unused bracket, ladder, and `build_measurement_plan` kinds. That is a different product. This plan replays one stored `run_k6`.
- Weakening `SandboxPolicy`, allowing `docker.sock`, or editing the pinned FastAPI compose so the pin boots.
- MySQL, Mongo, Redis, GraphQL, Kubernetes, write-heavy workloads.
- Dashboard redesign. The comparison a developer reads in this plan is `verification.json` and a section of `report.md`. Visual layout is plan 2.
- Claiming every repository boots.

---

## 4. The contract the loop is allowed to trust

The model may suggest a fix. Code decides whether that suggestion is about a real measurement.

### 4.1 Persist what the process currently drops

At the end of a completed investigation, write `run_dir/reads.jsonl`, one JSON object per successful `read_file`: `path`, `start_line`, `end_line`, `evidence_id`. The data is already on `InvestigationDeps.read_ranges`. Without this file, a later verify command cannot prove the patch touches code the agent saw.

Also require each `experiments/<id>.json` `input` to keep `endpoints`, `rate`, and `duration_s` exactly as `run_k6` was called. That file is already written by `_persist_experiment`. The replay reads it and does not ask the model for a new rate.

### 4.2 Fix contract

The investigator’s last message may end with one fenced block:

```yaml
loadline_fix:
  experiment_id: exp-k6-0003
  operation_id: items
  metric: p95_ms          # p95_ms | error_rate | achieved_rps
  direction: decrease     # decrease for p95_ms and error_rate; increase for achieved_rps
  control_operation_id: health
  path: app.py
  start_line: 12
  end_line: 18
  rationale: one sentence
```

A parser accepts the block only when all of the following are true:

- `experiment_id` is a file under `experiments/`.
- `operation_id` is a key in that file’s `output.operations` (or the equivalent field `format_run_k6_result` actually writes). If per-operation stats are missing, the contract is rejected. An aggregate-only run cannot prove which endpoint moved.
- `path` plus the line range is covered by some record in `reads.jsonl`. A range the model invented is rejected.
- `path` is application source. Reject `Dockerfile`, `dockerfile`, `compose*.yml`, `compose*.yaml`, `docker-compose*`, `.env`, `.env.*`, `*.lock`, `.loadline.yaml`, anything under `loadline/`, and anything under `tests/oracles/`.
- The before-number is not taken from the model. Code copies `p95_ms`, `error_rate`, and `achieved_rps` from the experiment file into `verification.json` under `before`.

If the block is absent or fails these checks, status is `no_verifiable_fix`. No branch, no patch, no pull request. The original report still stands.

### 4.3 Patch

A second, short agent may propose a unified diff. It receives only:

- the contract
- the `read_file` snippet for that range
- the before numbers from the experiment file
- an instruction to change the smallest region that explains the cited metric

Its only write is a diff. It has no `run_k6` tool and no shell.

The applier then:

1. Refuses the diff unless every changed file is the contract `path` (one file in this build).
2. Refuses the diff above 80 changed lines.
3. Refuses a dirty target worktree. Verification happens on a new branch `loadline/verify-<run_id>` from a clean `HEAD`. If the target is not a git repo, stop and say so.
4. Runs `git apply --check`, then `git apply`.
5. Does not commit until the remeasure exists. The commit that lands on the branch contains only the applied diff.

Loadline’s own repo is not the target. The patch lands in the repository that was measured.

### 4.4 Same k6

“Same” means the object in `experiments/<id>.json` `input`:

- same endpoint list (method, path, body, headers, weight, auth flag)
- same `rate`
- same `duration_s`

Implementation calls the existing `run_k6` function (or `run_k6_plan` with the stored plan), not a fresh `loadline run`. A second investigator would pick new rates and the comparison would be a different experiment.

Boot the patched branch with the same `.loadline.yaml` and the same sandbox policy. If boot fails, status is `remeasure_blocked`. No pull request.

Also replay the control operation at that same rate and duration when the original experiment did not already include it. The original experiment’s row for the control is the control-before number. If the original experiment had no control, record `control: not measured` and do not let the control gate pass. A single-endpoint improvement with no healthy neighbor is reported and does not open a pull request. The defect fixture below always has both `/health` and the slow route, so the demo path has a control.

### 4.5 When a number “improved”

Compare only the contract metric, on the contract operation, at the contract rate.

| Metric | Improved |
|---|---|
| `p95_ms` | `after <= before * 0.75` and `after <= before - 20` |
| `error_rate` | `after <= before - 0.05` (five percentage points) |
| `achieved_rps` | `after >= before * 1.25`, and `p95_ms` did not rise by more than 10% |

Control gate, when the control was measured at the same rate: control `p95_ms` did not rise by more than 20%, and control `error_rate` did not rise by more than 0.02. If the cited operation improves and the control blows up, verdict is `regressed_control`.

Any other movement is reported in the table and does not authorize a pull request. In particular, a different operation getting faster while the cited operation is flat is `hypothesis_failed`.

Run the replay once. A second identical replay is allowed only to estimate noise, and only the first replay is the official after-number unless the two after-numbers disagree by more than the improvement margin, in which case the verdict is `inconclusive`.

### 4.6 What the developer reads

`verification.json` (written by code):

```json
{
  "schema_version": "loadline-verification/1",
  "source_run_id": "",
  "experiment_id": "",
  "operation_id": "",
  "control_operation_id": "",
  "metric": "p95_ms",
  "direction": "decrease",
  "rate": 10,
  "duration_s": 15,
  "endpoint": {"method": "GET", "path": "/api/items"},
  "before": {"experiment_id": "", "p95_ms": 0, "error_rate": 0, "achieved_rps": 0},
  "after": {"experiment_id": "", "p95_ms": 0, "error_rate": 0, "achieved_rps": 0},
  "control_before": {},
  "control_after": {},
  "verdict": "improved",
  "pr_opened": false,
  "pr_url": null,
  "branch": "",
  "patch_paths": []
}
```

`verdict` is one of `improved`, `hypothesis_failed`, `regressed_control`, `inconclusive`, `no_verifiable_fix`, `remeasure_blocked`.

Append this section to `report.md` with a code writer, leaving the investigator’s prose above it untouched:

```markdown
## Verification

Verdict: improved

| | Before | After |
|---|---|---|
| Experiment | exp-k6-0003 | exp-k6-verify-0003 |
| Call | GET /api/items | GET /api/items |
| Offered rate | 10 req/s | 10 req/s |
| Duration | 15 s | 15 s |
| p95 | 412 ms | 18 ms |
| Error rate | 0.00 | 0.00 |
| Achieved | 9.8 req/s | 10.0 req/s |
| Control GET /health p95 | 6 ms | 7 ms |

Before numbers are copied from experiments/exp-k6-0003.json. After numbers are copied from experiments/exp-k6-verify-0003.json. The investigator’s earlier prose is not a measurement.
```

The terminal prints the same table at the end of `loadline verify`.

### 4.7 Pull request

Open a pull request only when `verdict == improved`.

Body, generated from `verification.json` only:

- one sentence naming the operation, the metric, and the two numbers
- the table above
- the path and line range
- a short excerpt of the investigator prose, truncated, labelled as the hypothesis
- the branch name and the source run id

The body must not contain a number that is absent from `verification.json` or the cited experiment files.

Push the verify branch and `gh pr create` against the target repo’s default branch. Loadline does not force-push. If `gh` is missing or the target has no GitHub remote, write `pr-body.md` next to `verification.json`, leave `pr_opened: false`, and stop. That is a recorded miss, not a silent success.

On `hypothesis_failed`, do not push. Leave the branch local so the diff can be inspected, and say that the hypothesis failed.

---

## 5. Chunk 0 — One real report, and a regression baseline

### Goal

Prove this machine can boot the known-good fixture, finish an investigator run, and open the dashboard on that run directory. Fix install and runtime breakage before any new command.

### Steps

1. `uv sync` in the Loadline repo.
2. `uv run loadline doctor` and, only if you accept a provider charge, `uv run loadline doctor --check-model`.
3. Docker is running. `uv run loadline doctor --cleanup` if a previous run left labelled containers.
4. `uv run loadline run --repo tests/fixtures/fx-pyhttp-pg --fast`
5. Confirm stdout contains `--- report ---` and stderr prints `report:` and `run_dir:`.
6. `uv run loadline dashboard --serve --no-browser` and open the printed run. The page loads. Peak offered load is a number from a `k6_run` row, or the page says not measured. It must not invent a finding.
7. Record the run id, exit code, and whether the report is `completed` or `investigation_incomplete`. Both are honest. A missing `report.md` on exit 0 is a bug in this chunk.

### Automated tests (run before and after any fix in this chunk)

```bash
uv run pytest tests/unit -q --tb=line
uv run pytest tests/unit/test_sandbox_policy.py tests/unit/test_no_fixture_leakage.py tests/sandbox/test_sandbox_hostile.py -q
```

`tests/sandbox/test_boot_fixture.py` and `tests/sandbox/test_run_pipeline_fixture.py` if Docker is up. The pipeline fixture may skip the investigator; that still has to pass.

### Checkpoint

Write down, in the session notes, the run directory path and the first headline sentence of `report.md`. If this chunk fails, the rest of the plan does not start.

### Done when

The command prints a report and the dashboard serves that run. Unit tests are green. Hostile-compose tests still refuse.

---

## 6. Chunk 1 — `loadline load` for a containerized repo

### Goal

One command trial-boots a repo. When boot is blocked for a reason that a hint can fix, a short agent writes `.loadline.yaml` and boots again. Security refusals never reach that agent.

### Command

```bash
uv run loadline load <repo>
```

Behavior:

1. Load `.loadline.yaml` through the existing `load_hints`. An invalid file stops immediately with the parser error. The agent is not asked to invent keys.
2. Call the existing `analyze_boot_json` / `boot_repository` path. Do not fork a second boot implementation.
3. If status is `booted`:
   - If `.loadline.yaml` is absent, write one with `schema_version: "1"` and the values the successful boot actually used: `compose_file` or `dockerfile`, `app_service`, `container_port`, `health_path`.
   - If the file already exists, leave it untouched.
   - Print `booted` and the hint path. Do not run k6. Do not start the investigator.
4. If `blocker.security` is true, or `blocker.code` is `policy_refused`: print the blocker JSON and exit 10. Do not construct a model client. The FastAPI pin stays on this path.
5. If status is `blocked`, `retryable` is true, and `security` is false: start the setup agent.
6. Stop after two hint writes (three boots total, matching the skill). Then print the last blocker.

### Setup agent

System prompt, in one place next to the command: you may read config and write `.loadline.yaml`. You may not edit Compose, Dockerfiles, or application source. You may not run load.

Tools, and no others:

| Tool | Allowed |
|---|---|
| `read_config` | Repo-relative reads of compose files, Dockerfiles, `.env.example`, `README*`, and the current `.loadline.yaml`. Refuse `.env`, keys, and pem files. Return file text, the last blocker, and `config_schema`. |
| `try_boot` | One call to `boot_repository`. Returns status, blocker, attempts. |
| `write_hints` | Validate with `LoadlineHints`, write atomically (temp file, re-parse, rename). |

Writable keys for this agent: `schema_version`, `compose_file`, `dockerfile`, `app_service`, `container_port`, `health_path`, `compose_profile`.

Not writable by the agent in this chunk, because boot ignores them today: `command`, `env`, `exclude_operations`, `slo.p95_ms`, `slo.err_rate`. If the agent emits them, `write_hints` rejects the file. The user can still put them in the file by hand later, once chunk 1b applies them.

`write_hints` rejects unknown keys, a `health_path` that does not start with `/`, and any env-like secret even if a future key is added. It rejects a payload whose serialized form contains `docker.sock`, `privileged: true`, or a host bind.

The agent is not given `run_k6`, a shell, or a general file writer.

Usage limit: 8 model requests. On auth failure, exit 2 the same way `loadline run` does, before Docker.

### Boot holes to close in this chunk

Close a hole only when a test or the chosen demo repo hits it. Do not boil the ocean.

**Compose merge.** `_resolve_compose_path` loads one file. Docker’s own rule is: a project file plus `compose.override.yaml` / `docker-compose.override.yml` when present. Implement merge by asking Docker, not by re-coding the spec:

```bash
docker compose -f compose.yaml -f compose.override.yaml config --format json
```

Feed that JSON into the existing sandbox policy and the rest of `boot_repository`. If `docker compose config` fails, the blocker is the compose error, with `retryable: true` and `security: false`, and `remediation` points at `compose_file`.

Discovery today lists only `compose.yaml`, `compose.yml`, `docker-compose.yaml`, `docker-compose.yml` at the repo root (`COMPOSE_NAMES`). Teach it to notice a sibling override file and to pass both `-f` arguments. A contradiction note can remain. The boot path must still merge.

**Health URL.** Keep the current order: hint, then HTTP URL parsed from `healthcheck.test`, then `/health` plus `/healthz` and `/readyz`. Add a unit test that already matches `_parse_healthcheck_http`. Extend the parser only if the demo repo’s healthcheck is a shape the current regex misses; record the exact `test` string in the test. Do not hardcode `/api/v1/utils/health-check/`.

**Hints that are still ignored.** Wire these in the sandboxed plan, not by editing the user’s compose file:

- `compose_profile` → `docker compose --profile <name>` on the up command.
- `command` → replace the app service `command` on the policy-rewritten plan copy. Reject values that mention `docker.sock`, `privileged`, `/var/run/docker.sock`, or `network_mode: host`.
- `env` → merge onto the app service environment, then run the existing env policy so secrets are still generated or refused.
- `exclude_operations` → drop those operation ids before `run_k6` builds a mix. This does not matter for `loadline load`, which never calls k6. Wire it so a later `loadline run` honors the file `load` just wrote.
- `slo.p95_ms` and `slo.err_rate` → pass into the verdict helper instead of the hardcoded `slo_p95_ms=2000.0` in `k6_runner.py`. If unset, keep 2000 and say the SLO source is the default.

Each wired key gets one unit test that fails if the key is parsed and then dropped.

If Monday is slipping, ship merge + the keys the demo repo needs, and make `loadline load --json` list `hints_ignored: [...]` for the rest. Silence is the bug. A listed ignore is an honest blocker.

### Skill

Update `skills/loadline-run/SKILL.md` so it calls `loadline load` when that command exists, and so its writable keys match the agent. The skill remains the external-agent description of the same rules. It is not a substitute claim that an in-product agent exists.

### Automated tests

Unit, no Docker:

- A compose file plus an override that adds `healthcheck` and `command` is what `docker compose config` would merge. If Docker is absent in unit tests, assert the argument list passed to the compose command includes both `-f` paths, using a fake runner.
- A service with `docker.sock` still returns `policy_refused` and `security: true` after merge. Existing `tests/unit/test_sandbox_policy.py` and `tests/sandbox/test_sandbox_hostile.py` stay as they are.
- `write_hints` rejects unknown keys, `command: curl http://host/docker.sock`, and a write outside `.loadline.yaml`.
- The setup-agent tool list, inspected in a unit test, does not contain `run_k6` or any writer except `write_hints`.
- A fake boot that returns `policy_refused` causes `load` to exit 10 with a model-call counter still at 0.
- A fake boot that returns `blocked` + `retryable` + a remediation field `health_path` leads to one `write_hints` and a second boot. The third boot is not attempted after success.
- `compose_profile`, once wired, appears on the compose argv.

Sandbox, Docker:

- `tests/fixtures/fx-pyhttp-pg` still boots via `loadline load` and gains a `.loadline.yaml`. Restore the fixture git state afterward so the fixture stays clean; write the hint assertion against a copy under `tmp_path`.
- New fixture `tests/fixtures/fx-compose-override`: base `compose.yaml` whose app image has no health URL, override file that sets the healthcheck URL and the listen command. `loadline load` on a temp copy reaches `booted`. Before the merge fix this fixture must fail; that is the regression the test locks.
- New fixture `tests/fixtures/fx-sock-proxy`: a proxy service bind-mounting `/var/run/docker.sock`. `loadline load` exits 10, security true, and the model-call counter is 0. This is the FastAPI-shaped refusal without depending on the pin being cloned.

Regression after the chunk:

```bash
uv run pytest tests/unit -q --tb=line
uv run pytest tests/unit/test_sandbox_policy.py tests/sandbox/test_sandbox_hostile.py tests/sandbox/test_boot_fixture.py -q
```

### Checkpoint you run by hand

You need to give one repository path that is not under `tests/fixtures/` and not the FastAPI pin. See section 10.

```bash
uv run loadline load <that-path>
uv run loadline run --repo <that-path> --fast
```

Pass: either a `report.md`, or a printed blocker whose `security` field is true. The FastAPI pin, if you run it, must still be `policy_refused` with the docker.sock / host bind sentence. Say that sentence in the demo.

Fail: the command edits a Dockerfile or compose file; the command calls k6 during `load`; the sock fixture boots; unit tests go red.

### Done when

`loadline load` on the override fixture boots, the sock fixture is refused with no model call, and one non-fixture repo either reaches the investigator or returns a security blocker.

---

## 7. Chunk 2 — A defect you are allowed to prove

### Goal

Give the loop a target where one endpoint is slow for a reason that sits in application source, and a neighbor endpoint that stays fast. `fx-pyhttp-pg` is the boot canary. It is the wrong proof target: its oracle allows an honest null, and a patch there would be a random edit.

### Fixture `tests/fixtures/fx-blocking-handler`

Copy the shape of `fx-pyhttp-pg` (Dockerfile, compose, FastAPI, `/health`). Add one route, for example `GET /api/items`, whose handler blocks the worker for about 300–400 ms with a local call (`time.sleep` or a synchronous wait). `/health` does not block.

Rules:

- The fixture name, the sleep, and the route do not appear in `loadline/` strings, prompts, oracles read by production code. `tests/unit/test_no_fixture_leakage.py` must stay green.
- The slowness is in the handler the agent can `read_file`, not in compose, not in a host mount, not in a policy exception.
- Compose healthcheck uses an HTTP URL on `/health` so chunk 1’s boot path already works.

### Deterministic measurement test

`tests/sandbox/test_verify_replay.py` (Docker, no model):

1. Boot a temp copy of the fixture.
2. Call `run_k6` at a fixed rate (10 req/s, 15 s is enough) against `GET /api/items` and `GET /health`.
3. Record p95 from the experiment file.
4. Apply a patch that removes the blocking call. This patch lives under `tests/`, as the oracle for the harness. Production code does not contain it.
5. Boot again. Call `run_k6` with the same input object.
6. Assert the items p95 satisfies the section 4.5 rule and the health p95 does not trip the control gate.

This test proves the replay and the comparator. It does not prove the model is clever. That split is intentional.

### Automated tests with no Docker

- Comparator: before 400 ms, after 30 ms, control flat → `improved`.
- Comparator: before 400 ms, after 390 ms → `hypothesis_failed`.
- Comparator: items improve, health p95 doubles → `regressed_control`.
- Comparator: items flat, health improves → `hypothesis_failed`.
- Contract parser: experiment id missing from `experiments/` → `no_verifiable_fix`.
- Contract parser: path not in `reads.jsonl` → reject.
- Contract parser: model text says `p95: 12` while the experiment file says `410` → `before.p95_ms` is 410.
- Applier: diff touching `compose.yaml` → reject, worktree unchanged.
- Pull-request body builder: returns an error when verdict is not `improved`, and the body contains both numbers when it is.

### Checkpoint

```bash
uv run pytest tests/unit/test_verification.py tests/unit/test_no_fixture_leakage.py -q
uv run pytest tests/sandbox/test_verify_replay.py -q
```

Done when the sandbox test shows the slow route’s p95 drop and the healthy route stay flat, and the flat-number unit test refuses a pull request.

---

## 8. Chunk 3 — Close the loop on a real investigator report

### Goal

`loadline verify <run_dir>` reads a finished run, checks the contract, patches, replays, and writes the comparison. The investigator is asked, in a short addition to `agents/investigator_prompt.md`, to end with the `loadline_fix` block when it believes a small code change would move a metric it measured. The block is ignored unless section 4.2 passes. Do not turn the prompt into a checklist that names this fixture.

### Command

```bash
uv run loadline verify <run_dir>
uv run loadline verify <run_dir> --no-pr
```

`--no-pr` still writes `verification.json` and the report section. Use it until chunk 4’s GitHub path is ready.

Steps inside the command:

1. Refuse a run dir outside the Loadline home, same warning rule as `report show`, and refuse a missing `experiments/` directory.
2. Parse the contract from `report.md`. On failure, write `verification.json` with `no_verifiable_fix` and exit 0. The investigation itself succeeded; the fix was not verifiable.
3. Build `before` from the experiment file.
4. Ask the patch agent for a diff. Apply on `loadline/verify-<run_id>`.
5. Boot the branch. Replay the stored k6 input. Write the after experiment under a new id `exp-k6-verify-<n>` in a new run directory so the original ledger is not rewritten. `verification.json` points at both run ids.
6. Append the comparison section to the original `report.md` and to the new run’s `report.md`.
7. Print the table.

The original run’s containers are already torn down by `run_pipeline`. Verify boots again. It does not assume the old network still exists.

### Live checkpoint (spends a model call)

```bash
uv run loadline run --repo tests/fixtures/fx-blocking-handler --fast
uv run loadline verify <that-run_dir> --no-pr
```

Read `verification.json` yourself.

| `verdict` | What it means for the demo |
|---|---|
| `improved`, and the diff deletes or shortens the blocking call | This is the demo. The thing that was slow is faster at the same rate. |
| `hypothesis_failed` | The system worked. The suggested patch did not fix the measured route. Do not narrate it as a fix. Look at the diff. If the agent never cited `/api/items`, tighten the prompt’s one paragraph about control versus affected route and run once more. A second flat result stays a flat result. |
| `no_verifiable_fix` | The agent wrote prose and not a contract that matches a read and an experiment. The parser is doing its job. Adjust the prompt example of the fence, not the parser’s checks. |
| `regressed_control` | The slow route moved and `/health` got worse. No pull request. |

Do not keep re-running until a flattering number appears and then hide the failures. One success, or one recorded failure plus a prompt fix and a second run, is the honest budget. A third run needs a written reason that names which check failed.

### Automated tests

- `verify` on a fixture run directory assembled in `tmp_path` (copied experiment JSON, reads.jsonl, report fence) with the patch agent replaced by a stub diff: assertion is the comparison verdict, and `run_k6` was called with the stored rate.
- Stub diff that does not change the file: `hypothesis_failed`, `pr_opened` false.
- Missing fence: `no_verifiable_fix`, patch agent not called (counter is 0).

Regression:

```bash
uv run pytest tests/unit -q --tb=line
uv run pytest tests/unit/test_investigator_tools.py tests/unit/test_investigator_prompt.py tests/unit/test_no_fixture_leakage.py -q
```

### Done when

A verify command on the blocking-handler run writes a comparison whose before and after rows cite two experiment files, and a deliberately useless patch does not become a pull request.

---

## 9. Chunk 4 — Pull request only after the number moves

### Goal

`loadline verify <run_dir>` without `--no-pr`, on a target that has a GitHub remote, opens a pull request whose body is the comparison.

### Safety

- Branch `loadline/verify-<run_id>` from a clean HEAD.
- Commit only the applied file.
- `git push -u origin HEAD` for that branch. Never `--force`. Never `main`.
- `gh pr create` with a HEREDOC body built from `verification.json`.
- If verdict is not `improved`, the push function is not called. A unit test mocks `gh` and asserts it was not invoked.
- If the target remote is missing, write `pr-body.md` and stop.
- Loadline’s `.env` is not copied into the target and not committed.
- The verify command refuses to run if the target path is the Loadline repo itself, so a bug cannot open a pull request full of Loadline internals against this hackathon repo by accident. Override only with an explicit `--i-am-patching-loadline` flag that the demo does not use.

### Checkpoint

On `fx-blocking-handler`, after a verdict of `improved`:

- Open the pull request URL.
- The body contains the before p95, the after p95, the rate, the duration, and the path.
- The diff is the handler change.
- Push a junk patch on a scratch branch by hand is not part of the product. The unit test with a flat `verification.json` is what locks the gate.

If the live model’s verdict was `hypothesis_failed`, do not open a pull request “for the demo.” The checkpoint is the unit test plus the JSON file. You can still show that file on camera: the hypothesis failed, and no pull request was opened. For the video, prefer a run that actually improved, because that is the claim. Get that run from the fixture, whose defect is real.

### Automated tests

- Body renderer snapshot: numbers match the JSON, the word “improved” is absent when the verdict is `hypothesis_failed`.
- Mock subprocess: `gh` argv is empty when verdict is not `improved`.
- Existing git safety: the test repo’s default branch name is not the one that gets pushed.

### Done when

One pull request URL is real, or you have a written `hypothesis_failed` from the live model and a green test that `gh` is not called in that state. The video uses the pull request only in the first case.

---

## 10. The repository path this plan needs from you

Chunk 1’s “not a fixture” checkpoint needs a path on this machine.

What makes a good demo repo:

- It has a `Dockerfile` or a compose file and it is meant to boot with `docker compose`.
- It serves HTTP.
- It does not require `docker.sock`, privileged mode, or a host mount to start. If the only app you care about is the FastAPI template, we will boot it only to show the refusal, and the successful boot will be the override fixture plus your other repo.
- It is a git checkout with a clean worktree and a GitHub remote if you want the pull request on that repo rather than on `fx-blocking-handler`.

Reply with the absolute path. Until then, chunk 1’s automated fixtures still land, and the live non-fixture checkpoint waits.

The proof that a fix changed a measured failure is `fx-blocking-handler`, even if your repo’s investigation comes back with no bottleneck. A user repo with no defect must be allowed to end as “no bottleneck found.” Forcing a pull request there is the failure mode this plan exists to prevent.

---

## 11. Chunk 5 — Partner proof

Do this after chunks 0–4 have artifacts. Partners are 25% of the score. They are evidence, not a second product.

### neatlogs

- Key only in `.env` as `NEATLOGS_API_KEY`. Never in a plan file, a fixture, or a commit.
- One real `loadline run` (the blocking-handler run or the chunk 0 fixture run) with the key set.
- In app.neatlogs.com, the trace’s workflow is `capacity-investigation` (`loadline/neatlogs_workflows.py`).
- Probe: `uv run loadline-neatlogs-probe --hosted`.
- If there is time, a second trace where a tool step fails and a later step succeeds. A rejected `read_file` (bad path) followed by a successful `read_file` is enough. Do not fabricate a span.

Checkpoint: a trace URL you can open, plus the probe’s exit code.

### Entire

- `loadline doctor` already vendors the graph the investigator calls. Do not install a second Entire.
- Commit during the hackathon (when you ask for the commit) and keep Entire checkpoints.
- `entire checkpoint list` after that commit shows one.
- The code-map story in the demo is: `repo` / graph during the investigation, and `loadline doctor` printing `graph_relations` and `handles_route`.

### cfo.ai

- A human signs up at cfo.ai/neathacks, builds the pricing / cost / runway plan, exports `docs/cfo-plan.pdf`, and cancels billing immediately.
- No Python in this repo calls cfo.ai. A test can assert `loadline/` has no `cfo.ai` URL.
- Fill only numbers you can point at (model calls you actually made, a k6 duration you actually ran). Label every other figure as an assumption, consistent with `pitch.md`.

Checkpoint: the PDF is in `docs/`, and it is not committed if it contains account identifiers you do not want public. If the export has no secrets, it can be in the public repo. Check the PDF before you commit it.

---

## 12. Chunk 6 — Demo and submission

Only after the artifacts in section 2 exist.

Video, at most 3 minutes, in this order:

1. `loadline load` or `loadline run` on screen, live or a recording of a run from the same day. If you show the FastAPI pin, the frame is the `policy_refused` sentence.
2. `report.md` verdict and one `run_k6` citation (experiment id, route, p95).
3. `verification.json` table, then the pull request if and only if the verdict was `improved`.
4. One screen each: neatlogs trace, `entire checkpoint list` or doctor graph line, cfo.ai PDF.

Each partner, even as one sentence: architecture (what it is connected to), implementation (which command), runtime (what you ran), reasoning (what it was for), result (what you saw).

Submission is a public quote-post of the official neatlogs post on X: team, name Loadline, public repo, demo. Window is Monday 12 Oct 2026, 19:00–23:55 IST. Logistics stay in `hackathon_knows.md`.

---

## 13. Order and time

Today is Sunday 11 Oct 2026, morning IST. The submission window opens Monday 19:00 IST.

| When | Chunk | Stop if |
|---|---|---|
| Sunday morning | 0. Real report + unit tests | Report missing. Fix install. Do not start chunk 1. |
| Sunday afternoon | 1. `loadline load`, merge, sock refusal | Sock fixture boots, or unit tests go red. |
| Sunday evening | 2. Blocking fixture + comparator tests | Replay test cannot show a p95 drop on the sleep route. The loop is not ready for a model. |
| Sunday night | 3. `loadline verify` on one live run | |
| Monday daytime | 4. Pull request gate, then 5. partners | No pull request unless `improved`. Partner screens can be captured in parallel with chunk 4. |
| Monday 19:00–23:55 | 6. Video and quote-post | |

Chunk 1’s ignored-hint list is allowed to ship as an explicit `hints_ignored` field. Chunk 3’s parser checks are not allowed to ship loosened so a demo pull request can exist.

---

## 14. Command cheat sheet after this plan

```bash
uv run pytest tests/unit -q --tb=line
uv run loadline run --repo tests/fixtures/fx-pyhttp-pg --fast
uv run loadline load <repo>
uv run loadline run --repo tests/fixtures/fx-blocking-handler --fast
uv run loadline verify <run_dir> --no-pr
uv run loadline verify <run_dir>
uv run loadline dashboard --serve
uv run loadline-neatlogs-probe --hosted
uv run loadline doctor
```

Exit meanings that stay stable: 2 auth / doctor failure, 10 `policy_refused` or other boot block, 0 a finished run including `investigation_incomplete` and including `hypothesis_failed`. A failed hypothesis is not an exit-code error. The JSON verdict carries it.
