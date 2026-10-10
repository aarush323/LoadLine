# 01 — Repository intake and capability discovery

Mechanics for `tech_doc.md` §4, §5 and §6. Discovery covers Docker/Compose HTTP repositories and does not execute CI commands.

## 1. Purpose

Turn an unfamiliar directory into a `RepoProfile` (what exists, with provenance) and a `CapabilityReport` (what Loadline can do with it) **without executing repository code**. Everything stack-specific is an adapter or data pack.

## 2. Pipeline

```text
walk (respect .gitignore, size caps, binary skip, vendor dirs)
  → manifest scanners (language/build/deps)        ┐
  → framework detectors (manifests and imports) │ each emits Facts with Provenance
  → entrypoint scanners                            │
  → topology scanners (compose/k8s/dockerfiles/workspaces)
  → dependency scanners (compose, env contracts, client libs, migrations)
  → interface scanners (specs, routes, consumers)  │
  → data/test/deploy scanners                      │
  → external-ref scanner (URLs/hosts/credentials)  ┘
  → merge into evidence graph → capability evaluation (adapters' applicability)
  → write profile.json + capabilities.json → print matrix
```

All scanners are pure functions of the file tree. A scanner may not read outside the repo, follow symlinks out of it, or run subprocesses other than git metadata queries.

## 3. Facts and merge rules

- A `Fact` = value + confidence + provenance list. Two scanners asserting the same value merge (confidence combines as `1 − Π(1 − cᵢ)`, capped 0.99 for static-only evidence).
- Contradictions (two entrypoints, two ports) are kept as alternatives, ranked; the runtime adapter chooses via applicability and, if needed, trial boots.
- `llm_inference` facts have confidence ≤0.5 and are excluded from any claim until a `runtime_observation` or `static_code` fact corroborates them.
- Confidence sources: manifest-declared (0.9), convention-only (0.5), README-only (0.4), CI-only (0.6), tests (0.7), runtime-observed (0.95).

## 4. What each scanner family looks for (examples, extensible by data)

| Family | Signals |
|--------|---------|
| Language/build | file extensions weighted by size excluding vendor; manifests and lockfiles; toolchain pins (`.python-version`, `.nvmrc`, `go.mod` toolchain, `.tool-versions`) |
| Framework | manifest dependencies; import names; config files (`application.yml`, `settings.py`, `next.config`, `routes.rb`) |
| Entrypoint | Dockerfile `CMD/ENTRYPOINT`; compose `command`; Procfile; package scripts; Makefile/justfile targets named like run/serve/start/dev; framework conventions; CI deploy/run steps; devcontainer `postStart` |
| Topology | compose services and `depends_on`; k8s Deployments/Services; workspaces/monorepo package graph; multiple Dockerfiles; skaffold/Tilt |
| Dependencies | compose images; env-var contracts (`DATABASE_URL`, `REDIS_HOST`, `MONGO_*`, `AMQP_*`, `KAFKA_*`, `ELASTIC*`, `S3_*`); client libraries in manifests; migration tools; ORM config; k8s StatefulSets |
| Interfaces | OpenAPI/Swagger, GraphQL SDL, `.proto`, AsyncAPI; route registrations (packs); WebSocket handlers; queue consumers; CLI-only (→ `no_interface`) |
| Data | migrations, seeds, fixtures, dumps, ORM models, schema SQL |
| Tests | test commands and frameworks; request-level tests; collections (Postman/Bruno/`.http`/HAR) |
| External refs | all URLs/hosts/IPs/credentials in config, env files, code constants; classified per `tech_doc.md` §7.6 |

## 5. Capability evaluation

For each adapter: `applicability(profile)` → score in 0..1 + evidence. The report lists, per family, the best adapter and the next alternatives with scores. `level` assignment:

- `ready` — applicable ≥0.6, binaries present, no missing inputs.
- `degraded` — applicable but a named loss (e.g., routes only by low-confidence convention).
- `needs_input` — applicable but a **blocking** requirement is only user-resolvable.
- `unsupported` — no adapter ≥0.2 after the fallback chain (`tech_doc.md` §5.6).

`AttemptLog` records adapters tried, scores and reasons; it is printed with any blocker.

## 6. Printed matrix (shape, placeholders only)

```text
Repository: <path>  sha <short>  languages: <lang list>
Services:   <name> (<framework>, <runtime>)  …
Dependencies: <engine/kind> … (source: compose|env|client lib)
Interfaces: http(<n> ops via openapi|routes|tests) · graphql · grpc · …
Capabilities
  runtime        ready      compose              (alternatives: dockerfile 0.7)
  workload/http  degraded   routes(pack:<id>)     missing: request bodies for <n> ops
  observability  ready      universal + <source adapters>
  codeintel      ready      entire + ripgrep
  fixverify      degraded   <ecosystem>           no test command found
Blockers: <none | code + what only you can provide>
Isolation tiers available: T0 ✔  T1 ✘  T2 ✘  T3 ✘   (third-party code requires ≥T1)
```

## 7. Questions to the user (only blockers)

A question is raised iff: (a) a `Blocker` exists with non-empty `user_can_provide`, and (b) a deterministic check shows nothing generated (secret generation, stub, dependency provisioning) can satisfy it. Interactive TTY → prompt with evidence; non-interactive → `needs_input.json`:

```json
{ "blockers": [ { "code": "missing_secret", "topic": "<ENV_NAME>",
    "why": "read at startup in <file:line>; no default; not generated",
    "options": ["provide a value", "stub the dependency", "exclude the service"] } ],
  "answer_with": "loadline run --answers answers.yaml" }
```

`answers.yaml` keys are blocker topics. Answers are `user_supplied` facts and are never echoed in reports (redacted).

## 8. `.loadline.yaml` (hints only; never required)

```yaml
services: { <name>: { entrypoint: "<cmd>", port: <n>, env: { KEY: "<placeholder>" } } }
auth:     { bootstrap: "<operation id or seed user hint>" }
slo:      { p95_ms: <n>, err_rate: <x> }
exclude:  [ "<operation id or path pattern>" ]
knobs:    [ { service: "<name>", env: "<KEY>", meaning: "worker count" } ]
```

Hints enter as `user_supplied` facts and pass through the same policy as everything else.

## 9. Measuring discovery quality (corpus)

- ≥12 pinned snapshots, varied languages/frameworks/stores, split **tuning (≥8)** / **held-out**; truth labels in `tests/corpus-truth/*.yaml` (never imported by `loadline/`).
- Metrics: stack accuracy, service/dependency precision and recall, entrypoint hit rate, route precision/recall per framework pack, false-runnable rate (claims `ready` but cannot boot).
- Regressions fail `make acceptance` on the tuning split; held-out numbers are reported only, never used to tune.

## 10. Non-goals

No dynamic analysis here, no package installs, no network. Runtime observation (OpenAPI served by the app, `/metrics` labels) is added later by boot/probe stages and merged as `runtime_observation` facts.
