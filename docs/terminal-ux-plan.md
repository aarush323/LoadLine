# Terminal run visibility

Implemented UX for `loadline run`: phased stderr progress, boot sub-steps, full investigate trace (model tool calls and k6), human blockers, and markdown report on stdout.

## Usage

```bash
# Default TTY: progress on stderr including investigate tool lines, report.md on stdout when successful
uv run loadline run --repo ./myapp

# CI / scripting
uv run loadline run --repo ./myapp --json --no-report-print

# Less noise (no investigate sub-lines)
uv run loadline run --repo ./myapp --quiet

# More boot detail and longer investigate arg snippets
uv run loadline run --repo ./myapp --verbose

# Show a past report
uv run loadline report show ~/.local/share/loadline/runs/<run_id>
```

## What you should see

During boot, stderr updates at least every 10–15s (`health: Ns / budget`, `still building...`). Phases: Preflight → Boot → Investigate → Report.

During **Investigate** on a TTY (default, not `--quiet` / `--json`), stderr includes lines such as:

- `[investigate] → repo routes` / `← repo 12 routes`
- `[investigate] → read_file app/api/main.py L1-L80`
- `[investigate] → run_k6 rate=10 duration=15s ops=health,login`
- `[investigate] docker agent-k6-1 offered=10rps duration=15s ops=health`
- `[investigate] ← k6 exp-k6-0001 agent-k6-1 rate=10 p95_health=12ms`

On boot failure, stderr includes compose `ps` and log tails (not only JSON).

Set `LOADLINE_LOG=debug` to append the same messages to `run_dir/events.jsonl`.

See also the archived stub [ui-plan.md](ui-plan.md).
