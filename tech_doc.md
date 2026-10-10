# Loadline — technical contract

**Status:** this file is the only contract. `mvp.md` is the short scope. `implementation.md` is the build order. `design/*.md` is background and is not binding. If another file disagrees with this one, this one is right.

**Product:** `loadline run` in a repository that can be executed. Loadline discovers how it runs, boots it in an isolated Docker/Compose environment, finds real HTTP operations, load-tests them with k6, and an agent investigates scalability bottlenecks. The output is an evidence-backed report, or a named blocker.

The report separates **measured**, **projected** and **hypothesis**. "No bottleneck found within the measured range" and "blocked: <specific reason>" are valid outcomes. Loadline does not recognise planted flaws and does not fabricate numbers.

> The reference application demonstrates that Loadline works. It must never be the reason Loadline works.

---

## 0. What this build is

One command. Five deliverables:

1. **Point at a repository.** Discover how the app runs, its dependencies and its HTTP operations. Reuse its Docker/Compose configuration.
2. **Run it in isolation.** Docker/Compose, a deterministic safety policy, resource limits, cleanup. No custom sandbox product.
3. **Generate load.** k6, from the service's own spec, OpenAPI files, existing tests, and code. Smoke-test before any load. Read-safe operations only.
4. **Investigate.** Code runs one baseline ramp. The Investigator then chooses experiments, states hypotheses with structured predictions, and reads code. Code scores every prediction, verdict and confidence value.
5. **Report.** Measured capacity, ranked findings with code locations, experiments, confidence, remediation text, and a labelled projection. Confirmed findings, hypotheses and measurement limits stay separate.

**Built:**

