# Autonomous Load Engineer — superseded

**Status: superseded. Not authoritative.** This file was the original pre-build product spec (Locust-based, typed-tool, SQLite-state design). The 2026-10-10 product direction reset replaced it. The full original text is preserved, non-authoritative, in `.archive-pre-reset/`.

**Authoritative documents:** [`tech_doc.md`](./tech_doc.md) (contract) · [`mvp.md`](./mvp.md) · [`implementation.md`](./implementation.md) · [`design/`](./design/00-topics.md).

## Ideas absorbed into the v3 contract

| Original idea | Where it lives now |
|---------------|--------------------|
| Source-linked "Testability Manifest" with provenance | `RepoProfile` + `OperationDescriptor` with `Fact`/`Provenance` (`tech_doc.md` §4.1–§4.5) |
| Evidence types (static code, config, OpenAPI, tests, runtime observation, LLM inference, user-supplied) | `Provenance.kind`; `llm_inference` cannot support findings until corroborated |
| Typed, bounded workloads validated before traffic | declarative `WorkloadPlan`, `TargetGuard`, side-effect policy (`tech_doc.md` §8) |
| Deterministic validation, agent proposes | deterministic-code vs agent ownership split (`tech_doc.md` §3.3, R5) |
| Truthfulness: only report what was measured | R3, wording lint, evidence recompute (`tech_doc.md` §14) |
| Safety: authorised targets only, no production | R6 `TargetGuard`; sandbox-only targets; no attach mode in v1 |
| Fix-and-verify in an isolated worktree | `tech_doc.md` §13 |

## Ideas deliberately not carried over

Locust as the engine (k6 behind an adapter instead), SQLite run state (append-only ledger instead), attaching to an arbitrary running application (out of scope in v1), model-authored workload code.
