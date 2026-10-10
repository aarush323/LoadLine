# Loadline — implementation plan

Build order for `tech_doc.md`. This file does not add scope. Do not start a step until the previous step's gate is green. Do not start product code until this plan's review note at the bottom says locked.

## 0. Rules for the build

1. One code path. The generator runs only as a container on the run network. There is no host-k6 path and no published target port.
2. Tests for verdicts, the bracket, the evaluator, confidence (64 combinations), `SandboxPolicy`, `TargetGuard` and the hints parser are written before the implementation they lock.
3. `test_no_fixture_leakage` exists in S1 and stays green.
4. A missing tool degrades that capability or returns a named blocker. It does not start a second policy.
5. Numbers in reports come from the ledger. The phrase for a missing number is "not measured (reason)".
6. Stack facts live in catalogue data and in `.loadline.yaml` keys listed in `tech_doc.md` §16.3. Core does not grow a special case for a framework.

## 1. Order

```text
S0 spikes
  → S1 core, auth preflight, hints schema
  → S2 read-only discovery
  → S3 sandbox, probe, boot JSON
  → S4 k6 on the internal network
  → S5 telemetry and limit_attribution
  → S6 experiments, baseline, report
  → S7 Investigator
  → S8 evaluation
  → S9 skill and installer
```

S4's gate is the point at which load testing may be called working. S9 starts only after S8 is green.

## 2. S0 — Spikes

Record each result in `docs/spikes.md` as pass, fail, or blocked, with the command and the output summary. A fail stops the step that depends on it.

| Spike | Pass looks like | If it fails |
|-------|-----------------|-------------|
| S-DOCKER | Rootless Docker or Podman creates an internal network. A container on it cannot open an external address. A second container on it reaches the first by alias. The spike writes `PROBE_IMAGE_DIGEST` as a `sha256:` digest. An empty value fails the spike. | Stop. Do not invent a host-k6 fallback. |
| S-GEN | The pinned k6 image accepts a script on stdin, writes a summary that includes `dropped_iterations` and per-operation metrics, and can be killed. Ceiling is measured against a null server on the same network. Note whether Docker Desktop's VM, not the laptop, is the CPU ceiling. | Stop S4. |
| S-CGROUP | Per container, record the CPU and memory fields this engine actually returns. CPU usage must be readable. If `cpu.stat` `throttled_usec` or Docker `throttling_data` is absent, record `not measured (field absent)`. OOM is recorded when the engine exposes it. | CPU usage unreadable stops S5. Missing throttle does not. Do not treat a missing field as zero. |
| S-ENTIRE | On 4–5 real repos: `capabilities --json`, `query` vs `search`, `def`, `neighbors`, `impact`. Record whether `HANDLES_ROUTE` exists and whether it maps an operation to a handler per language. Record `edges` as NDJSON and whether `--worktree` exists. | Use ripgrep only; mark code intelligence degraded. Do not guess flags. |
| S-COMPACT | Optional. Try Harness `TieredCompaction` on a fake long board. Adopt it only if a real run exceeds the context budget. | Skip. Pydantic AI history processors remain the plan. |
| S-AUTH | One pinned model: structured output, a tool call, a timeout, usage numbers, and a missing-key error. API key only. | Do not start S7. Do not add a second provider to get past the failure. |

S-GEN does not compare a host k6 process as a product option. The container path is the product.

## 3. S1 — Core

**Build:** `pyproject.toml` console script `loadline` (Python 3.12, uv). Packages: `core/` (ledger, evidence, budgets, redaction), `constants.py`, CLI commands `run`, `analyze`, `report`, `doctor`, `dev`. Exit codes from `tech_doc.md` §16.2. Models for `RepoProfile`, `CapabilityReport`, `LaunchPlan`, `WorkloadPlan`, `Blocker`, `Hypothesis`, `Finding`.

**Auth preflight:** `run` and `analyze --boot` check `LOADLINE_MODEL` and the matching API key before any Docker call. Missing config exits 2 and names the variable. No model swap. `doctor` makes no provider call. `doctor --check-model` is opt-in and prints a billing warning.

**Hints parser:** load `loadline-hints/1` from `tech_doc.md` §16.3. Unknown keys fail. Secret-shaped values fail. Paths must stay inside the repo.

**Tests:** empty directory → named blocker, not a traceback. Unknown hint key rejected. Missing `LOADLINE_MODEL` does not create a container. `test_no_fixture_leakage` scans `loadline/`.

