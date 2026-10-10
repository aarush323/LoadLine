# 04 — Core architecture: HLD and LLD

Module boundaries for `tech_doc.md` §3–§5. Interface signatures are defined only in `tech_doc.md` §5.2.

## 1. Components

```text
cli.py ─► orchestrator (core/run.py) ─► phases (core/phases/*.py)
                    │
                    ├─ ledger + evidence store      (core/ledger.py, core/evidence.py)
                    ├─ policy engine                (core/policy/{target_guard,sandbox,experiment}.py)
                    ├─ budgets/watchdogs            (core/budget.py)
                    ├─ capability registry          (core/registry.py)  ← adapters (entry points + built-ins)
                    ├─ experiment engine            (core/experiments/*.py, evaluator.py)
                    ├─ confidence/findings          (core/findings.py)
                    └─ report model/render/lint     (report/*)
agents/: investigator.py only — tools are thin wrappers over core services
```

The orchestrator owns all side effects. Agents and adapters receive narrow service objects and cannot import each other.

## 2. Process model

One Python process (the orchestrator + agents + adapter calls). External processes: container engine CLI/API, generator (container or subprocess), profilers/collectors (inside sandbox), `entire`, `git`. Async I/O for collectors; step execution is sequential per host (generator lock). Every subprocess has a timeout, a process-group kill, and output size caps.

## 3. State machine

```text
INTAKE ─► DISCOVERED ─► PLANNED ─► BOOTED ─► OPS_READY ─► CALIBRATED ─► INVESTIGATING ─► CONCLUDED ─► (FIXING ─► VERIFIED)? ─► REPORTED ─► TORN_DOWN
   any ──error/blocker──► BLOCKED ─► REPORTED (partial) ─► TORN_DOWN
```

Transitions are ledger events; `--resume` replays events to the last consistent state and re-enters (only idempotent phases re-execute; completed experiments are never re-run; interrupted steps are marked `invalid(generator_failed)` and retried per policy). Resume requires the same repo SHA/dirty hash and plan hashes (`resume_mismatch` otherwise, exit 8).

## 4. Ledger and evidence

`ledger.jsonl` append-only, one event per line (types: `tech_doc.md` App. B). Events are immutable; corrections are new events. Evidence blobs live under `evidence/` and `waves/`, addressed by id and sha256; events reference ids. Report numbers are recomputed from raw per-step files at render time; ledger summary values are compared and a mismatch aborts rendering. The ledger is flushed per event (fsync batching ≤1s) so a crash loses at most one event.

## 5. Envelopes

All tools and adapter calls return:

```python
class ToolResult(BaseModel):
    ok: bool
    code: str | None            # blocker/error code (tech_doc App. A)
    data: dict | None           # capped (tech_doc §14.5)
    evidence_ids: list[str]
    warnings: list[str]
    advice: str | None          # legal moves / what to do next (deterministic text)
```

No raw exceptions reach an agent; adapters raise typed `AdapterError(code, detail)`.

## 6. Registry and plugins

Adapters register with a manifest. Discovery: built-in modules + Python entry points group `loadline.adapters`. `loadline doctor` lists adapters, binaries required, conformance status. An adapter failing conformance is disabled, loudly. The registry computes capability levels from `applicability` scores and required binaries.

## 7. Policy engine

- `TargetGuard.check(job)`: every request target ∈ services created for this run (container labels), no literal external hosts, no host loopback; runs at compile and again at execute.
- `SandboxPolicy.validate(plan, trust, tier) → ValidatedLaunchPlan | Refusal` (rules: `tech_doc.md` §7.4).
- `ExperimentPolicy.admit(spec, state) → Admit | Reject(reason, legal_moves)`: legality, budgets, read gate, autopilot guard (`tech_doc.md` §11.5).
- All policies are pure functions of data + state: unit-testable without containers or models.

## 8. Concurrency and locks

Host-wide generator lock (`runs/.generator.lock`, stale-lock recovery by pid+start time). Multiple Loadline runs may *discover* concurrently; only one may *generate load*. Distinct run networks and labels allow safe parallel boots in tests.

## 9. Budgets and watchdogs

`Budget` tracks wall minutes, load seconds, steps, tool calls, model requests/tokens, boot attempts. Every `admit`/tool call debits. Exhaustion ⇒ `budget_exhausted` event; the orchestrator moves to `conclude` with whatever evidence exists. A watchdog thread enforces absolute wall time and kills generator/collectors.

## 10. Config and constants

`loadline/constants.py` (values: `tech_doc.md` App. C); effective values dumped into `run.json`. No behaviour constant is read from environment except documented flags.

## 11. Directory and import rules

`core` imports nothing from `adapters` or `agents`. `adapters` import `core.types` only. `agents` import `core.services`. A lint test enforces the dependency direction and bans importing fixtures from `loadline/`.

## 12. Extensibility checks (what "add a stack" means)

| Add | Touch | Don't touch |
|-----|-------|-------------|
| a web framework | route pack YAML + golden test | core, agents |
| a database | catalogue YAML (+ observability adapter, conformance test) | core, agents |
| a language ecosystem | `fixverify` ecosystem adapter + codeintel pack | core |
| a protocol | workload adapter + generator support + conformance | core |
| an experiment kind | experiment module (spec, preconditions, cost, readouts) + doc | agents' prompts beyond the catalogue render |
