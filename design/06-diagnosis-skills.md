# 06 — Diagnosis knowledge packs (hints, not detectors)

Notes for `tech_doc.md` D13. Signature hypotheses live in `agents/investigator_prompt.md`. They never decide a finding: confidence comes only from the function in `tech_doc.md` §12.

## 1. What a pack is

Signature hypotheses live in `agents/investigator_prompt.md` and are rendered on the board. Extra packs are not part of this build.

```markdown
---
id: serial-dependency-calls
mechanism_label: serial_dependency_calls          # free-text label, grouping only
applies_when:                                      # observable preconditions (readouts/telemetry), never repository names
  - "implied_concurrency[service] high while cpu_util[service] low"
  - "dependency latency share of request time substantial"
evidence_families: [client, service_resource, dependency, code]
discriminating_experiments:
  - kind: dependency_perturb
    prediction: "p95 shift ≈ injected latency × calls per request"
    competing: [cpu_bound, lock_contention]
code_cues:                                          # per ecosystem, as search hints only
  python: ["awaiting in a loop", "ORM access inside iteration"]
  node:   ["await inside for-of", "per-item client call"]
  jvm:    ["repository call in stream/loop"]
  go:     ["client call inside range loop"]
remediation_patterns: ["batch/join/prefetch", "bounded concurrency", "cache with explicit invalidation"]
cautions: ["a confirmed slope does not locate code; read the call path"]
---
Body: how to reason, what would refute it, common confounders, how to read the relevant readouts.
```

## 2. Library (cross-stack mechanisms; extensible)

Each is a pack of the form above; none refers to any application, framework-specific route, or fixture:

| Pack id | Mechanism family |
|---------|------------------|
| `serial-dependency-calls` | sequential I/O per request (N+1, fan-out without concurrency) |
| `blocking-in-concurrent-runtime` | blocking calls on event loop/async workers/limited thread pool |
| `connection-or-pool-exhaustion` | bounded pools/queues limiting concurrency |
| `lock-or-serialisation` | locks, single-writer queues, global interpreter/virtual-thread pinning |
| `cpu-bound-hotspot` | application CPU saturation (throttle, profile concentration) |
| `unbounded-work-per-request` | work growing with data size/page/payload |
| `missing-or-ineffective-index` | dependency work growing with dataset size (via `data_scale`) |
| `cache-ineffectiveness-or-stampede` | cache miss storms, cold start, TTL cliffs |
| `memory-growth-or-gc-pressure` | drift, GC pauses, OOM kills |
| `retry-or-timeout-amplification` | retries multiplying load; timeouts too long |
| `logging-or-serialisation-overhead` | log/serialisation cost proportional to volume |
| `dependency-saturation` | the datastore/broker/API is the limit |
| `generator-or-host-artifact` | measurement artefact (handled first via `limit_attribution`) |
| `configuration-limit` | worker/thread/limit settings under-provisioned |

Packs encode *how to test*, e.g. "predict throughput scales ×k with CPU limit ×k if CPU-bound; if it does not, CPU-bound is refuted".

## 3. Rules for authoring and using packs

1. **Hints only.** The agent may cite a pack in a hypothesis. The validator ignores citations when computing confidence.
2. **No fixture or application identifiers.** Lint rejects pack text containing names generated from `tests/fixtures/` and `tests/corpus/` (`test_no_fixture_leakage`).
3. **Every pack lists at least one discriminating experiment** with a competing hypothesis; packs without one are rejected by lint.
4. **Code cues are search hints per ecosystem**, never regex gates.
5. **Open set:** agents may form hypotheses outside the library (`mechanism_label: other:<text>`); the validator treats them identically.
6. **Pack-signal consistency test:** each pack's `applies_when` readouts must exist in the experiment catalogue's published readouts (lint).

## 4. Anti-overfitting

A pack that only helps on one stack is a data defect: each pack must have code cues for ≥2 ecosystems or be flagged `ecosystem_specific` and listed in the coverage matrix. Packs are never tuned against held-out canaries.

## 5. Not here

- No detection thresholds that produce findings.
- No closed claim list (retired in v3, `tech_doc.md` App. D).
- No per-application skills.