**Gate:** those tests pass. `loadline --version` and `loadline doctor` run.

## 4. S2 — Discovery (no execution)

**Build:** scanners for languages, manifests, compose files, Dockerfiles, entrypoints, dependency client libraries, OpenAPI files on disk, request tests, CI workflow files (read, never run), external URLs, image architecture vs host. Output `profile.json` and `capabilities.json`. Contradictions are stored, not merged away.

**Corpus:** 4 or 5 pinned repos, split tuning / held-out, with truth labels outside `loadline/`.

**Gate:** `loadline analyze` on every corpus repo exits without running a build, a container, or a CI command. Crashes are zero.

## 5. S3 — Sandbox, probe, boot JSON

**Build:**

- `SandboxPolicy` with the seven rules in `tech_doc.md` §7.4. Every service is moved onto this run's internal network. Published ports are rewritten off the host. Privileged, `docker.sock`, host mounts and host network are refused. There is no `--allow-egress`.
- Compose adapter and Dockerfile adapter. Catalogue images for dependencies. Limits from the table in `tech_doc.md` §7.3. `doctor` records engine CPU and memory; a smaller engine than the host is `docker_engine`.
- One internal network per run. Labels `loadline.run=<id>` on containers, networks and volumes. The run directory is under Loadline's home, not inside the target repo.
- Probe image is `PROBE_IMAGE_DIGEST` from spike S-DOCKER. S3 refuses an empty value or a floating tag. The container does not mount the repo. Egress must fail from the probe, the app container, and one dependency. The probe then calls the app by alias.
- Health check, bounded attempts (`BOOT_MAX_ATTEMPTS=5`). A repeated failure signature is not tried again. Migration commands are copied from the repo's own compose or scripts. Empty data that leaves no smoke-passing read is `data_missing`.
- Teardown always runs, in `finally`, on SIGINT, and on watchdog kill. No `--keep-env`. `doctor --cleanup` removes leftovers by label only.
- `analyze --boot --json` matches the document in `tech_doc.md` §16.1. Secret-shaped values in `launch_plan` and diagnostics are `[redacted]`. Every `remediation.field` is a §16.3 key. `security: true` implies `retryable: false`.
- Build network is recorded as `none` or `unrestricted`. It is not treated as the run network.
- Emulation (image platform ≠ host) is detected and stored.

**Tests:** at least 20 hostile plans. Egress fails from the probe and from the app while the probe can reach a fixture service by name. Teardown leaves zero labelled objects after success, failure and SIGINT. Two concurrent runs do not share a network. A compose file that publishes `0.0.0.0` or attaches an external network is rewritten or refused. A prod-looking URL is not contacted. Needs-secret ends `needs_input` and does not invent a credential. A secret does not appear in `launch_plan.json`. A target directory named `runs` is not used as the run directory.

**Gate:** most runnable corpus repos boot, respond to the probe, and tear down. The others return a named blocker and a usable attempt log. Load testing is still not claimed.

## 6. S4 — k6

This step is the load-test gate.

**Build:**

- Pin the k6 image by digest in `K6_IMAGE_DIGEST`. Empty or a floating tag is a failed S4. `doctor` checks that image, not `PATH`.
- Compiler: `WorkloadPlan` → one generic script. Operation ids and weights are the plan's. No string from the model is concatenated into the script.
- Stdin into the container. No mount of the user repo. No host `HTTP_PROXY`. Redirects that leave the service alias fail the step.
- `TargetGuard` rejects any URL that is not a service of this run.
- One k6 process per step, killable, generator lock held.
- Summary parser: throughput, p50/p95, error rate, `dropped_iterations`, VU, per operation. p99 only when samples reach `MIN_SAMPLES_P99`. Below `MIN_SAMPLES`, the percentile is `not measured` and a verdict that needed it is `invalid(measurement_gap)`. Raw output saved under the run id even if the process is killed.
- Calibration on this placement: null-target ceiling, quiet baseline, control probe. `RATE_CAP = 0.7 × ceiling`.
- Verdict order, ladder, bracket, refine and confirm exactly as `tech_doc.md` §9. Refine and confirm run only when asked.
- `WorkloadAdapter.discover` owns operations (`tech_doc.md` §8.1). Live spec first. The agent does not add routes. Zero smoke-passing `read_safe` operations is `no_working_operation`.
- Handler location: `HANDLES_ROUTE` only where S-ENTIRE confirmed it; otherwise ripgrep. Provenance kept separate from the live spec.

