# Remaining product gaps (S0–S9 vs `loadline/`)

Compared `implementation.md` (S0–S9), `tech_doc.md`, `docs/implementation-status.md`, and the current `loadline/` tree. **Read-only audit** (2026-10-10).

**Pinned FastAPI product run:** `uv run loadline run --repo integration/targets/full-stack-fastapi-template --fast` → exit **10**, `policy_refused` (`service proxy has a host bind mount` / Traefik `docker.sock`). No `report.md`, investigator not invoked. That refusal matches `integration/DESIRED-OUTPUT.md` and `SandboxPolicy` rule 3; it is **not** a missing-product bug and **not** grounds to weaken the sandbox.

---

## Gap register

| Plan | Owner file(s) | Missing behavior | FastAPI run: gap vs policy? |
|------|----------------|------------------|-----------------------------|
| **S3 / tech_doc §3.2, §16.2** | `loadline/run_pipeline.py`, `loadline/adapters/runtime/compose_boot.py`, `loadline/core/report_render.py` | Lifecycle promises `blocked(code) → report(partial) → teardown` and “a report is written whenever any evidence exists.” On `policy_refused`, `allocate_run_dir` runs but nothing is persisted (`capabilities.json`, `ledger.jsonl`, `attempts`, `report.md`). `run_loadline` returns immediately with stderr JSON only. | **Policy correctly refused** boot. Missing partial report is a **separate gap** (did not cause exit 10). |
| **S3 / reference §15, DESIRED-OUTPUT §1** | `loadline/discovery/intake.py`, `loadline/adapters/runtime/compose_boot.py` | Compose adapter loads **one** YAML file (`load_compose`); it does not merge `compose.override.yml` / `compose.deploy.yml` the way `docker compose` does locally. Discovery only **records** multiple root compose files as a contradiction. | **Policy correctly refused** before merge would matter. If proxy were absent, unmerged override would still block a faithful boot (e.g. `mailpit`, dev `command`, bind mounts on `backend` / `playwright`). |
| **S3 / tech_doc §16.3** | `loadline/adapters/runtime/compose_boot.py`, `loadline/discovery/workload.py`, `loadline/adapters/generator/k6_runner.py` | Hint keys are parsed in `loadline/core/hints.py` but **not applied** in runtime: `compose_profile`, `command`, `env`, `exclude_operations`, `slo.p95_ms`, `slo.err_rate` (only `compose_file`, `dockerfile`, `app_service`, `container_port`, `health_path` are used). | **Policy correctly refused** first. Hints would not unlock stock `compose.yml` without a **separate**, policy-valid compose file (allowed by schema; pin is not patched in integration). |
| **S3** | `loadline/adapters/runtime/compose_boot.py` (`_health_url`) | Probe health URL defaults to `/health` unless hinted. Pinned FastAPI backend health is `/api/v1/utils/health-check/` (compose `healthcheck`). No inference from compose `healthcheck.test`. | **Policy correctly refused** today. Would **block healthy boot** on a policy-valid FastAPI plan that omitted `health_path` in `.loadline.yaml`. |
| **S1 / tech_doc §16.2, delivery** | `loadline/boot.py`, `loadline/run_pipeline.py` (no writer) | Non-interactive `needs_input` should write `needs_input.json` and exit **9**; only JSON on stderr exists today. | **Not** the FastAPI outcome (`policy_refused`, exit 10). |
| **S0** | `docs/spikes.md` (record), `loadline/investigator/run.py` (gate) | **S-AUTH** spike not run/recorded (`implementation-status.md`). Plan: do not start S7 without it. | **Not** FastAPI boot (auth preflight passed; boot blocked by policy). Blocks **live investigator verification**, not sandbox boot. |
| **S4 / tech_doc §9** | `loadline/run_pipeline.py`, `loadline/core/bracket.py` | Product `run` runs calibration + **baseline only**; ladder/bracket/refine/confirm are implemented in `core/` but not driven on the main path (only via investigator `run_experiment`, see below). | **Not reached** (no boot). Would limit investigation after a healthy boot. |
| **S6–S7 / tech_doc §11.3–11.4** | `loadline/run_pipeline.py` (`_measurement_runner_factory`) | Investigator `run_experiment` calls a runner that **ignores** `kind` and `params` and always runs the same short k6 shape. Kinds like `isolate`, `mix_ablation`, `refine`, `warm_cold`, etc. do not change measurement. | **Not reached** on FastAPI. **Blocks a plan-complete investigation** after healthy boot. |
| **S7 / tech_doc §11.4** | `loadline/investigator/tools.py` | `PredictionEvaluator` / `score_prediction` exist in `loadline/core/` but are **not** invoked from `declare_hypothesis` or `run_experiment` tool returns (no `prediction_scored` ledger events from tools). | **Not reached** on FastAPI. **Blocks discriminating hypotheses** per contract after healthy boot. |
| **S7 / tech_doc §11.6** | `loadline/investigator/agent_factory.py` | No agent `output_validator` tying prose digits to `ReportModel` (report render lints digits; agent final string is unchecked). | **Not reached** on FastAPI. |
| **S7 / tech_doc §11.5** | `loadline/core/experiment_policy.py` | Admission does not enforce “handler `read_file` before rate past first ladder step” or duplicate-experiment / inconclusive-streak rules described in §11.5. | **Not reached** on FastAPI. |
| **S7** | `loadline/investigator/operation_proposer.py` | Live operation proposer is a **no-op** (returns unchanged list). Acceptable if `WorkloadAdapter.discover` always supplies ops; not a boot blocker. | **Not** FastAPI boot. |
| **S5** | `loadline/adapters/observability/` | MySQL/Mongo/Redis adapters deferred (plan: degraded). Postgres path exists. | **Not** boot blockers. |

---

## What still blocks a **healthy-boot investigation**

### On the pinned FastAPI template (default compose)

1. **Nothing in the table above caused exit 10.** Traefik `docker.sock` is an honest, security-marked `policy_refused`.
2. **There is no product bug that prevents investigation because boot never became healthy.** Reaching healthy boot on this pin without weakening policy requires a **policy-valid launch plan** (e.g. user-supplied `.loadline.yaml` + alternate compose path **outside** the pinned upstream file set, or a future adapter feature). That is **out of scope** for the unpinned clone per `integration/DESIRED-OUTPUT.md` §3—not a sandbox weakening.
3. If a policy-valid plan were supplied later, **health path** and **compose merge** gaps would likely block boot or smoke **before** investigator unless addressed (`compose_boot.py`, intake/merge).

### On repos that already boot (e.g. `tests/fixtures/fx-pyhttp-pg`)

These **do** block a plan-complete investigation after healthy boot:

| Gap | Owner |
|-----|--------|
| `run_experiment` does not implement experiment kinds (only generic k6) | `loadline/run_pipeline.py` |
| `PredictionEvaluator` not wired into investigator tools | `loadline/investigator/tools.py` |
| Bracket/ladder/refine not driven on `loadline run` (baseline-only load path) | `loadline/run_pipeline.py`, `loadline/core/bracket.py` |

Partial report on early `blocked` does **not** stop investigator when boot succeeds; it only affects blocked-run UX and §16.2 “report whenever evidence exists.”

---

## Explicitly not listed

- Style, test count, or “S8 green” claims vs held-out corpus runs.
- Weakening `SandboxPolicy`, allowing `docker.sock`, or patching `integration/targets/full-stack-fastapi-template/`.
- S0 **S-DOCKER** egress spike anomaly in `docs/spikes.md` (environment/engine), unless product `doctor` misreports egress readiness.
