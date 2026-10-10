# Loadline implementation status

Last updated after **gap closure + fixture `loadline run`** (2026-10-10).

| Gate | Status | Evidence |
|------|--------|----------|
| S0 spikes | **mostly verified** | **S0 auth canary not run**. |
| S1–S9 | **built** | `loadline run`: baseline + **ladder/bracket**, kind-aware k6 plans, prediction scoring in tools; blocked boots write `profile.json` / `capabilities.json`. |
| **Product run (FastAPI pin)** | **blocked (policy)** | Command below; exit **10**; no report; no investigator call. |
| **Fixture run (`fx-pyhttp-pg`)** | **not a success claim** | Exit **0** but `investigation_incomplete` on **80k token cap** (since removed); report at path below. |

## Product command (human)

```bash
cd /home/aarush_linux/projects/neathacks
# .env: OPENROUTER_API_KEY; set LOADLINE_MODEL if absent:
export LOADLINE_MODEL="${LOADLINE_MODEL:-openrouter:deepseek/deepseek-v4.1-flash}"
uv run loadline run --repo integration/targets/full-stack-fastapi-template --fast
```

**Outcome (2026-10-10):** exit **10**, `policy_refused` — `service proxy has a host bind mount` (Traefik `docker.sock`). **Report:** not written. **Investigator:** not run. Details: `integration/RESULTS.md`.

### Fixture command (healthy boot)

```bash
uv run loadline run --repo tests/fixtures/fx-pyhttp-pg --fast
```

**Outcome (2026-10-10):** exit **0**, status `investigation_incomplete` — `UsageLimitExceeded` at `total_tokens_limit=80000` (90 018 tokens). That cap was a product defect (same class as the old `request_limit=8`); **removed** — `loadline run` now passes `UsageLimits` with no request cap and no token cap. **Report:** `/tmp/loadline-s8-ref-125335/runs/bbad1e518c65/report.md` (partial; **no successful live investigation claimed**). Teardown: `loadline doctor --cleanup`. Details: `integration/RESULTS.md`.

`--fast` baseline uses **5s warmup / 15s measure** (`FAST_WARMUP_S` / `FAST_MEASURE_S`). Investigator `UsageLimits` has **no** request cap and **no** token cap. Auth missing → exit **2** before Docker.

## Tests (harness)

```bash
uv run pytest tests/unit -q --tb=line          # 81 passed
uv run pytest tests/sandbox/test_run_pipeline_fixture.py -q  # 1 passed (fixture)
```

## Paid model calls

| When | Outcome |
|------|---------|
| S7 live attempts | `investigation_incomplete` (not re-run for this product test). |
| Product `loadline run` (FastAPI) | **none** — boot blocked. |
| Fixture `loadline run` (`fx-pyhttp-pg`) | **one** OpenRouter run — incomplete (token cap). |

## Honest limits

Pinned **full-stack-fastapi-template** cannot boot under current policy without changing upstream compose (out of scope). Arbitrary-repo success not claimed.
