# 05 — Investigation agent: reasoning, experiments, predictions

Mechanics for `tech_doc.md` §11 and §12. Experiment kinds are the table in §11.2, including `dependency_perturb`. Code owns measurement, limits, legality and every report number. The agent owns hypotheses, experiment choice, code reading and remediation wording.

## 1. Why this shape

A fixed detection catalogue or a fixed sequence (ramp → telemetry → read) fits one stack and fails the next. The generic version is the scientific loop: **hypothesis → prediction → intervention → comparison → code investigation → refine/reject**, with code scoring predictions so the model cannot narrate its way to success.

## 2. Agent inputs (each turn)

- Static instructions: role, honesty rules, tool contract, untrusted-data rules (§8).
- Dynamic instructions: the four-section board in `tech_doc.md` §11.1, regenerated every turn.
- Message history compacted by `history_processors` to ledger references after K turns.

## 3. Experiment specs (illustrative; kinds are defined in `tech_doc.md` §11.2)

```json
{ "kind": "dependency_perturb", "hypothesis_id": "h2",
  "params": { "edge": "<service>-><dependency>", "inject": {"latency_ms": 20}, "at_rate": "lo*0.8", "ops": ["<op>"] },
  "predictions": [
    { "readout": "p95_ms", "comparator": "changes_by", "magnitude": {"min_ms": 100, "per_call_ms": 20}, "against": "baseline@same_rate" },
    { "readout": "throughput_rps", "comparator": "unchanged", "magnitude": {"rel": 0.05} } ] }
```

```json
{ "kind": "resource_perturb", "hypothesis_id": "h1",
  "params": { "service": "<service>", "resource": "cpu", "scale": 2.0, "at_rate": "hi" },
  "predictions": [ { "readout": "throughput_rps", "comparator": "ge", "magnitude": {"rel": 1.6}, "against": "baseline@hi" } ] }
```

Each kind publishes its readouts (names, units, computation) so predictions are checkable. Magnitudes may be absolute, relative, or functions of declared parameters (e.g., injected latency × calls per request); the evaluator has a small fixed expression grammar (`per_call_ms`, `rel`, `abs`, `min`, `max`) — no free-form code.

## 4. `PredictionEvaluator`

For each prediction:
1. Resolve `against` (baseline step at the same rate/plan hash, or another experiment id).
2. Compute readout values with sample size and bootstrap CI from raw step data.
3. Noise floor: `max(configured min, 2 × baseline run-to-run variation)` where variation comes from calibration repeats or confirm steps.
4. Outcome:
   - `confirmed` if the comparator holds beyond the noise floor and validity is `valid`,
   - `refuted` if the opposite holds beyond the noise floor,
   - `inconclusive` otherwise (including invalid steps).
5. Emit `prediction_scored` with numbers and evidence ids.

**Discriminating** prediction: its expected outcome differs under at least one registered competing hypothesis (declared with `competing`). Hypothesis status `supported` requires ≥1 confirmed discriminating prediction and no refuted one without explanation. This replaces any "pattern match" notion of M.

## 5. Typical reasoning moves (examples, not sequences)

| Observation | Hypotheses the agent may form | Discriminating intervention |
|-------------|------------------------------|-----------------------------|
| Throughput plateaus, CPU util low, implied concurrency high | blocking/serialised work; pool or lock limit; slow dependency | `resource_perturb` on pool/worker knob; `dependency_perturb` slope; `profile_capture` on-CPU vs off-CPU |
| p95 grows with payload/page size | per-item work amplification; serialization cost; query size | `param_scale` plus dependency call counts per request |
| CPU throttled at the service's limit | application CPU-bound | `resource_perturb` CPU×k predicts throughput×k |
| Dependency latency rises with rate while service idle | dependency saturation | dependency stats trend, `dependency_perturb` on the *dependency's* other client or limit |
| Memory/latency drift over time | leak/growth | `soak_bounded` at ≤`lo` |
| First requests slow after restart | cold caches/JIT | `warm_cold` |

These are prompts to think, shipped as knowledge packs (`06`), never gates.

## 6. Legality and advice (`ExperimentPolicy`)

`admit` returns either `Admit` or `Reject(code, reason, legal_moves[])`. Rejections are data for the model (advice text ≤400 chars). Examples of codes: `kind_unavailable(capability)`, `precondition(op_not_smoked)`, `rate_over_cap`, `budget`, `read_gate(op)`, `autopilot(repeat)`, `intervention_unsafe`, `side_effect_class`. Legal moves list is computed, not hand-written.

**Read gate:** escalation beyond the first ladder at an operation requires a prior `read_file` covering its handler (when CodeIntel supports the language). **Autopilot guard:** same experiment kind + params hash twice without a new hypothesis or changed param → reject; two consecutive `inconclusive` → require an `inspect_runtime` or code-read turn, or a changed question, before the next load step.

## 7. Context discipline and compaction

Tool returns are summaries with evidence ids; raw series are never injected. History processor keeps the last N turns verbatim and replaces older turns by `ledger#seq` references plus one-line outcomes. The four-section board is regenerated before every turn (no `get_run_state` tool). `UsageLimits(request_limit, total_tokens_limit)` prevents runaway; `tool_calls_limit` from budget.

## 8. Untrusted data handling

Repository text, logs, response bodies and error messages are wrapped in delimited blocks labelled `UNTRUSTED_DATA`, truncated, control-char stripped, and never placed in instruction position. Tools never accept free-form commands. An injection test suite (hostile README/comments/log lines instructing the agent to ignore rules, call tools, or exfiltrate) must show no change in tool-use legality or content.

## 9. Agent profiles for "agent improved"

`LOADLINE_AGENT_PROFILE`:
- **v0 (baseline policy):** hypotheses optional, no discriminating requirement, no board, no legal-move advice, no read-gate advice (policy still enforces safety and limits; legality of experiments is never relaxed).
- **v1 (default):** everything in this doc.
Comparison is made on the same target SHA with two live runs: tokens, cost, tool errors, rejected-experiment count, findings with `M` true, uncited/unlocated findings, and measured `lo` agreement. Safety and measurement validity are identical in both profiles.

## 10. Scripted driver (tests only)

> The product has exactly one deterministic investigation step, the `baseline` ramp. A scripted driver may exist in the test suite to exercise the engine and report without an LLM; it never ships as a fallback.

A deterministic driver that plays the legal-move set with a **fixture-agnostic** policy (calibrate → ladder on mix → ladder per heaviest operations → attribute → perturb the attributed resource). It exists to test the engine, evaluator and report paths in CI. It contains no fixture knowledge; it does not produce findings (it produces experiment logs and a null-finding report).

## 11. Termination

See `tech_doc.md` §11.7. "No bottleneck found within the measured range" (e.g., `above_ladder`) and "cannot conclude" are valid reports.

## 12. One agent

The only in-app agent is the Investigator (`tech_doc.md` §11.3). Boot does not use an agent (`design/03-environment.md` §9). Findings carry remediation text (`tech_doc.md` §13).