**Tests, written first:** verdict order; a 50-sample window does not print a p95; bracket statuses including `above_ladder` and `generator_limited`; VU formula; classifier table; plan hash stable; compiler rejects a non-sandbox URL; a redirect off the service fails; dropped iterations become `generator_limited`.

**Gate:** three booted services in different languages produce a valid bracket. A purpose-built case is detected as `generator_limited`. Until this gate is green, docs and the demo do not say load testing works.

## 7. S5 — Telemetry

**Build:** k6 client metrics, cgroup or engine CPU, memory and OOM, host CPU and fd/port pressure, generator CPU, redacted logs. Throttle is read only from the field spike S-CGROUP observed on this engine. A missing field is `not measured (field absent)`. `coverage` on every series. `limit_attribution` from `tech_doc.md` §10.4. Postgres adapter first. MySQL, MongoDB and Redis are later and their absence is `degraded`.

**Gate:** on two services with different datastores, a non-pass step has an attribution and evidence ids. A host-saturated step is not labelled as an application bottleneck. A run whose engine omitted throttle data does not claim `environment_limit` from throttle.

## 8. S6 — Experiments and report

**Build:** kinds `rate_step`, `rate_ladder`, `refine`, `confirm`, `isolate`, `mix_ablation`, `param_scale`, `resource_perturb` (including `scale_replicas` when Compose allows), `dependency_perturb`, `warm_cold`. `ExperimentPolicy.admit` returns legal alternatives on a reject. `PredictionEvaluator` uses `NOISE_REL`, `NOISE_ABS_MS`, and `MIN_SAMPLES` from `tech_doc.md` §11.4. Confidence function with `V` always false. Finding validator. Baseline stage: one full-mix ramp at 5 s / 15 s, no branch. Report sections and measured / projected / hypothesis tags from `tech_doc.md` §14. Projected section uses only measurements already taken. Wording lint. Recompute from `waves/`.

`EntireGraphProvider` as specified in `tech_doc.md` §5.3, including `--worktree` when the tree is dirty and the flag exists. Empty graph results do not become negative claims.

**Tests:** 64 confidence combinations. A delta inside `NOISE_REL` is `inconclusive` for a `changes_by` prediction and `confirmed` for `unchanged`. A prediction against an unknown readout is rejected. Report render fails when a digit is not in the model. A test driver in `tests/` may script experiments. That driver is not imported by `loadline/`.

**Gate:** the test driver produces a report with a non-empty Limitations section and a working baseline stage.

## 9. S7 — Investigator

**Build:** Pydantic AI agent, the seven tools in `tech_doc.md` §11.3, the four-section board, the existing `agents/investigator_prompt.md` (do not author a second prompt), `UsageLimits` (~40% of wall budget), output validator (digits must exist in `ReportModel`). Tool returns are named readouts with units, sample size, and deltas versus baseline and the previous experiment. neatlogs `wrap(Agent)` when `NEATLOGS_API_KEY` is set. Stall, error or budget → `investigation_incomplete(reason)` and the report is still written. No second investigator.

**Gate:** a test asserts the prompt file contains the hard rules, the `{{BOARD}}` placeholder, and no fixture name. On a fixture, the run ends in ranked findings or an honest null. Forcing a provider error yields `investigation_incomplete` and does not invent a finding.

## 10. S8 — Evaluation

**Build:** fixtures from `tech_doc.md` §18.1, sealed oracles, three hidden-cause cases (misleading comment, generator-bound run, two competing explanations), one git-history case (parent of a real performance fix). No-leakage test. Held-out repos are not used to tune.

**Gate:** every fixture and at least three held-out repos end in a report or a named blocker. Teardown is clean. A host-saturated or emulated run does not produce an application-bottleneck finding.

## 11. S9 — Skill and install

Start only after S8 is green. S3's boot JSON tests and the hints parser must already be green. The skill is not written during S3.

**Build:**

