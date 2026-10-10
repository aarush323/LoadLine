# Loadline design docs — topic map (v3)

Names, numbers and scope are defined in [`../tech_doc.md`](../tech_doc.md). These files explain mechanics. They do not add scope.

> The reference application demonstrates that Loadline works. It must never be the reason Loadline works.

## Decisions (full log in `tech_doc.md` §2)

| Topic | Decision |
|-------|----------|
| Product | discover → boot → workloads → calibrate → baseline → investigate → report |
| Architecture | Core plus runtime, workload, generator, observability and code-intelligence adapters |
| Support | Per-capability levels. A missing adapter degrades that capability. Named blockers. No fabricated results. |
| Safety | Hardened Docker, `SandboxPolicy`, `TargetGuard`, egress denied and probed, no published ports. Docker is not a complete boundary. |
| Load | k6, open-model constant arrival rate, calibration, verdicts, bracket |
| Telemetry | Universal tier always. Dependency adapters: Postgres, then MySQL/MariaDB, MongoDB, Redis. |
| Agent | One Investigator, seven tools. No in-app environment planner. |
| Reasoning | Hypotheses with structured predictions. Code scores them. `investigation_incomplete` if the agent stops. |
| Confidence | `S, M, X, K, R, V` in `tech_doc.md` §12. `V` is false. |
| Remediation | Text in the finding. No patch and no before/after verification. |
| Code intelligence | Entire Graph plus ripgrep. Entire is optional. |
| Partners | neatlogs, Entire checkpoints (separate from the Investigator), cfo.ai PDF |
| Acceptance | Fixtures, hidden-cause cases, one git-history case, 4–5 repos, no-leakage test |

## Doc map

| Doc | Topic | Primary `tech_doc.md` sections |
|-----|-------|-------------------------------|
| `01-repo-analysis.md` | Intake, capability discovery, questions to the user | §4, §5, §6 |
| `02-load-model.md` | Workload model, generator contract, capacity engine | §8, §9 |
| `03-environment.md` | Sandbox, runtime adapters, dependencies | §7 |
| `04-hld-lld.md` | Core architecture, interfaces, run lifecycle, ledger | §3, §4, §5 |
| `05-agent-reasoning.md` | Investigator, experiments, predictions, board | §10, §11 |
| `06-diagnosis-skills.md` | Knowledge packs (hints, not detectors) | §11, §12 |
| `07-reporting.md` | Report model, finding cards, lint, live UI | §12, §14 |
| `08-fix-agent.md` | Remediation text only (`tech_doc.md` §13) | §13 |
| `09-robustness.md` | Failure modes, exit codes, watchdogs, host validity | §9.6, §16 |
| `10-review.md` | v3 adversarial review: contradictions resolved, residual risks, anti-overfit audit | §0, §18 |
| `11-harness-review.md` | Harness and tracing facts (Pydantic AI, neatlogs) | §15 |
| `12-oss-bom.md` | Tools and dependencies by layer | §5, R9 |
| `13-entire-across-product.md` | Entire as an adapter and as partner evidence | §15 |
| `OPEN-QUESTIONS.md` | Decisions only the humans can make | — |

The board in `tech_doc.md` §11.1 replaces a `get_profile` tool. Old copies live in `.archive-pre-reset/` and are not part of the contract.

## Rules for editing these docs

1. No fixture names, flaw ids, ports, paths or datasets appear as examples of *product* behaviour. Illustrative examples use placeholders (`<service>`, `<operation>`).
2. Any new stack knowledge goes in a data pack, not in prose that implies core logic.
3. If a number must change, change `tech_doc.md` App. C first.
