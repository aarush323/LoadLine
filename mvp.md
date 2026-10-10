# Loadline — MVP

Short form of `tech_doc.md`. Build order: `implementation.md`. Change scope in `tech_doc.md` first, then update this file to match.

> **Product:** `loadline run` in any runnable repo: it boots it in isolation, load-tests it with k6, and an agent investigates bottlenecks. Output is an evidence-backed report, or a named blocker.

> The reference application demonstrates that Loadline works. It must never be the reason Loadline works.

## 1. The five things we build

1. **Point it at a repository.** One command; reuse its Docker/Compose config; discover stack, services, dependencies, HTTP operations.
2. **Run it in isolation.** Docker/Compose + `SandboxPolicy` + `TargetGuard`; `--internal` network egress denial, verified; limits always set; label teardown. Never claimed as a complete boundary.
3. **Generate load.** k6, open-model, declarative `WorkloadPlan`; operations merged from service spec, OpenAPI, tests, code, LLM proposals (smoke-tested; read-safe only).
4. **Investigate agentically.** Baseline ramp (code), then the Investigator (seven tools) forms hypotheses with structured predictions, runs experiments, reads code; code scores everything. No fallback policy: stall/budget ⇒ `investigation_incomplete`.
5. **Evidence-backed report.** Measured capacity, ranked findings with code locations, experiments, confidence, remediation; **[MEASURED] / [PROJECTED] / [HYPOTHESIS]** kept apart; mandatory Limitations. "No bottleneck found within the measured range" and "blocked: <reason>" are valid outcomes.

## 2. Deliverable checks

| # | Must be true | Verified by |
|---|--------------|-------------|
| 1 | `analyze` yields stack, services, deps, operations with provenance, launch plan; missing info ⇒ specific blocker; CI config is evidence only, never executed | corpus metrics |
| 2 | Policy refuses/rewrites hostile plans with a printed diff; CPU rule applied and recorded as lab constraint; zero labelled resources after normal/failed/interrupted runs | hostile-plan tests |
| 3 | Operations smoke-tested; only passing read-safe ones loaded; verdicts, bracket, SLO and its source printed | oracle tests |
| 4 | Seven tools; predictions scored by code; `supported` only via a confirmed discriminating prediction; no fixture/flaw identifiers in production code | no-leakage, hidden-cause evals |
| 5 | `report.md` + `report.json`; every number traceable; wording lint; Projected section labelled | lint, ledger recompute |

## 3. In scope

Docker + Compose · k6 · HTTP/REST · universal telemetry + Postgres adapter first (MySQL/MariaDB, MongoDB, Redis next) · Entire Graph via `EntireGraphProvider` + ripgrep · Pydantic AI Investigator (pinned) · neatlogs · Entire checkpoints (partner, separate) · cfo.ai plan (human PDF) · one portable `loadline-run` Agent Skill (after boot is reliable) · `analyze --boot --json`.

## 4. Not in this build

Fix & verify (ABBA) · in-app EnvPlanner · MCP server · per-host plugin packages · GraphQL/gRPC/WebSocket · buildpack/process/k8s runtimes · profilers · tree-sitter route-pack authoring · metamorphic mutator · 12-repo corpus (use 4–5) · LSP · `report.html` · USL fit · write workloads and snapshots · `data_scale`, `concurrency_step`, `profile_capture`, `soak_bounded`.

Not in `BRIEF.md` ⇒ ask first; park in `design/OPEN-QUESTIONS.md`.

## 5. Quality bar

No hard-coded endpoints, ports, paths, tables, counts, flaw locations or sequences · never fabricate ("not measured (reason)") · one code path per feature, no fallbacks · never target anything but this run's services · host-saturated or emulated measurements never support an application-bottleneck claim · do not claim every repo works.

## 6. Acceptance

- Fixtures with sealed oracles, hidden-cause cases, a git-history ground-truth case, ≥3 held-out repos, no-leakage test.
- Outcome per repo: report or named blocker; never a crash or fabricated number.
- Teardown leaves zero labelled resources in normal, failed and interrupted runs.

## 7. Demo

1. Live `loadline run` on an unfamiliar repo ending in a report or precise blocker.
2. Hypothesis → prediction → experiment → code-scored outcome → code-linked finding.
3. A real recovery beat (rejected experiment or invalid step) visible in neatlogs.
4. The skill resolving a boot blocker, if S9 lands.
5. Partner beats: neatlogs v0/v1 on the same SHA; Entire checkpoint; cfo.ai plan.

## 8. Judging alignment

Agent 30 · partners 25 · demo 20 · building in public 15 · usefulness 10. Logistics: `hackathon.md`.