| Area | This build |
|------|------------|
| Runtime | `compose` adapter (reuse the repo's files) and `dockerfile` adapter (repo Dockerfile plus catalogue dependencies) |
| Isolation | Hardened Docker. No privileged mode, `docker.sock`, host mounts, host network or published ports. Egress denied on an `--internal` network and checked with a probe. If gVisor is installed, detect it and print it. Docker is not a complete security boundary. |
| Protocols | HTTP |
| Workloads | Service spec endpoint, OpenAPI/Swagger, tests and collections, code (Entire plus file reads), LLM proposals. Smoke-tested. Read-safe only. |
| Load | k6 constant-arrival-rate. Calibration, verdicts, ladder, bracket. One baseline ramp before the agent. |
| Telemetry | Always on: k6 client metrics, cgroup CPU and throttling, memory and OOM, host, generator, logs. Then one dependency adapter at a time: Postgres, MySQL/MariaDB, MongoDB, Redis. |
| Code intelligence | `EntireGraphProvider` plus ripgrep plus line-ranged reads. Entire is optional; without it the run continues and code-location confidence is lower. |
| Agent | One Investigator. Seven tools (§11.3). Pydantic AI. |
| Experiments | `rate_step`, `rate_ladder`, `refine`, `confirm`, `isolate`, `mix_ablation`, `param_scale`, `resource_perturb` (including `scale_replicas` when Compose allows it), `dependency_perturb`, `warm_cold` |
| Report | `report.md` and `report.json`, the ledger, a Projected section, Limitations |
| CLI | `run`, `analyze`, `report`, `doctor`, `dev` |
| Delivery extra | One portable `loadline-run` skill, built only after `analyze --boot --json` blockers are trustworthy (`delivery.md`) |
| Acceptance | Fixtures with sealed oracles, hidden-cause cases, one git-history case, 4–5 corpus repos, held-out repos, no-leakage test |

**Not in this build** (do not implement, demo or claim): fixing and verifying a patch; an in-app environment-planning agent; an MCP server; per-host plugin packages; GraphQL, gRPC, WebSocket and queues; buildpack, process and Kubernetes runtimes; profilers; tree-sitter route packs; a metamorphic mutator; a 12-repo corpus; LSP; `report.html`; a Universal Scalability Law fit; write workloads; `data_scale`, `concurrency_step`, `profile_capture`, `soak_bounded`.

A repository with no usable Docker or Compose configuration ends in a named blocker (`no_entrypoint` or `boot_failed`). Loadline does not invent a project to test instead.

### Rules

| # | Rule | Enforced by |
|---|------|-------------|
| R1 | No language, framework, database, protocol, service count, layout, route or dataset size is assumed by core. Stack knowledge lives in adapter data, not in core. | `test_no_fixture_leakage` |
| R2 | Production code never recognises a fixture, its names, its paths, or a planted flaw. Oracles are sealed. | §18.4 |
| R3 | Every number in a report traces to an evidence record. Missing data is "not measured (reason)". | wording lint (§14.3) |
| R4 | Loadline detects what it can do and names the blocker when it stops. It does not claim every repository works. | capability report, Appendix A |
| R5 | Code owns measurements, limits, experiment legality, prediction scores, confidence, severity, ranking and every report number. The agent owns hypotheses, experiment choice, reading code, locating the mechanism and remediation wording. The agent cannot relax a limit or a safety rule. | §3.3 |
| R6 | The load target is only the isolated instance created for this run. URLs found in the repository are data, never targets. | `TargetGuard` (§7.6) |
| R7 | Ordinary Docker is not a complete boundary against malicious code. The isolation in force is printed. | §7.1 |
| R8 | Loadline does not modify, merge, rebase or push the user's branch. | git guard |
| R9 | Use k6 for load, cgroups for resource signals, ripgrep and Entire for code location. No custom load generator. | `design/12-oss-bom.md` |
| R10 | A finding keeps observed facts separate from hypotheses. A mechanism is a cause only after code confirms a discriminating prediction. | `record_finding` validator |

There is one investigation path. If the agent stalls, errors or exhausts its budget, the run ends `investigation_incomplete(reason)` and code writes the report from the ledger. There is no second policy that finishes the investigation.

---

## 1. Product definition

### 1.1 What the user does

```bash
cd any-runnable-repo
loadline run --goal "Find scalability bottlenecks and improve throughput"
```

`--goal` is optional; that sentence is the default. No config file is required. An optional `.loadline.yaml` may supply hints (§16.3). Hints never override the sandbox policy, the target guard, resource limits or egress rules.

### 1.2 What a finished run contains

1. **Discovery:** stack, services, dependencies, HTTP operations, launch method, each with evidence and a support level.
2. **An isolated environment:** the application and its dependencies, health-checked, observed, torn down.
3. **Workloads** taken from the repository's own interfaces and tests, smoke-tested, read-safe only.
4. **Measurements:** throughput, latency, errors, resource use, with generator, host and measurement failures separated from application behaviour.
5. **An investigation:** hypothesis, structured prediction, experiment, code-scored outcome, code location.
6. **A report** (`report.md`, `report.json`, evidence ledger) whose statements are marked measured, projected or hypothesis.

### 1.3 What Loadline is not

- Not a production load tester. It never targets production or arbitrary URLs (R6).
- Not for repositories that are not runnable services (libraries, mobile or desktop apps, GPU jobs, batch jobs with no request interface). Those end as `not_a_service` or `no_interface`.
- Not able to provision licensed databases, real third-party SaaS or cloud-only services. Those end as `needs_input` or `external_dependency`. Loadline never invents third-party credentials.
- No automatic merge, no web UI, no hosted service.

---

## 2. Decisions

| ID | Decision |
|----|----------|
| D1 | Core plus adapter families: runtime, workload, generator, observability, code intelligence. Typed interfaces (§5). |
| D2 | Each capability is `ready`, `degraded`, `needs_input` or `unsupported`. A missing adapter degrades that capability. It does not fail the run and it does not switch to a scripted investigation. |
| D3 | Load generation is k6 behind `GeneratorAdapter`, open-model `constant-arrival-rate`, one process per step. k6 is an unmodified binary inside a pinned container image. The script is passed on stdin. The image does not mount the user's repository. A host k6 binary is not required. |
| D4 | One placement only: the k6 container and a Loadline-owned probe container join the run's `--internal` network and address services by name and container port. No target port is published. There is no host-k6 mode and no loopback publish. |
| D5 | Adapters propose a `LaunchPlan`. Core `SandboxPolicy` validates or rewrites it. Only then does a runtime adapter execute it. |
| D6 | Isolation is hardened Docker on every run. gVisor is detected and printed when installed. There is no trust flag and no isolation flag. |
| D7 | Boot is deterministic: `compose` or `dockerfile`, then a named blocker with a bounded attempt log. There is no in-app planning agent. A later skill may edit `.loadline.yaml` and retry (§16.3, `delivery.md`). |
| D8 | Workloads are declarative. Trusted code compiles a `WorkloadPlan` into one fixed generic k6 script. The Investigator does not author a script. Operation ids and mix weights in the script come only from the validated plan. |
| D9 | Side-effect classification is core policy. This build loads `read_safe` operations only. |
| D10 | Telemetry never requires a particular database. The universal tier is always on. Dependency adapters are added one at a time. |
| D11 | Experiment kinds are a legal set filtered by capability, preconditions and budget. They are not a fixed sequence. The one pipeline stage before the agent is `baseline`. |
| D12 | Predictions are `(readout, comparator, magnitude, against)`. `PredictionEvaluator` marks each `confirmed`, `refuted` or `inconclusive`. |
| D13 | Signature hypotheses in the Investigator prompt are sources of ideas, not a checklist and not a gate. Confidence requires a confirmed discriminating prediction (§12.2). |
| D14 | Confidence is a pure function of six booleans `S, M, X, K, R, V` (§12.2). `V` is false in this build, so confidence is at most 0.85. |
| D15 | The Investigator has seven tools (§11.3). That list is the only one. |
| D16 | The agent runtime is Pydantic AI. Harness `TieredCompaction` is adopted only if context grows long. Versions are pinned. The Investigator does not get a shell, a filesystem tool or a coder tool. |
| D17 | neatlogs wraps the agent. Entire is the code-graph provider and, separately, the partner checkpoint integration. The Investigator does not depend on checkpoints. |
| D18 | Acceptance is fixtures with sealed oracles, hidden-cause cases, one git-history case, and held-out repos (§18). |

---

## 3. Architecture

### 3.1 Shape

```text
user repo ──► intake ──► loadline core
                         lifecycle · ledger · SandboxPolicy · TargetGuard
                         ExperimentPolicy · budgets · prediction evaluator · report
                              │            │              │                │
                         RuntimeAdapter  WorkloadAdapter  Observability   CodeIntel
                         compose         http + smoke     universal       Entire graph
                         dockerfile      k6 generator     cgroup/host     ripgrep
                                                      postgres, then mysql, mongo, redis
```

One in-app agent: `Investigator` (§11). It calls the seven tools. It cannot run a shell, open a network connection or write files.

### 3.2 Lifecycle

```text
intake → plan_env → boot → discover_ops → smoke → calibrate → baseline
       → investigate → report → teardown
   any stage → blocked(code) → report(partial) → teardown
   investigate → investigation_incomplete(reason) → report(from ledger) → teardown
```

`plan_env` is deterministic. `baseline` is one ramp of the full mix at `--fast` timing (5 s warm-up, 15 s measure). It does not branch. `teardown` always runs. `investigate` starts only with a healthy environment, at least one smoke-passed operation, and a completed calibration. Otherwise the run ends in a named blocker.

### 3.3 Ownership

| Concern | Code | Agent |
|---------|------|-------|
| Measurement | load steps, metrics, verdicts, the bracket, the baseline ramp | which experiment to request |
| Limits | rate, VU, time, token and call budgets; isolation; egress; secrets | nothing |
| Legality | which kinds, parameters and operations are admissible | choosing among the legal ones |
| Acceptance | thresholds, confidence, severity, ranking | nothing |
| Report numbers | every figure | nothing |
| Hypotheses | storing them, scoring predictions | proposing, refining, rejecting |
| Code | search, graph and read tools | what to read and how to interpret it |
| Environment | validating and executing the launch plan, health, teardown | nothing |

### 3.4 Repository layout

```text
loadline/
  core/            lifecycle, ledger, evidence, policy, budgets, capability registry
  adapters/
    runtime/       compose.py dockerfile.py catalog/
    workload/      http_openapi.py http_tests.py
    generator/     k6/
    observability/ universal/ postgres.py mysql.py mongo.py redis.py
    codeintel/     entire.py ripgrep.py
  agents/          investigator.py investigator_prompt.md tools/
  report/          model.py render.py lint.py
  cli.py
  constants.py
tests/
  unit/ adapters/ sandbox/ e2e/ canaries/
  fixtures/        agent-visible apps
  oracles/         sealed yaml, never copied into a run
```

`loadline/` contains no fixture names, ports, route names or flaw identifiers (R2).

---

## 4. Core data model

Types are Pydantic models with `schema_version`, serialised as JSON in the run directory.

### 4.1 Facts

```text
Fact { value, confidence: 0..1, provenance: Provenance[], adapter_id }
Provenance { kind: static_code | config | api_spec | test_suite | docs | runtime_observation
                   | llm_inference | user_supplied,
             ref: file:line | command+exit | evidence_id, observed_at }
```

An `llm_inference` fact may drive a smoke call. It cannot support a finding until a `runtime_observation` or `static_code` fact agrees. `user_supplied` outranks inference and is labelled as such. CI configuration is `config` evidence. Loadline reads it and does not execute it.

### 4.2 `RepoProfile`

```text
RepoProfile {
  root, vcs: {sha, dirty}, size,
  languages[Fact], build_systems[Fact], frameworks[Fact], entrypoints[Fact],
  services[ServiceCandidate], dependencies[DependencyCandidate],
  interfaces[InterfaceCandidate], data[DataSources], tests[TestSuite],
  deploy[DeploySources], external_refs[ExternalRef],
  ci_evidence[Fact], architecture_mismatch[Fact]
}
```

### 4.3 `CapabilityReport`

```text
CapabilityReport {
  runtime: Capability, workload: {protocol: Capability},
  observability: {source_kind: Capability}, codeintel: {language: Capability},
  blockers: Blocker[], attempts: AttemptLog[]
}
Capability { level: ready | degraded | needs_input | unsupported, adapter_id, reasons[], missing[] }
Blocker { code, summary, evidence[], user_can_provide[], unblocks[] }
```

### 4.4 `LaunchPlan`

```text
LaunchPlan {
  services: Service[], network: NetworkSpec, data: DataPlan, health: HealthSpec[],
  provenance: Provenance[], proposed_by: adapter_id
}
Service { name, role: app | dependency | tool,
          source: repo_compose | dockerfile | catalog_image,
          image|build|command, env, resources: {cpu, mem, pids}, health, depends_on }
```

Ports in a plan are container-side names for the internal network. They are not published on the host.

### 4.5 Workloads

```text
OperationDescriptor {
  id, protocol, service, selector: {method, path},
  handler: {path, line_range} | None,
  params: ParamSpec[], auth: AuthRequirement,
  side_effect: read_safe | read_suspect | write_reversible | write_external | destructive | unknown,
  provenance: Provenance[],
  smoke: {status: untested | passed | failed, evidence_id}
}
WorkloadPlan {
  id, hash, mix: [{op, weight, params_source}],
  shape: {model: open, rate, duration, warmup},
  control_probe: OperationId | None,
  slo: {p95_ms, err_rate, source: user | goal | derived},
  safeguards: {allow_writes: false, egress: denied}
}
```

### 4.6 Experiments, hypotheses, findings

```text
ExperimentSpec { id, kind, params, hypothesis_id?, predictions: Prediction[], cost_estimate, preconditions }
Prediction { readout, comparator: gt|lt|ge|le|within|changes_by|unchanged, magnitude, against: experiment_id|baseline }
ExperimentResult { id, spec_hash, status, steps[], readouts{name: value+unit+n}, evidence_ids[], validity,
                   deltas_vs_baseline, deltas_vs_previous }
Hypothesis { id, claim, mechanism_label, scope, predictions[], competing_with[],
             status: proposed | testing | supported | refuted | inconclusive | abandoned, evidence_ids[] }
Finding { id, component, symptom, workload_ref, observed_facts[], hypotheses[], locations[],
          mechanism, alternatives_considered[], confirming_experiment, remediation, confidence, severity, evidence_ids[] }
Evidence { id, kind, provenance, blob_ref, sha256, family }
```

`mechanism_label` is free text. The prompt's signatures are CPU-bound, blocking or pool-bound, dependency-bound, per-item I/O, contention, memory pressure, and cold-start. Anything else is `other:<name>`. A hypothesis is `supported` only when at least one discriminating prediction is `confirmed`.

### 4.7 Run directory

```text
runs/<run_id>/
  run.json profile.json capabilities.json launch_plan.json launch_plan.validated.json
  workload_plan.json ledger.jsonl evidence/<id>.* waves/<exp>/
  report.md report.json
```

`ledger.jsonl` is the source of truth for the run. Report numbers are recomputed from `waves/` on every render. `--resume` replays the ledger.

---

## 5. Adapters

### 5.1 Contract

```python
class AdapterManifest(BaseModel):
    id: str
    version: str
    family: Literal["runtime", "workload", "generator", "observability", "codeintel"]
    supports: list[str]
    requires_binaries: list[str]
    safety_class: Literal["pure", "reads_repo", "executes_in_sandbox", "touches_host"]

class Adapter(Protocol):
    def manifest(self) -> AdapterManifest: ...
    def applicability(self, profile: RepoProfile, env: Env | None) -> Applicability: ...
```

A conformance suite checks every adapter: applicability is pure, outputs match the schema, errors are typed.

### 5.2 Families

```python
class RuntimeAdapter(Adapter, Protocol):
    def propose(self, profile) -> LaunchPlan | NeedsInput | Unsupported: ...
    def start(self, plan: ValidatedLaunchPlan, sandbox: Sandbox) -> Env: ...
    def health(self, env) -> HealthReport: ...
    def inspect(self, env) -> list[ServiceState]: ...
    def restart(self, env, service) -> None: ...
    def interventions(self, env) -> list[InterventionCapability]: ...
    def apply_intervention(self, env, spec) -> Revert: ...
    def stop(self, env) -> CleanupReport: ...

class WorkloadAdapter(Adapter, Protocol):
    def discover(self, profile, env, codeintel) -> list[OperationDescriptor]: ...
    def harvest_params(self, env, ops) -> ParamPools: ...
    def smoke(self, env, op) -> SmokeResult: ...
    def compile(self, plan: WorkloadPlan) -> GeneratorJob: ...

class GeneratorAdapter(Adapter, Protocol):
    def ceiling(self, placement) -> GeneratorCeiling: ...
    def run(self, job: GeneratorJob, window) -> RawResults: ...
    def parse(self, raw) -> StepMeasurements: ...

class ObservabilityAdapter(Adapter, Protocol):
    def discover(self, profile, env) -> list[TelemetrySource]: ...
    def start(self, source, window) -> Collector: ...
    def stop(self, collector) -> list[MetricSeries]: ...

class CodeIntelAdapter(Adapter, Protocol):
    def index(self, root) -> IndexStatus: ...
    def search(self, query, mode: Literal["literal", "semantic"]) -> list[Hit]: ...
    def graph(self, op: Literal["def", "neighbors", "impact"], symbol) -> GraphResult: ...
    def read(self, path, start, end) -> Snippet: ...
```

### 5.3 EntireGraphProvider

At startup, record whether `entire` is installed, its version, and the JSON from `entire graph capabilities --json`. Flags come from that JSON and from `entire graph help` / `<cmd> --help` on the installed binary. The ranked-search command in current upstream docs is `entire graph query`. If the installed binary exposes `query`, use it. If it exposes only `search`, use that and record `command_alias: search`. Do not send a flag the installed help does not list.

The Investigator uses `query` (or the recorded alias), `def`, `neighbors` and `impact`. `explain` is optional. `snapshot`, `symbols` and `edges` are for development diagnostics only. `edges` output is NDJSON, one record per line, not one JSON document. `diff`, `commit` and `checkpoint` are not Investigator tools. `verify` is never run.

Interactive queries read the working tree. Bulk exports such as `edges` default to committed HEAD. If `git status` shows uncommitted changes and the installed command accepts `--worktree`, pass it. Graph locations and `read_file` ranges must refer to the same tree. If `--worktree` is missing and the tree is dirty, code intelligence is `degraded` and the report says the graph may not match the working tree.

`HANDLES_ROUTE` is used only when `capabilities --json` lists it. The spike runs it on the corpus and records, per language, whether an operation maps to a handler. A mapping that the spike did not confirm is not treated as a handler location. Core does not special-case a framework's route table.

Arguments are built by one tested function, with a timeout and an output cap. Results become locations, snippets, relationship types, coverage and warnings. A missing symbol is a warning, not an invented symbol. An empty result is not evidence that a call or a dependency is absent.

`search_code` is the ranked Entire query plus a ripgrep literal search. `code_graph` dispatches to `def`, `neighbors` or `impact`, and to `HANDLES_ROUTE` when that relation is confirmed for the language. `read_file` is a line range with a secret denylist. A graph hit does not satisfy the "code was read" check; only `read_file` does. If Entire is missing, the language is unsupported, or the graph is partial, ripgrep and `read_file` still work and `codeintel` is `degraded`, which caps `K`.

Order for locating a handler:

1. The live OpenAPI document from the booted service, fetched by the probe container. That is a runtime fact. File specs, tests and graph hits stay labelled with their own provenance.
2. Handler location from `HANDLES_ROUTE` when the spike confirmed it for this language. Otherwise ripgrep for the method and path, then `read_file`.
3. `def`, `neighbors` and `impact` from that handler. Do not put a raw graph dump on the board.
4. `read_file` on the ranges that a finding will cite.
5. A mechanism is a cause only after a discriminating prediction is confirmed on a measurement. Suspicious code is a hypothesis.

### 5.4 Stack knowledge as data

The service catalogue is data: dependency kind and engine map to an image, a health command and an env contract (`adapters/runtime/catalog/`). SQL stats queries for MySQL and MariaDB are catalogue data. Adding an engine is a catalogue entry plus a test, not a core change.

### 5.5 Capability levels

| Level | Meaning |
|-------|---------|
| `ready` | Applicable, prerequisites present |
| `degraded` | Usable with a named loss, printed, and findings that depend on it are capped |
| `needs_input` | Only the user can supply what is missing |
| `unsupported` | No adapter applies |

"Loadline runs any repository" is not a claim. Coverage is published in `docs/COVERAGE.md` from manifests and canary results.

### 5.6 How a capability is resolved

1. The strongest evidence first: a compose file, then a Dockerfile.
2. Other adapters of the same family, by applicability score.
3. If a blocker remains that only the user can clear, write it with `user_can_provide`.
4. Stop with that blocker and the attempt log. Exit 9 (needs input) or 10 (blocked).

Loadline does not substitute another project or a canned workload. It does not run a planning model to repair boot.

---

## 6. Intake

Deterministic and read-only. No installs, no builds, no execution of CI commands. Output: `profile.json`, `capabilities.json`.

| Aspect | Evidence |
|--------|----------|
| Languages and build systems | extensions, manifests, lockfiles, toolchain files |
| Frameworks | dependency manifests and imports |
| Entry points | Dockerfile `CMD`/`ENTRYPOINT`, compose `command`, package scripts, Makefile targets, `main` modules |
| Services | compose files, multiple Dockerfiles, workspaces |
| Dependencies | compose services, env-var contracts, client libraries, config files, migration tools |
| Interfaces | OpenAPI/Swagger, request tests, route hits from code intelligence |
| Data | migrations, seeds, fixtures, dumps |
| Tests | test manifests, request-level tests, Postman/Bruno/HTTP/HAR files |
| CI | workflow files, as evidence: `services:`, image names, env var names, test command names. Never executed. |
| External refs | URL, host and credential scan (§7.6) |
| Architecture | image platform versus host. Emulation is recorded and labelled. |

Contradictions are kept. `loadline analyze` prints the capability report. Discovery accuracy is measured on the corpus (§18.3).

Questions are asked only when `Blocker.user_can_provide` is non-empty. On a TTY, prompt with the evidence. Otherwise write `needs_input.json` and exit 9. `--answers FILE` supplies the answer.

---

## 7. Runtime and sandbox

### 7.1 Isolation

Executing a repository executes its build scripts, installers, entrypoints and migrations. Protected assets: host files, host secrets, other repositories, the user's network, the model-provider key, and git history.

Every run uses hardened Docker: rootless Docker or Podman where available, user-namespace remap, `cap_drop ALL` plus a minimal allow-list, `no-new-privileges`, default seccomp, read-only rootfs when possible, pid/memory/cpu limits, no devices, no host mounts, no `docker.sock`, an internal network with egress denied. `doctor` checks each control and the report lists the ones that could not be applied.

If gVisor (`runsc`) is installed, the run detects it, prints it, and records it. There is no flag to select an isolation tier.

The report says which controls were applied and that Docker is not a complete boundary against malicious code. Loadline does not write "sandboxed" or "safe" without that statement. This build runs the user's own repository.

### 7.2 Build

The build context is the target repository. Loadline's run directory is `~/.local/share/loadline/runs/<id>` (or `LOADLINE_HOME`), never a `runs/` folder inside the target. `.git` and `.env*` are excluded from the context. A file in the target named `runs` is the target's file and is not Loadline state.

Runtime containers have no egress (§7.3). Image builds are not the same network. If the engine can build with `network=none` and the build succeeds, record `build_egress: none`. If the build needs a registry and succeeds only with the engine's default network, record `build_egress: unrestricted`. That fact is a limitation. It is not evidence about runtime egress, and it is not a hole in the run network.

### 7.3 Run

- One network per run, created by Loadline, `internal: true`, no default route. Every application container, catalogue dependency, the probe, and k6 is attached to that network and to no other. Compose's default network is not used. Service aliases resolve on this network. Nothing is published to the host. There is no `--allow-egress` flag. A repository that cannot boot without reaching the public internet ends `external_dependency` or `egress_not_enforced`. An internal network does not stop a process on the host from reaching a container. The report says Docker is not a complete boundary.
- The egress check runs inside the probe, inside the application container, and inside one dependency container when one exists. All three connects to an external address must fail before load starts. If the application container cannot be checked, the run stops `egress_not_enforced`. It does not assume the probe's result covers the app.
- The k6 image digest is `K6_IMAGE_DIGEST` in `constants.py`, written by spike S-GEN. S4 refuses to start if that constant is empty or is a floating tag. The script is the fixed generic script, passed on stdin, with operation ids and weights from the validated plan only. The container does not mount the repository, does not inherit host proxy variables, and does not follow a redirect to a different host. `TargetGuard` checks every URL before the container starts. Raw k6 output is collected from stdout and from a run-scoped volume labelled `loadline.run=<id>`, including after a kill. Calibration (§9.2) uses this same placement. Load testing is not described as ready until the S4 gate has passed.
- Resource limits are always set, on every container Loadline starts:

  | Container | CPU | Memory | PIDs |
  |-----------|-----|--------|------|
  | App service, repo declared a limit within the ceiling | the declared limit | the declared limit, or `DEFAULT_APP_MEM` if memory was omitted | `DEFAULT_PIDS` if omitted |
  | App service, no declared limit | `DEFAULT_APP_CPUS` (1) | `DEFAULT_APP_MEM` (512m) | `DEFAULT_PIDS` (256) |
  | Catalogue dependency | `DEFAULT_DEP_CPUS` (1) | `DEFAULT_DEP_MEM` (512m) | `DEFAULT_PIDS` |
  | k6 | `GEN_CPUS` (1) | `GEN_MEM` (512m) | `DEFAULT_PIDS` |
  | Probe | `PROBE_CPUS` (0.5) | `PROBE_MEM` (128m) | 64 |

  A declared CPU above `CPU_SAFETY_CEILING` (4) or memory above `MEM_SAFETY_CEILING` (2g) is lowered to the ceiling and recorded. Defaults are lab constraints, not a production capacity.
- `doctor` records the engine's CPU and memory (`docker info` / Podman equivalent). If that CPU count is below the host's logical cores, the limiter is `docker_engine` and every capacity figure is `measurement_ceiling_limited`. Saturation uses the engine's CPU count. A missing engine field is `not measured (field absent)`, not zero.
- A measurement taken while the engine or host is saturated cannot support an application-bottleneck claim. A measurement taken under emulation is labelled and is not treated as native hardware.
- Host environment variables are not forwarded. Dependency secrets are generated inside the sandbox for that run. Third-party API credentials are never invented: the run ends `needs_input`, or the dependency is recorded as unmet. Secrets are never written into a committed hints file, `launch_plan.json`, the boot JSON, or compose diagnostics. Those files store `[redacted]` for secret-shaped values. The real value exists only in the container environment.

### 7.4 `SandboxPolicy`

Applied to every `LaunchPlan`. Each rule allows, rewrites (recorded diff) or refuses (blocker).

| # | Rule | Action |
|---|------|--------|
| 1 | `privileged`, extra capabilities, host pid/ipc/network, devices, weakened security options | refuse |
| 2 | host bind mounts, `docker.sock`, `/proc`, `/sys`, `/` on a service | drop that service (record diff) when other services remain and it is not the app; otherwise refuse |
| 3 | published ports | rewrite to the internal network only |
| 4 | `host-gateway`, `network_mode`, external networks, or a service left on any network other than this run's internal network | refuse, or rewrite every service onto the run network and drop the others |
| 5 | egress | deny; connects from the probe, the app, and one dependency must fail before load starts |
| 6 | missing resource limits | add the defaults in §7.3 |
| 7 | env values | resolve compose `${VAR}` from the target repo `.env` only (never host env); generate run-scoped local secrets for placeholder dependency/app credentials and reuse the same value across services and embedded URLs; rewrite external URLs to `sandbox.invalid`; clear literal third-party secrets (record diff, do not invent). Disk artifacts store `[redacted]`, not the value |

The original and the validated plan are both stored. The diff is printed. Runtime adapters accept only a `ValidatedLaunchPlan`.

### 7.5 Runtime adapters

| Adapter | When | Behaviour |
|---------|------|-----------|
| `compose` | the repo has a compose file | use it after policy; honour profiles; add the generator; reuse its dependencies |
| `dockerfile` | a Dockerfile and no compose file | build the image; provision dependencies from the catalogue; wire env contracts |

`analyze --boot --json` returns one document, the same one as `tech_doc.md` §16.1: `status`, `blocker`, `attempts`, `config_schema`, `capabilities`, `launch_plan`, `boot`.

Readiness is shared by the compose and dockerfile adapters. The budget walks the app service and its transitive `depends_on` closure (list or map keys; conditions are not used for timing). Each healthcheck contributes `start_period + (interval + timeout) × retries`, with defaults `0`, `5s`, `5s`, and `3`. A service with no healthcheck contributes 15s. The wait is `min(180, max(30, max(per service) + 15s))`. A dockerfile-only boot uses 60s under that same cap. The probe polls every 2s on the run network, addressing the compose service name. Non-2xx responses and connection errors stay inside the window.

A missed deadline is `health_timeout`. `blocker.summary` is multi-line: the first line is the health URL, budget, elapsed time, and last probe, then `compose ps` or `docker ps` and logs for the app and each direct dependency. `blocker.evidence` holds the same bundle as structured fields. The run directory gets `attempts.json` when boot is blocked.

Transient `compose up` failures (image pull and network flakes) retry up to 3 times on the same plan, with a 5s backoff, and each try is recorded in `attempts[]`. `BOOT_MAX_ATTEMPTS` (5) is the ceiling for those boot retries, not a health-poll count. Unset variables, compose config errors, Dockerfile build errors (`build_failed`), and policy refusals are deterministic and are not retried. Compose merge and override files are not applied; Loadline boots the single discovered compose file.

### 7.6 `TargetGuard`

Every URL, host or credential in the repository becomes an `ExternalRef`: `in_sandbox`, `local_dev`, or `external`.

- The generator may address only services created for this run, identified by the run label. `TargetGuard` checks every target when the plan is compiled.
- `external` refs are never contacted. The operation is excluded as `external_dependency`.
- There is no mode that accepts a user-supplied target URL.

### 7.7 Dependencies and data

The service catalogue maps a dependency kind and engine to an image, a health check and an env contract. An engine that is not in the catalogue is `unsupported_dependency` with the engine name.

Data comes from commands the repository itself declares: a compose one-shot, an entrypoint, or a package script whose argv is copied from that file and run inside the sandbox. Loadline does not invent a migration. If that command fails, the blocker is `boot_failed`. After a healthy boot, dependency adapters measure dataset size. If the size is zero and every smoke-passing read needed harvested ids, those operations are excluded and the blocker is `data_missing` when none remain. The size is measured. It is not invented.

Loadline does not replace an external HTTP API with a stub in this build. The affected operations are excluded and named.

### 7.8 Teardown

Every object is labelled `loadline.run=<run_id>`. Teardown always runs, including after failure, timeout, and SIGINT. There is no `--keep-env`. Teardown removes containers, networks, volumes, and temp directories that carry that label, and nothing else. `loadline doctor --cleanup` removes leftovers by the same label. Acceptance tests require zero labelled objects after a normal run, a failed run, and an interrupted run.

### 7.9 Interventions

Adapters may declare: `set_resource_limit(service, cpu|mem)`, `scale_replicas(service, n)` when Compose supports it, `set_env` for keys discovered as knobs (workers, pools, timeouts), `inject_dependency_latency(edge, ms)`, `restart(service)`. Each one is reverted and the service is health-checked afterwards.

---

## 8. Workloads

### 8.1 Sources

`WorkloadAdapter.discover` owns this list. The Investigator does not add operations. Disagreements are kept.

1. The running service's own spec endpoint, fetched by the probe. Provenance `runtime_observation`. This is the authority for live HTTP routes.
2. OpenAPI or Swagger files in the repository. Provenance `api_spec`. These are not live until the probe sees the same operation.
3. Existing tests and collections (request tests, Postman, Bruno, HTTP, HAR, README `curl` examples).
4. Code: Entire plus `read_file`, including a handler location when one was found. This locates source. It does not invent a route the live spec did not list.
5. LLM proposals for parameters or bodies, and for operations only when sources 1–4 produced nothing. Provenance stays `llm_inference` until smoke passes.

An operation with no live spec and no file spec is included only when a test or a code hit names the method and path, and smoke then passes. If smoke leaves zero `read_safe` operations, the blocker is `no_working_operation`.

### 8.2 Parameters and auth

Parameter values come from specs, examples and tests, then from read-safe responses, then from LLM proposals that passed smoke. Auth discovered from the spec or from tests is used inside the sandbox (a seeded user, or a token the user supplied). Tokens are redacted. Credentials Loadline cannot see become `needs_input`.

### 8.3 Side effects

Classification decides what is excluded. Only `read_safe` operations are loaded.

| Class | Meaning | This build |
|-------|---------|------------|
| `read_safe` | read semantics and no write or external call on the handler path | loaded after smoke |
| `read_suspect` | read-shaped, with evidence of writes or external calls | excluded |
| `write_reversible`, `write_external`, `destructive` | mutations | excluded |
| `unknown` | not enough evidence | excluded |

The report lists excluded operations and the evidence for the class.

### 8.4 Compilation and smoke

`WorkloadPlan` compiles to one fixed generic k6 script. `TargetGuard` runs at compile time. The plan hash is stored.

Each admitted operation is called once before any load. Failures are excluded with a reason. Zero passing operations is `no_working_operation`.

---

## 9. Load engine

### 9.1 Rules

Open-model constant arrival rate, so a slow target cannot hide its knee by slowing the client. One k6 process per step. One run holds the generator lock.

### 9.2 Calibration

1. **Generator ceiling.** k6 against a null target. `RATE_CAP = 0.7 × ceiling`.
2. **Quiet baseline.** A low-rate step per admitted operation and for the mix. This yields `baseline_p95` and the derived SLO (§9.5).
3. **Control probe.** The cheapest smoke-passed read, at `PROBE_RPS` during every step. If the cheapest read has idle p95 above `PROBE_MAX_BASELINE_MS`, there is no probe and probe-based conclusions are marked unavailable.

### 9.3 Verdicts

First match wins:

1. `invalid(target_unhealthy)` — unhealthy, restart, OOM or crash loop.
2. `invalid(generator_failed)` — generator crash or parse failure.
3. `invalid(measurement_gap)` — required telemetry covered less than 90% of the window.
4. `invalid(host_saturated)` — host CPU above 0.90, memory pressure, or port/fd exhaustion.
5. `generator_limited` — dropped iterations above 0.5%, VU cap hit, or generator CPU above 0.85 of its limit.
6. `fail` — p95 above the SLO, error rate above the SLO, or the probe stalled (probe p95 above max(3× its baseline, 100 ms)). A percentile is computed only when the measure window has at least `MIN_SAMPLES` (200) successful responses. Below that, the percentile is `not measured (samples=N)` and the step is `invalid(measurement_gap)` if the verdict needed it. p99 is omitted unless the window has at least `MIN_SAMPLES_P99` (1000) successful responses. p50 and p95 may be reported at `MIN_SAMPLES`.
7. `invalid(achieved_below_target)` — achieved rate under 0.95 of target without a drop signal.
8. `pass`.

Only `pass` and `fail` move the bracket. Any other status is retried once, then ends the search.

### 9.4 Ladder, bracket, confirm

- **Ladder:** start at 2 req/s, double each step, stop at the first non-pass or at `RATE_CAP`. Default step timing is 10 s warm-up and 30 s measure. `--fast`, which the baseline uses, is 5 s and 15 s.
- **Bracket:** `lo` is the highest passing rate with every lower rate passing. `hi` is the lowest failure above `lo`. Statuses: `bracketed`, `below_ladder`, `above_ladder`, `generator_limited`, `invalid(code)`.
- **Refine:** geometric mean of `lo` and `hi` until `hi/lo ≤ 1.15` or four refinements. Only when the agent asks.
- **Confirm:** repeat `lo` once. A failed confirm lowers `lo` and marks it unconfirmed. Only when the agent asks.
- **VU sizing:** `ceil(rate × baseline_p95_s × 1.5) + 2`, with max `4 ×` that value.

### 9.5 SLO

User `--slo`, or `clamp(5 × baseline_p95_ms, 200, 2000)` for p95 and 1% for errors. The report prints the SLO and its source. A derived SLO is a measurement convention, not a business requirement.

### 9.6 Host

`doctor` fails below 4 logical cores unless `--allow-low-cores` is set, in which case every capacity figure is `measurement_ceiling_limited`. The generator is limited and pinned separately from the services when the OS allows it.

### 9.7 Budgets

About 40% of the run's wall-clock budget is reserved for the agent (`AGENT_WALL_FRACTION`). Image build and boot have their own budget. Refine and confirm run only when the agent requests them.

---

## 10. Observability

### 10.1 Series

`MetricSeries{name, unit, entity, kind, points, coverage}`. `coverage` is the fraction of the window that was sampled.

### 10.2 Always on

| Source | Signals |
|--------|---------|
| k6 | throughput, p50/p95/p99, errors, dropped iterations, VU use, per operation |
| cgroups or engine stats | CPU usage, memory, OOM, pids, restarts. Throttle only if the spike S-CGROUP recorded the field this engine actually returns (`cpu.stat` `throttled_usec`, or Docker `throttling_data`). A missing field is `not measured (field absent)`. It is not zero, and it cannot by itself support `environment_limit`. |
| Host | CPU, memory pressure, load, ephemeral ports, file descriptors, disk |
| Generator | CPU, memory, scheduling delay |
| Logs | line rate, error counts, repeated lines, redacted |

`u_cpu = usage / limit`, `throttle_ratio`, and `implied_concurrency = throughput × latency` are reported per service.

### 10.3 Dependency adapters, in order

Postgres first (`pg_stat_*`). Then MySQL/MariaDB (queries stored as catalogue data). Then MongoDB. Then Redis. A missing adapter sets that source to `degraded`. The run continues.

Counters are snapshotted per step and reported as deltas.

### 10.4 `limit_attribution`

For every step that is not `pass`, code emits a ranked attribution from: `generator`, `host`, `environment_limit` (throttle, OOM, pids, fds), `application_cpu`, `application_blocking` (low CPU, rising implied concurrency, probe stall), `dependency`, `measurement_failure`, `unknown`. Each entry cites evidence. This is an input to the agent, not a finding. `host` or an emulated environment cannot be turned into an application-bottleneck claim.

---

## 11. Investigator

The system prompt is `agents/investigator_prompt.md` and no other file. The run substitutes `{{BOARD}}` and does not append instructions. A test checks that this file contains the hard rules and names no fixture. Repository text and tool output are data (§17).

### 11.1 What the agent is given

A board, regenerated from the profile and the ledger before every turn. Summaries and evidence ids only. Never source text, raw graph dumps or unbounded logs.

1. **Repository profile.** Language, framework, entrypoints, services, dependencies, operation-to-handler links, coverage gaps.
2. **Measurement evidence.** Baseline workload, rates, bracket, sample size, per-operation observations, failed steps, `limit_attribution`.
3. **Code-intelligence coverage.** Whether Entire is available, which relationships it returned, which operations have a handler location.
4. **Investigation state.** Budgets left, legal experiment kinds, hypotheses, prediction results, the strongest unresolved question.

### 11.2 Experiment catalogue

The catalogue is the set of legal moves this turn: kind × capability × preconditions × budget. The agent chooses. `ExperimentPolicy.admit` allows or rejects. A kind exists only when a capability can run it.

| Kind | Purpose | Requires |
|------|---------|----------|
| `rate_step`, `rate_ladder`, `refine`, `confirm` | capacity (§9) | generator and ≥1 operation |
| `isolate` | one operation against the mix | ≥2 operations |
| `mix_ablation` | add or remove operations | ≥2 operations |
| `param_scale` | vary a declared parameter (page size, payload, cardinality) | a parameter that scales |
| `resource_perturb` | change a CPU/memory limit or a discovered knob; `scale_replicas` when Compose allows it | the intervention |
| `dependency_perturb` | add latency on a dependency edge | latency injection |
| `warm_cold` | restart, then measure cold against warm | restart |

`inspect_runtime` is a tool, not a load step. New kinds need a typed spec, preconditions, a cost and named readouts. There is no fixed investigation sequence beyond the baseline stage in §3.2.

### 11.3 Tools

| # | Tool | Returns |
|---|------|---------|
| 1 | `search_code` | Entire ranked hits plus ripgrep literal hits |
| 2 | `code_graph` | `def`, `neighbors` or `impact` |
| 3 | `read_file` | a line range; secrets removed; the range is recorded |
| 4 | `inspect_runtime` | redacted logs, service state, discovered knobs, available interventions |
| 5 | `declare_hypothesis` | the stored hypothesis, or a rejection if its readouts cannot be produced |
| 6 | `run_experiment` | admission or a rejection with the legal alternatives; on completion, named readouts with units and sample size, plus deltas versus baseline and versus the previous experiment |
| 7 | `record_finding` | acceptance, or a validation error; code sets confidence and severity |

Code writes the report. The agent's final structured output supplies the prose. The agent has no shell, no network tool and no write tool.

### 11.4 Predictions

1. `declare_hypothesis` carries a claim, a mechanism label, a scope, at least one competing hypothesis, and predictions. Each prediction names a readout the catalogue can produce (`p95_ms`, `throughput_rps`, `err_rate`, `cpu_util`, `throttle_ratio`, `implied_concurrency`, `dep_latency`, `dep_calls_per_req`, and deltas of those).
2. `run_experiment` runs only if `admit` allows it and the budget remains.
3. `PredictionEvaluator` scores each prediction using only steps whose verdict is `pass` or `fail`, with at least `MIN_SAMPLES` successful responses. Otherwise the score is `inconclusive`.
   - Two readings are within noise when the relative difference is under `NOISE_REL` (0.10) or, for a latency readout, the absolute difference is under `NOISE_ABS_MS` (15).
   - `unchanged` is `confirmed` when the delta is within noise, and `refuted` when it is outside noise.
   - `changes_by` (and `gt` / `lt` / `ge` / `le`) is `confirmed` only when the delta is outside noise and in the predicted direction. A delta inside noise is `inconclusive`, not a refutation.
   - `supported` requires a confirmed prediction that would have come out differently under a registered competitor.
4. The agent then reads code, refines, or drops the hypothesis. Refutations stay in the report.

### 11.5 Admission

A request is admitted when the kind exists, preconditions hold, the operations passed smoke, the rate is within the cap, the budget can pay for it, the intervention reverts, and the side-effect class is allowed.

Before raising the rate on an operation past the first ladder step, a `read_file` of its handler must exist when code intelligence can locate one. Otherwise the gate is waived, `code_unavailable` is recorded, and `K` stays false.

The same experiment without a new hypothesis or a changed parameter is rejected. After two inconclusive results the next load step waits for a code read or a different question. Rejections are ledger events and include the legal moves.

### 11.6 Context

`history_processors` replace old turns with ledger references. Tool returns are capped (§14.5) and carry evidence ids. `UsageLimits` caps requests and tokens. An `output_validator` rejects prose whose digits are not in `ReportModel`. The model used for acceptance tests is pinned. Harness `TieredCompaction` is wired only if measured turns exceed the context budget.

### 11.7 Stopping

The agent stops when it has findings whose discriminating predictions were confirmed, or the bracket is `above_ladder` and nothing else failed, or the budget is nearly gone. It says what it could not test. If it stalls, errors or hits the budget, the run state is `investigation_incomplete(reason)`. Code writes the report from the ledger. Nothing else continues the investigation.

---

## 12. Findings, confidence, ranking

### 12.1 Validator

`record_finding` requires a component, a symptom with a workload and cited valid steps, a mechanism, evidence ids, observed facts separate from hypotheses, alternatives and what happened to them, the confirming experiment, and remediation text. A `file:line` range is required when the handler language was readable; the range must have been returned by `read_file` this run. Otherwise the finding is `unlocated` and `K` is false.

### 12.2 Confidence

- **S** — the symptom is on at least one valid step with an SLO breach or a capacity limit in this scope.
- **M** — a discriminating prediction was confirmed, or two independent evidence families agree and none contradicts them.
- **X** — generator, host, environment and measurement artefacts are excluded by `limit_attribution`, and every competing hypothesis is refuted or explicitly deferred.
- **K** — the cited range was read this run and is the handler or reachable from it.
- **R** — the effect appears in at least two independent valid steps, and those readings are within noise (§11.4).
- **V** — a fix was verified by measurement. Always false in this build.

```python
def confidence(S, M, X, K, R, V):
    if not S: return 0.0
    c = 0.40
    if M: c = 0.50
    if M and X: c = 0.65
    if M and X and K: c = 0.85
    if not R: c = min(c, 0.65)
    if V and M and X and K and R: c = 0.95
    return c
```

An exhaustive 64-combination test locks this function. Bands: High ≥ 0.80, Medium 0.60–0.79, Low < 0.60. Causal verbs in prose require at least 0.65, which this build can reach only with `S`, `M`, `X` and `R`.

### 12.3 Severity and rank

`critical`: limits capacity at `hi` on an operation with mix weight ≥ 0.2. `high`: SLO breach on a weighted operation. `medium`: degradation with the SLO still met, or a secondary operation. `low`: a measured inefficiency with no SLO impact. `info`: a ruled-out hypothesis.

`rank = severity_weight × confidence × impact`. `impact` is the measured relative change from the confirming experiment, scaled by mix weight. If that change was not measured, impact is the observed share of the SLO gap. Unmeasured gains are labelled `[ESTIMATE]` and rank below measured ones.

---

## 13. Remediation

Findings include recommended remediation text and a code location when one was read. This build does not patch the repository, run a fix agent, or verify a before/after performance change. `V` is false. Confidence does not exceed 0.85.

---

## 14. Report

### 14.1 Files

`report.md`, `report.json` (`schema_version`), `ledger.jsonl`.

### 14.2 Sections

1. **Verdict** and the trace link.
2. **What was run:** capabilities, isolation controls, services, dependencies, data size, SLO and its source, CPU lab constraint, emulation if any, budgets used.
3. **Coverage:** operations discovered, admitted and excluded, with reasons.
4. **Capacity:** bracket per operation and for the mix. A missing knee is "not measured (reason)".
5. **Resources and dependencies** at `lo` and `hi`. Missing sources are listed.
6. **Experiment log:** hypotheses, predictions, code-scored outcomes.
7. **Projected scale.** CPU-seconds per request, throughput when a CPU or memory limit changed, a replica test if one was run, calls per request against a scaled parameter. Each line states its assumptions and a range. Three points show whether the response looked linear. They are not a curve fit and not a production capacity. The section is labelled projected.
8. **Ranked findings.**
9. **Ruled out.**
10. **Limitations.** Required, and never empty.
11. **Reproduce:** SHA, versions, plan hashes, commands.
12. **Partner artefacts.**

Sections 4 through 9 tag each statement **measured**, **projected** or **hypothesis**.

### 14.3 Wording lint

Every number has a unit and an evidence id. Causal verbs require confidence ≥ 0.65. Unmeasured gains are prefixed `[ESTIMATE]`. Digits in agent prose must appear in `ReportModel`. Limitations states the isolation controls, any emulation, the SLO source, and that model providers receive repository excerpts.

### 14.4 Evidence

`report.json` numbers are recomputed from `waves/` and compared to the ledger. A mismatch fails the render.

### 14.5 Tool caps

A tool return is at most 6,000 characters of JSON plus evidence ids. Logs and series are summarised.

### 14.6 Live UI

Rich output, or plain text with `--no-live`. The live view shows phase, environment, the current experiment, the bracket and hypothesis status.

---

## 15. Partners

Partners do not change the architecture above.

| Partner | Role |
|---------|------|
| neatlogs | `neatlogs.init(workflow_name="loadline", tags=["neatHack", f"run_id:{id}", f"agent_profile:{v0\|v1}", f"fast:{bool}"])`. Tags are a list of strings. `neatlogs.wrap(Agent)` under one workflow trace. Tool attributes: `loadline.result_id`, `loadline.ok`, `loadline.experiment_kind`, `loadline.adapter`. |
| Entire | `EntireGraphProvider` (§5.3). Checkpoints and history are a separate partner artefact. The Investigator does not call them. |
| cfo.ai | A human-written business plan, exported as PDF. Not an agent tool. |

"Agent improved" means two live neatlogs traces of two Loadline revisions on the same target SHA. Deadlines are in `hackathon.md`.

---

## 16. CLI

### 16.1 Commands

```text
loadline run      [--repo PATH=.] [--goal TEXT] [--slo p95=MS,err=PCT]
                  [--fast] [--budget-minutes N]
                  [--answers FILE] [--non-interactive] [--resume RUN_DIR]
                  [--no-live] [--allow-low-cores]
loadline analyze  [PATH] [--boot] [--json]
loadline report   RUN_DIR
loadline doctor   [--cleanup] [--check-model]
loadline skills   status|install|uninstall ...   # S9, after the boot JSON contract is tested
loadline dev      step|ramp|experiment ...
```

`analyze` prints discovery and the capability report. `--boot` also boots and smoke-tests, and does not apply load. `--json` is the interface the skill reads. The document is:

```text
status: booted | blocked | needs_input
blocker: { code, summary, retryable: bool, security: bool,
           user_can_provide: string[],
           remediation: [{ kind: hint, field: <schema key>, reason }],
           evidence?: { health_url, budget_s, elapsed_s, ps, logs, last_probe } }
attempts: [{ n, signature, result, unblock, detail? }]
config_schema: loadline-hints/1
capabilities: CapabilityReport
launch_plan: ValidatedLaunchPlan | null
boot: { health, services } | null
```

This is the only boot JSON. `capabilities`, `launch_plan` and `boot` are null when the run did not get that far. The skill reads `status`, `blocker`, `attempts` and `config_schema`. A remediation `field` is one of the keys in §16.3. If Loadline has no safe hint, `remediation` is empty and `retryable` is false. The skill does not invent a field. `security: true` is never retryable.

`blocker.summary` may be several lines. On a TTY the CLI prints the full text to stderr. `health_timeout` carries `blocker.evidence` (ps, logs, last probe). A blocked boot also writes `attempts.json` in the run directory. Transient compose-up retries are classified pull/network flakes only (§7.5); a repeated signature is not itself a reason to stop or to retry.

`doctor` checks the runtime and prints hard blocker, degraded, optional-absent, or ready. It does not install packages and it does not call a model. `doctor --check-model` is the only doctor mode that sends a provider request, and it warns that the provider may bill. `doctor` looks for the pinned k6 image, not for a k6 binary on `PATH`. Missing `NEATLOGS_API_KEY` is an optional-absent partner check, not a missing model credential.

`dev` is for spikes and tests. It is not the product surface.

Run states: `completed`, `blocked(code)`, `investigation_incomplete(reason)`.

### 16.2 Exit codes

| Code | Meaning |
|------|---------|
| 0 | Report written, including an honest "no bottleneck" conclusion |
| 1 | Internal error |
| 2 | `doctor` or preflight failed |
| 3 | `investigation_incomplete`, or no valid measurement |
| 4 | Policy violation |
| 5 | User abort |
| 6 | Budget exhausted |
| 7 | Health never reached |
| 8 | Resume invalid |
| 9 | Needs input (`needs_input.json`) |
| 10 | Blocked (`capabilities.json` and the attempt log) |

A report is written whenever any evidence exists.

### 16.3 `.loadline.yaml` (`loadline-hints/1`)

Optional. Unknown keys are a validation error. Values are `user_supplied`. They do not override `SandboxPolicy`, `TargetGuard`, resource limits, published-port rules or egress. The file must not contain secrets, URLs of systems outside this run, or image-pull credentials.

| Key | Type | Meaning |
|-----|------|---------|
| `schema_version` | `1` | required when the file exists |
| `compose_file` | repo-relative path | which compose file |
| `dockerfile` | repo-relative path | which Dockerfile |
| `compose_profile` | string | compose profile to enable |
| `app_service` | string | which compose service is the HTTP app |
| `container_port` | int | port inside the run network, not a host publish |
| `health_path` | path starting with `/` | HTTP path the probe calls |
| `command` | string | replaces the container command; still passes policy |
| `env` | map of name → literal | non-secret values only |
| `exclude_operations` | list of operation ids | dropped before smoke |
| `slo.p95_ms` | int | user SLO |
| `slo.err_rate` | float | user SLO |

The CLI rejects any other key, including keys that would change privilege, mounts, networks, published ports or egress. The skill may set a key only when the boot JSON lists that key in `remediation`. It makes the smallest edit, keeps unrelated keys, and does not commit secrets. After the initial boot attempt it may retry twice (three boot attempts total), and only when `retryable` is true and the file or the user's input changed. It does not edit application source to force a boot.

`skills/loadline-run/SKILL.md` is written in S9, after S8 is green and this schema and the boot JSON have tests. Its body, and no other, is:

1. When to use the skill.
2. Prerequisites: Docker or Podman, git, a model API key. Entire is provisioned by Loadline. k6 is an image digest, not a PATH binary.
3. Run `loadline analyze --boot --json`. Read `status`, `blocker`, `attempts`, `config_schema`.
4. If `blocked` and `retryable` and `security` is false, apply only a `remediation.field` that exists in the table above, then retry. Stop after two corrections.
5. If `needs_input` or `security` is true, stop and show the blocker. Do not invent a secret. Do not weaken policy.
6. If `booted`, run `loadline run` and show the report path. Do not edit application source, Compose, or Dockerfiles.

The skill is built after this schema and the boot JSON are tested. It is instructions for a coding agent, not a security boundary. This build does not include an MCP server or a marketplace plugin. Install paths and the `loadline skills` commands are in `implementation.md` (S9) and `delivery.md`.

### 16.4 Environment

`loadline run` and `loadline analyze --boot` check `LOADLINE_MODEL` and the credential that provider requires before any Docker call. If either is missing it exits 2 and names the variable. It does not switch model or provider, and it does not start a scripted investigator. The supported path is an API key (`openai:<model-id>` with `OPENAI_API_KEY`, or `anthropic:<model-id>` with `ANTHROPIC_API_KEY`). Other provider shapes are unused until a spike records that tool calls, structured output and budgets work on the pinned library. The host coding agent's login is not reused.

`NEATLOGS_API_KEY` is independent. The provider sees repository excerpts returned by tools. Limitations says so. Token counts are recorded only when the provider reports them. A dollar figure is printed only when a versioned price table for that model exists; otherwise the report says cost was not available. Secrets are removed before they enter a prompt and are never printed.

---

## 17. Safety

- Repository text, logs and responses are data. They are length-limited, delimited, stripped of control characters, and never treated as instructions.
- Read tools deny `.env*`, key files, `*.pem` and cloud credential paths. Tool output, logs and reports are redacted.
- The run network has no egress. A probe confirms that before load. Model-provider traffic comes from the Loadline process, not from the sandbox.
- Git metadata is read-only. Loadline does not commit, merge or push.
- Wall-clock budgets, per-step kill, the generator lock, the host-saturation guard and label cleanup always apply.
- The report states the isolation controls, whether the CPU limit was a lab default, and whether the run was emulated.

---

## 18. Acceptance

### 18.1 Fixtures

| Fixture | Role |
|---------|------|
| `fx-pyhttp-pg` | Python HTTP + PostgreSQL |
| `fx-node-mongo` | Node HTTP + MongoDB |
| `fx-polyglot-mesh` | at least three services, at least two languages |
| `fx-neg-needs-secret` | ends `needs_input` |
| `fx-neg-hostile-compose` | policy refuses or rewrites |
| `fx-neg-prod-urls` | those URLs are not load targets |

Flaws and locations live only in `tests/oracles/<fx>.sealed.yaml`. That file is not copied into the run and is not read by `loadline/`.

Hidden-cause cases, authored so the obvious hint is wrong: a misleading code comment, a run that is generator-bound, and a case with two competing explanations. One git-history case: check out the parent of a real performance-fix commit; the fix commit is the sealed oracle.

### 18.2 Per fixture

Discovery, launch-plan validity, the policy diff, health, workload generation, smoke, load, verdicts, evidence, diagnosis (the oracle checks mechanism, location and confidence, not the agent's path), teardown.

### 18.3 Corpus

Four or five pinned repositories, split into tuning and held-out. At least three held-out repos are never used to tune. Each ends in a report or a named blocker: never a crash, a fabricated success, or a substitute project.

### 18.4 No leakage

`test_no_fixture_leakage` scans `loadline/` for fixture names, paths, route strings and flaw ids. The Investigator prompt and any skill text must not name fixtures.

### 18.5 Layers

1. Units: verdicts, bracket, evaluator, the 64 confidence combinations, `admit`, the side-effect classifier, `TargetGuard`, `SandboxPolicy` against at least 20 hostile plans, redaction, ledger recompute.
2. Adapter conformance and corpus discovery. `analyze` executes no repository code.
3. Sandbox: egress probe fails, teardown, concurrent runs, hostile plans.
4. Fixture end-to-end with the live model. A driver in the test suite may script experiments to test the report renderer. That driver is not product code.
5. Held-out repos.
6. Hidden-cause cases, the git-history case, and the no-leakage test.
7. Partner evidence: neatlogs traces, an Entire checkpoint from a live run, the cfo.ai PDF.

### 18.6 Done

`loadline run` on each fixture and on at least three held-out repos ends in a report or a named blocker, with no crash and no fabricated number. Teardown leaves zero labelled objects after normal, failed and interrupted runs. The no-leakage test and the hidden-cause cases pass. A host-saturated or emulated measurement is never used as an application bottleneck.

---

## 19. Build order

`implementation.md` is the sequence: spikes, core, discovery, sandbox, workloads, observability, experiment engine and report, Investigator, evaluation, then the boot-repair skill. Each step ends with a run against real repositories.

When something has to be cut: extra database adapters, then report polish, then the skill. Do not cut the sandbox policy, the target guard, the egress probe, teardown, named blockers, Limitations, evidence recompute, the no-leakage test, the wording lint, or the partner evidence.

---

## Appendix A — Blockers

`not_a_service`, `no_entrypoint`, `no_interface`, `build_failed`, `boot_failed`, `health_timeout`, `missing_secret`, `unsupported_dependency`, `external_dependency`, `egress_not_enforced`, `policy_refused`, `needs_input`, `no_working_operation`, `data_missing`, `auth_unresolved`, `generator_unavailable`, `host_too_small`, `telemetry_incomplete`, `budget_exhausted`, `resume_mismatch`, `adapter_error`. Each one carries evidence and `user_can_provide`.

## Appendix B — Ledger events

`run_started`, `profile_written`, `capabilities_written`, `plan_proposed`, `plan_validated`, `boot_attempt`, `env_ready`, `egress_probe`, `ops_discovered`, `smoke`, `calibrated`, `baseline_finished`, `hypothesis`, `experiment_admitted`, `experiment_rejected`, `experiment_started`, `experiment_finished`, `prediction_scored`, `limit_attribution`, `code_read`, `finding`, `investigation_incomplete`, `verdict`, `report_written`, `teardown`, `error`.

Every event has `ts`, `run_id`, `seq` and `evidence_ids`.

## Appendix C — `loadline/constants.py`

| Name | Value |
|------|-------|
| `PROBE_RPS` | 2 |
| `PROBE_RATIO` | 3.0 |
| `PROBE_MIN_MS` | 100 |
| `PROBE_MAX_BASELINE_MS` | 50 |
| `HOST_SATURATED` | 0.90 |
| `GEN_CPU_SATURATED` | 0.85 |
| `DROP_MAX` | 0.005 |
| `ACHIEVED_MIN` | 0.95 |
| `COVERAGE_MIN` | 0.90 |
| `LADDER_START` | 2 |
| `LADDER_FACTOR` | 2 |
| `WARMUP_S` / `MEASURE_S` | 10 / 30 |
| `--fast` warm-up / measure | 5 / 15, used by `baseline` |
| `BRACKET_TARGET` | 1.15 |
| `BRACKET_MAX_REFINE` | 4 |
| `RATE_CAP_FRACTION` | 0.7 |
| `BOOT_MAX_ATTEMPTS` | 5; ceiling for boot retries. Transient `compose up` uses 3 attempts on the same plan. Health wait uses the readiness budget, not this counter |
| `DEFAULT_APP_CPUS` | 1, only when the repo sets no CPU limit |
| `DEFAULT_APP_MEM` | 512m, when the repo sets no memory limit |
| `DEFAULT_DEP_CPUS` | 1 |
| `DEFAULT_DEP_MEM` | 512m |
| `DEFAULT_PIDS` | 256 |
| `GEN_CPUS` | 1 |
| `GEN_MEM` | 512m |
| `PROBE_CPUS` | 0.5 |
| `PROBE_MEM` | 128m |
| `CPU_SAFETY_CEILING` | 4 |
| `MEM_SAFETY_CEILING` | 2g |
| `K6_IMAGE_DIGEST` | empty until spike S-GEN writes a `sha256:` digest. S4 refuses a tag or an empty value |
| `PROBE_IMAGE_DIGEST` | same rule, written by spike S-DOCKER |
| `MIN_SAMPLES` | 200 successful responses before p50 or p95 is reported |
| `MIN_SAMPLES_P99` | 1000, or p99 is omitted |
| `NOISE_REL` | 0.10 |
| `NOISE_ABS_MS` | 15 |
| `AGENT_WALL_FRACTION` | 0.40 |
| `SLO_ERR_DEFAULT` | 0.01 |
| `SLO_P95_CLAMP` | 200, 2000 |
| `SLO_P95_BASELINE_MULT` | 5 |
| default `--budget-minutes` | 45 |
| tool-call ceiling | 60 |

Printed in `run.json`. They are policy defaults, not claims about any application.

## Appendix D — Retired

These are not part of the product: a mandatory FastAPI and PostgreSQL stack; one HTTP service; a preseeded database; an allowlist of paths; GET-only as a substitute for side-effect classification; planted flaws as product logic; a fixed investigation script; mandatory `pg_stat_statements`; an in-app environment planner; eleven agent tools; a scripted investigation policy; publishing ports to the host; isolation-tier flags. Old copies are in `.archive-pre-reset/` and are not authoritative.
