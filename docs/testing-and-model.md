# Loadline — testing budget and model configuration

Authoritative contract: `tech_doc.md`. Build order: `implementation.md`. Live status: `docs/implementation-status.md`.

## OpenRouter (hackathon / CI canary only)

Do **not** call the model on every unit test. Mock structured output and tool calls in S1–S6 tests.

| When | Calls allowed |
|------|----------------|
| S0 spike S-AUTH | One small canary: auth, structured output, one tool call, timeout, usage fields |
| S7 gate | One controlled Investigator run on a small fixture (tool cycle + honest stop) |
| Pre-demo e2e | One reference-app `loadline run` after S3–S5 gates are green; one diagnostic rerun only if budget remains |

### Environment

```bash
export LOADLINE_MODEL="openrouter:deepseek/deepseek-v4.1-flash"
export OPENROUTER_API_KEY="<from .env>"
```

Loadline maps `openrouter:<model-id>` to Pydantic AI's OpenRouter provider. Missing `OPENROUTER_API_KEY` must fail preflight (exit 2) before Docker when `LOADLINE_MODEL` uses the `openrouter:` prefix.

### OpenRouter request profile (documented for S0 verification)

```json
{
  "provider": {
    "max_price": { "prompt": 0.10, "completion": 0.20 },
    "require_parameters": true
  },
  "usage": { "include": true }
}
```

Price ceilings are USD per million tokens. Do not relax `max_price` or `require_parameters` on failure — fix the request or record a blocker.

### Neatlogs

Set `NEATLOGS_API_KEY` when tracing failures or partner evidence. Workflow name: `loadline`. Tags include `run_id`, `agent_profile`, `fast`.

## Integration targets

- Deterministic fixtures: `tests/fixtures/` (oracles in `tests/oracles/`, never imported by `loadline/`).
- Reference app: `integration/targets/full-stack-fastapi-template/` (gitignored), SHA in `integration/targets.lock.json`.
- Entire install integration: `LOADLINE_ENTIRE_INTEGRATION=1` (separate from graph analysis on a target repo).

## Commands (quick reference)

```bash
uv sync --extra dev
uv run pytest tests/unit -q
uv run pytest tests/ -m "not integration" -q
LOADLINE_ENTIRE_INTEGRATION=1 uv run pytest tests/test_entire_runtime.py -m integration -q
```

## Terminal output during `loadline run`

On a TTY, stderr shows phased progress (`… Boot`, health wait ticks) and, during Investigate, a live trace of model tool calls and k6 start/done lines (Pydantic AI `run_stream_events`, formatted by `loadline/ui/agent_trace.py`). stdout prints `report.md` after success unless you pass `--no-report-print`. Scripting: `--json` emits one `RunPipelineResult` object on stdout and suppresses progress; `--quiet` keeps errors only and hides investigate sub-lines. Boot-only debugging: `loadline analyze PATH --boot` uses the same boot sub-step lines on stderr while JSON goes to stdout. Optional disk trace: `LOADLINE_LOG=debug` appends to `run_dir/events.jsonl`. See [terminal-ux-plan.md](terminal-ux-plan.md).
