# 02 — Workload model, generator contract, capacity engine

Mechanics for `tech_doc.md` §8 and §9. HTTP, k6, read-safe operations, generator on the internal network. Constants: `tech_doc.md` Appendix C.

## 1. Why open model

For request/response protocols the engine offers load at a fixed arrival rate regardless of response time; a slow target therefore shows queueing and failure instead of silently lowering offered load. k6's `constant-arrival-rate` executor is the generator primitive (one process per step); `dropped_iterations` is the generator-limit signal. Closed-model (`concurrency_step`) is available for session-style journeys and labelled as such; it never produces an arrival-rate knee.

## 2. `WorkloadPlan` (JSON, declarative; the only thing compiled to the generator)

```json
{
  "id": "wp_…", "hash": "sha256:…",
  "mix": [ { "op": "<operation id>", "weight": 0.6, "params": { "source": "pool:<name>" } } ],
  "journeys": [ { "id": "j1", "steps": [ { "op": "<id>", "extract": { "<var>": "$.path" } },
                                         { "op": "<id>", "use": ["<var>"], "think_ms": 100 } ] } ],
  "shape": { "model": "open", "rate": 40, "warmup_s": 10, "measure_s": 30 },
  "control_probe": "<operation id or null>",
  "slo": { "p95_ms": 500, "err_rate": 0.01, "source": "derived|user|goal" },
  "safeguards": { "allow_writes": "none", "restore_between": false, "egress": "denied" },
  "targets": [ { "service": "<service name>", "base": "http://<service>:<port>" } ]
}
```

Rules: operations referenced must be smoke-passed; `targets` must be services of this run (`TargetGuard`); weights sum to 1; the plan hash covers everything except `shape.rate` so the same plan can be replayed at different rates.

## 3. Generator contract (`GeneratorAdapter`)

Input: `GeneratorJob` = plan JSON + resolved parameter pools + auth tokens (redacted in logs) + placement. Execution: **one fixed generic script per generator adapter** (k6: `runner.js`), reading the job, building requests from operation templates, no per-run script text. Output per step: `StepMeasurements`:

```json
{ "step_id": "…", "target_rps": 40, "achieved_rps": 39.6, "planned_iters": 1200, "dropped_iters": 0,
  "vus_max": 12, "vus_limit": 48,
  "latency_ms": { "p50": …, "p95": …, "p99": …, "n": … },
  "by_op": { "<op>": { "rps": …, "p95": …, "err_rate": …, "status": { "2xx": …, "4xx": …, "5xx": …, "timeout": … } } },
  "probe": { "p95": …, "n": … } | null,
  "generator": { "cpu": …, "mem": … },
  "errors": [ { "class": "timeout|conn|status|check", "n": … } ] }
```

Step export uses the generator's summary JSON. Warm-up samples are discarded by tag. If the generator's per-step summary cannot be obtained (spike S-GEN), fall back to one-step-per-process (already the design) — no fallback to a different measurement semantics.

Placement is the k6 container on the run's `--internal` network. The script arrives on stdin. Results come back on stdout and a labelled run volume. There is no host placement and no published port.

## 4. Calibration

1. **Generator ceiling:** k6 against a null responder on that same network. Ceiling = highest rate with zero drops and generator CPU < `GEN_CPU_SATURATED`. Cache key: host id + k6 image digest. `RATE_CAP = RATE_CAP_FRACTION × ceiling`.
2. **Quiet baseline:** each admitted operation at a low fixed rate (e.g., 1–2 req/s) for a short window, idle target; yields `baseline_p50/p95`, error rate and cost class (cheap/medium/heavy by baseline latency terciles). Operations with failing baselines are excluded.
3. **Control probe selection:** among admitted read-safe operations, choose the lowest baseline p95 with the fewest dependencies in its handler call path (when code intel is available); else the cheapest by baseline. If the service exposes no read-safe operation cheap enough (baseline p95 > 50 ms at idle) the probe is *absent*, and `probe_stall` is unavailable (reported).
4. **SLO default** (if no `--slo`): `p95 = clamp(5 × baseline_p95(mix), 200, 2000) ms`, `err = 1%`, `source: derived`.

