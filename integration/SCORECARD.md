# Scorecard — product `loadline run` (pinned FastAPI template)

**Run scored:** `uv run loadline run --repo integration/targets/full-stack-fastapi-template --fast` (2026-10-10)  
**Rubric:** `integration/DESIRED-OUTPUT.md` §6 (five questions)  
**Evidence read:** `integration/RESULTS.md`, `docs/implementation-status.md`, `integration/targets.lock.json`, `integration/DESIRED-OUTPUT.md`; spot-check `loadline/**/*.py` for target-specific route leakage (no matches for `health-check` / `full-stack-fastapi`).

**Recorded outcome:** exit **10**; `status`: `blocked`; `blocker.code`: `policy_refused`; summary `service proxy has a host bind mount`; report **not written**; investigator / OpenRouter **not invoked**; `loadline doctor --cleanup` removed **2** labelled objects.

---

## 1. Pin integrity — **PASS**

| Criterion | Verdict | Evidence |
| --- | --- | --- |
| Target SHA matches pin | OK | `integration/RESULTS.md` (Product run table) and `integration/targets.lock.json` both give `7257e606cb94eada1dca40173e2b7f99dd549bc6`. |
| Clone not modified | OK | `integration/RESULTS.md` § Diagnosis (product run): “the clone was not modified.” |
| No target routes in `loadline/` discovery code | OK | `grep` over `loadline/**/*.py` found no `health-check` or `full-stack-fastapi` strings; rubric example paths appear only in `integration/DESIRED-OUTPUT.md`. |

---

## 2. Discovery honesty — **FAIL**

| Criterion | Verdict | Evidence |
| --- | --- | --- |
| Compose-based discovery with evidence in JSON | **Not logged for this invocation** | Product-run section of `integration/RESULTS.md` records only boot-blocker stderr JSON (`policy_refused` on `proxy`); it does **not** capture `analyze --json` / profile fields (`compose_files`, `dockerfiles`, languages, `capabilities.runtime`, OpenAPI degraded). |
| No false full-stack boot claim | OK | `docs/implementation-status.md` and `integration/RESULTS.md` state boot blocked, no report, investigator not run. |

**Note:** An earlier row in `integration/RESULTS.md` (S8 `analyze --json`) documents discovery **pass**, but that is a **different command sequence**, not the product `loadline run` being scored here. Scorers cannot treat it as evidence for this run without inventing continuity.

---

## 3. Policy outcome — **PASS**

| Criterion | Verdict | Evidence |
| --- | --- | --- |
| `policy_refused` on Traefik `docker.sock` (or equivalent) | OK | `integration/RESULTS.md` CLI JSON: `blocker.code` `policy_refused`, summary `service proxy has a host bind mount`; aligns with `integration/DESIRED-OUTPUT.md` §2 expectations. |
| Policy not weakened | OK | `integration/RESULTS.md` Diagnosis: “`SandboxPolicy` was not weakened”; `docs/implementation-status.md` same. |
| No smoke/baseline/investigator on unbooted plan | OK | Both logs: report not written; investigator not run. |

---

## 4. Evidence discipline — **PASS**

| Criterion | Verdict | Evidence |
| --- | --- | --- |
| Measured vs hypothesis separation in report/investigator | N/A (no outputs) | `integration/RESULTS.md`: “Report: **not written**”; `docs/implementation-status.md`: “no report; no investigator call.” |
| No invented bottlenecks or numbers | OK | No `report.md` / investigator output exists for this run; logs do not assert performance defects or k6 metrics. |

---

## 5. Observability — **FAIL**

| Criterion | Verdict | Evidence |
| --- | --- | --- |
| neatlogs trace URL + workflow/tags (`run_id`, `agent_profile`, `fast`) | **Not recorded** | `integration/RESULTS.md` product section has **no** hosted neatlogs URL; `docs/implementation-status.md` does not document trace tags or workflow name for this invocation. Rubric (`integration/DESIRED-OUTPUT.md` §6) expects URL in `RESULTS.md` when tracing is configured. |
| TOOL attributes (`loadline.result_id`, `loadline.ok`, etc.) | **Not applicable / not evidenced** | Investigator did not run (`integration/RESULTS.md`, `docs/implementation-status.md`); missing investigator tool traces is **expected**, not a pass substitute for trace/tag evidence that was never logged. |
| Teardown: zero labelled objects after cleanup | OK | `integration/RESULTS.md`: `doctor --cleanup` “removed 2 labelled objects”; user run summary matches. |

---

## Summary

| # | Question | Verdict |
| --- | --- | --- |
| 1 | Pin integrity | **PASS** |
| 2 | Discovery honesty | **FAIL** |
| 3 | Policy outcome | **PASS** |
| 4 | Evidence discipline | **PASS** |
| 5 | Observability | **FAIL** |

**Overall:** **3 PASS / 2 FAIL** — sandbox policy behaved as designed for the pinned compose; product-run logging is thin on discovery JSON and neatlogs trace evidence.
