# 09 — Robustness, failure modes, exit codes, host validity

Mechanics for `tech_doc.md` §9.6, §16.2 and Appendix A. Boot failures end in a named blocker. There is no LLM repair loop. Teardown always runs.

## 1. Exit codes (single definition: `tech_doc.md` §16.2)

0 report written · 1 internal error · 2 preflight failure · 3 ran but cannot conclude · 4 policy violation · 5 user abort · 6 budget exhausted before conclusion · 7 target unavailable · 8 resume invalid · 9 needs input · 10 blocked. stderr always ends with `loadline: exit=<n> reason=<code>`.

## 2. Failure-mode table (generic)

| Failure | Detection | Handling | Report impact |
|---------|-----------|----------|---------------|
| Repo not runnable / library | discovery finds no service interface | blocker `not_a_service` / `no_interface`; exit 10 | capability report only |
| Build fails | build exit/timeout | `build_failed`; exit 10 | blocker + attempt log |
| Boot/health timeout | health never green | `boot_failed` or `health_timeout`; exit 7 or 10 | blocker + redacted logs |
| Missing secret/licence | env contract unsatisfied, generated values impossible | ask user or exit 9 | `needs_input` |
| Hostile launch config | `SandboxPolicy` | refuse/rewrite; exit 4 if no safe rewrite | policy diff shown |
| Egress not blockable | egress probe | `egress_not_enforced`; exit 10 | blocker |
| No discovered operations / none pass smoke | smoke results | `no_working_operation`; exit 10 | coverage section |
| Auth unresolved | 401/403 after bootstrap | `auth_unresolved`; ask user | needs_input |
| Generator crash/hang | exit code/watchdog | kill group; step `invalid(generator_failed)`; retry once | step flagged |
| Generator saturated | drops/VU cap/CPU | `generator_limited`; reduce cap | capacity note |
| Host saturated | host metrics | `invalid(host_saturated)`; retry once; else stop search | capacity note |
| Service crash/OOM during step | restarts/OOM events | `invalid(target_unhealthy)`; recover or stop | step flagged |
| Telemetry source fails | collector error/coverage <90% | `invalid(measurement_gap)` for steps requiring it; source marked degraded | limitation |
| Intervention revert fails | health after revert | step invalid; restart environment from snapshot; if still bad → stop experiments | limitation |
| Model errors/timeouts | provider exceptions | bounded retries; then conclude with evidence so far | limitation |
| Agent loops/stalls | autopilot guard, budget | rejection with legal moves; `investigation_incomplete` when the budget or the agent fails | report from the ledger |
| Injected instructions in repo text | injection tests, untrusted wrapping | ignore; log `suspected_injection` | none |
| Disk full/pressure | pre-step check | stop; teardown; exit 2/1 | limitation |
| Interrupted run (SIGINT/crash) | signal handler/watchdog | teardown; ledger flush; resumable | partial report |
| Stray resources from earlier runs | label scan at start | warn; `doctor --cleanup` | none |

## 3. Retries and caps

| Item | Cap |
|------|-----|
| Boot attempts | `BOOT_MAX_ATTEMPTS` (5); a repeated failure signature is not retried |
| Invalid/generator-limited step retry | 1 |
| Model request retries | 2 per call with backoff |
| Tool call timeout | per tool (no unbounded calls) |
| Experiment rejections in a row | 2 inconclusive → code-read/changed question required; stall/budget → `investigation_incomplete` |
| Fix iterations | 5 test-failure iterations |

## 4. Watchdogs

Wall budget; per-step wall (planned + 30s); generator process group kill; collector deadman (no points for 10s → `measurement_gap`); orphan scan at start and end; zombie lock recovery.

## 5. Host validity

- ≥4 logical cores (else `host_too_small`, override `--allow-low-cores` ⇒ figures marked `measurement_ceiling_limited`).
- Generator ceiling measured, cached, and shown; rate cap derived.
- Memory/disk preflight for builds and datasets.
- Noisy neighbours: host CPU trend before/after each step; if drift exceeds threshold, `host_saturated` or warning.
- Laptops on battery/thermal throttling: doctor warns when CPU frequency governor suggests power save (best-effort).

## 6. Resume

`--resume RUN_DIR` verifies repo SHA/dirty hash, plan hashes, adapter versions; refuses on mismatch (exit 8). Replays ledger, re-establishes the environment (boot again from the validated plan; snapshots as available), continues with remaining budget. Completed experiments are not re-run.

## 7. Honest-failure message shape

```text
loadline: blocked — <code>
  what happened:   <one sentence with evidence ref>
  tried:           <adapter/plan attempts>
  you can provide: <specific inputs>   |   nothing — this is not supported yet (<adapter coverage ref>)
  partial results: runs/<id>/…
```

## 8. Pre-demo checklist (generic)

`loadline doctor` clean; strays removed; generator ceiling cached; canary repos pre-pulled/built where permitted; model/neatlogs keys set; held-out canary chosen *by the presenter on the day* (not tuned); recording starts with `loadline analyze`; backup recording of a prior successful run kept (labelled as recorded).