## 5. Step execution and verdicts

Sequence: set up (snapshot restore if writes) → health check → start collectors → warm-up → measure → stop collectors → health check → parse → verdict. Verdict order and thresholds: `tech_doc.md` §9.3 (single definition). Retries: an invalid or generator-limited step is repeated at most once; the second outcome stands.

`limit_attribution` (`tech_doc.md` §10.4) is computed for every non-pass step and stored with the step.

## 6. Ladder and bracket (worked example, placeholders)

```text
rates: 2 → 4 → 8 → 16 → 32 → 64 → 128(fail)
lo = 64 (pass, all lower pass), hi = 128 (fail)
refine: gm(64,128)=90 pass → lo=90; gm(90,128)=107 fail → hi=107; ratio 1.19 → refine again: 98 pass → lo=98 (ratio 1.09 ≤ 1.15)
confirm lo=98 → pass → "max sustainable ≈ 98 req/s on <mix>, confirmed"
```

Statuses: `bracketed`, `below_ladder` (first step fails: "cannot sustain even the lowest rate under the SLO"), `above_ladder` (cap passes: "capacity exceeds the host-measurable ceiling `RATE_CAP`"), `generator_limited`, `invalid(code)`. A null `lo` renders as "not measured (reason)".

## 7. VU sizing (Little's law)

`pre = ceil(rate × baseline_p95_s × 1.5) + 2`; `max = 4 × pre`, bounded by policy `VU_CAP` (derived from generator ceiling measurements). Reaching `max` marks the step `generator_limited`. For closed model, user count is the independent variable.

## 8. Parameter pools, state, auth

- **Pools** are named lists with provenance (spec examples, test requests, harvested responses, LLM proposals that passed smoke). A pool must be non-empty for any operation using it; otherwise that operation is excluded (`no_params`).
- **Harvest:** read-safe list/search operations are called at low rate; ids, tokens and enumerations extracted by JSONPath/regex defined by the operation's response schema (spec) or inferred from the first responses (marked `inferred`). Harvest is itself recorded as evidence.
- **Journeys** compile to fixed generic step interpreters (extract/use/think). No code strings from the agent.
- **Auth:** discovered scheme → bootstrap procedure (seeded user, signup op classified `write_reversible`, `needs_input`). Tokens are refreshed by the generic script if the scheme declares expiry (spec) or on 401 once.

## 9. Side-effect classification (decision table)

Inputs: method/RPC semantics, spec annotations (`x-` extensions, proto `idempotency_level`), handler call path (writes to dependencies, external clients, queue publishes, filesystem), name/path hints (weak), smoke observations (e.g., state changed between identical calls).

| Evidence | Class |
|----------|-------|
| read semantics ∧ no write/external in call path ∧ identical responses on repeat | `read_safe` |
| read semantics ∧ any write/external/non-determinism hint | `read_suspect` |
| write semantics ∧ writes only to sandbox deps ∧ snapshot capability | `write_reversible` |
| calls external clients/queues/email/payment/webhook | `write_external` |
| delete/drop/reset/admin/bulk patterns | `destructive` |
| none of the above decidable | `unknown` |

Without code intelligence for the language the classifier can only use semantics/spec/smoke evidence and downgrades `read_safe` to `read_suspect` for operations whose behaviour it cannot corroborate (recorded as `codeintel_unavailable`).

## 10. Protocol adapters (status)

| Protocol | Discovery | Generator | Tier |
|----------|-----------|-----------|------|
| HTTP/REST | OpenAPI, routes, tests, collections | k6 http | A |
| GraphQL | SDL/introspection, captured queries | k6 http (POST) | A/B |
| gRPC | `.proto`, reflection | k6 grpc | B |
| WebSocket | handler discovery, tests | k6 ws | B |
| Queue consumers | broker config, consumer code | broker producer scripts | C |
| TCP | port discovery | connect probe only | C |

## 11. Out of scope

Soak beyond the bounded `soak_bounded` experiment; spike/burst shapes beyond ladder (future experiment kinds); distributed generators; browser-level (Playwright) load.