- `skills/loadline-run/SKILL.md` with the six sections in `tech_doc.md` §16.3. One body. Description mentions load-testing and scalability investigation.
- Package data: the built wheel contains that same file.
- `loadline skills status|install|uninstall`. Default scope is the user. `--host all` writes `~/.agents/skills/loadline-run/` and `~/.claude/skills/loadline-run/` only. Idempotent. Refuses to overwrite an unrelated file unless `--force`. Uninstall removes only files recorded in Loadline's manifest. Tests use a temporary home.
- Hackathon install remains clone, `uv sync`, `uv run loadline`. Docs do not say `pip install loadline`. No Docker image of Loadline. No `npx` wrapper for the CLI.
- The skill does not edit application code, does not guess config keys, and stops after two correction retries.

**Not in S9:** Claude or Codex marketplace packages, an MCP server, subscription-login adapters.

**Gate:** a repo with one retryable hint boots after the skill applies that hint. A missing-secret repo stops with a question and no invented secret. A hostile compose file stops with `security: true` and an unchanged policy. The skill file in the wheel matches the repo file.

## 12. After the gates

More database adapters, then a later fix-and-verify skill. Not before S8 is green.

## 13. Cut order

Cut extra database adapters, then report polish, then S9. Do not cut the sandbox policy, the target guard, the egress probe, teardown, named blockers, Limitations, ledger recompute, the no-leakage test, the wording lint, or the partner evidence (neatlogs traces, an Entire checkpoint, the cfo.ai PDF).

## 14. Done

`tech_doc.md` §18.6, plus: the S4 gate is green on the container network; `doctor` does not bill by default; a missing model key fails before Docker; the boot JSON and the hints schema are what the skill consumes.

## 15. Reference application

This is how a realistic repository is tested. It is not a special case in `loadline/`.

**Target.** `https://github.com/fastapi/full-stack-fastapi-template`, cloned into `integration/targets/full-stack-fastapi-template/`. That directory is gitignored. The clone is a clean checkout of one commit. The SHA is written to `integration/targets.lock.json` (`repo`, `commit`, `recorded_at`). The test does not follow a branch. The checkout is never patched and never pushed.

**When it runs.** Unit tests on ordinary edits. A targeted check when discovery, sandbox boot, route mapping, k6, telemetry, the Investigator, packaging, or teardown changes. One clean pinned run after a major integration change and before the demo. Do not rerun this stack after a trivial edit.

**What it checks, in order.** Each stage is pass, fail, or skipped-with-a-reason. Exit code 0 is not enough. The check reads the artifact.

1. Discovery wrote `profile.json` and `capabilities.json` without a container.
2. A missing or invalid hint produces a blocker whose `remediation.field` is a §16.3 key, or a non-retryable code.
3. Boot uses the internal network, the limit table, and the egress checks. Readiness is the probe's health result.
4. Operations come from the live OpenAPI document when the app serves one.
5. Entire records CLI version, graph plugin version, and capabilities. A handler mapping is kept only when `read_file` shows that location. A dirty tree uses `--worktree` when the command supports it.
6. A graph edge is not written up as a cause. An empty graph is not written up as "no call path".
7. Smoke and one baseline exist, with sample counts. A window under `MIN_SAMPLES` does not print a precise p95.
8. k6 ran as a container on the run network. Raw output is on disk.
9. The report separates measured numbers, source evidence, hypotheses, missing telemetry, and incomplete findings. No bottleneck is invented.
10. Teardown leaves zero objects labelled with this run id after success, failure, timeout, and SIGINT.

**Anti-overfit.** Route paths, service names, handler names, tables, and expected bottlenecks live in `integration/` fixtures if a test asserts them. They do not appear in `loadline/`. The deterministic regressions stay on `fx-pyhttp-pg` and `fx-node-mongo`. Negative fixtures cover missing secrets, hostile compose, failed readiness, an unsupported graph relation, a short sample, missing telemetry, and a failed Investigator. A stage that did not run is skipped, not passed. A number that was not measured is absent, not filled in.

**Record.** Each important run appends `integration/RESULTS.md` with the Loadline commit, the target commit, the engine, the stage that failed, the artifact path, and the diagnosis. Entire's install test stays a separate command from this graph-analysis run so a setup failure is not scored as a mapping failure.

## 16. Review

Composer approved this revision on 2026-10-10: network isolation, no egress flag, engine CPU ceiling, the limit table, discovery ownership, noise and sample rules, migrations, `data_missing`, image digests, the skill body, the investigator prompt, secret redaction, build versus runtime networks, unconditional teardown, run-directory placement, and the pinned reference-app test. Execution waits until you say to start. A failed spike stops the step that depends on it. It does not add a second path.
