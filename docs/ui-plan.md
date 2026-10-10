# Run CLI progress (superseded)

**Implemented.** See [terminal-ux-plan.md](terminal-ux-plan.md) for usage and behavior.

## Problem

`loadline/cli.py` `run` calls `run_pipeline.run_loadline` and prints only `report:` / `run_dir:` on success, or JSON on stderr when boot blocks. There is no phase feedback during boot, k6 baseline/ladder, or the investigator. `tech_doc.md` §16.1 documents `loadline report RUN_DIR` but no `report` subcommand exists in the CLI today.

`report_render.render_markdown` and `write_report` already produce `report.md`; the gap is surfacing it and progress, not re-scoring findings.

## Design (cli-design contract)

**Grammar**

- `loadline run --repo PATH [--fast] [--skip-investigator] [--json] [--quiet] [--no-color] [--no-report-print]`
- `loadline report show RUN_DIR` — print `report.md` (or `report.json` with `--json`)
- Global: honor `NO_COLOR=1`; stderr = diagnostics + progress; stdout = primary payload (`--json` object only on stdout when `--json`)

**Lifecycle phases** (one line each on stderr unless `--quiet`):

```text
Preflight → Boot → DiscoverWorkload → Calibrate → Baseline → Ladder → Investigate → Report → Teardown
```

Use symbols + words (not color-only): e.g. `… Boot` / `✓ Boot` / `✗ Boot` with `NO_COLOR` stripping ANSI.

**Human blocker** (non-`--json`, TTY): what / code / next / `run_dir`. Full JSON via `--json`.

**Success (TTY, default):** status line, separator, body of `report.md` on stdout, footer with `run_dir` and neatlogs hint if configured.

**Script / CI:** `--json` → single JSON on stdout; `--quiet` → errors + exit code only.

**Investigator trace:** poll or callback on `ledger.jsonl` during Investigate; one-liners for hypothesis / experiment / finding on stderr.

## Implementation todos

1. **run-console-module** — `loadline/ui/run_console.py`
2. **pipeline-hooks** — instrument `run_pipeline` + investigator
3. **cli-flags-report** — `cli.py` flags, `loadline report show`
4. **cli-tests-docs** — unit tests + help examples

Add `rich` for stderr console and optional Markdown styling; no full TUI.

## Verification

```bash
uv run loadline run --repo integration/targets/full-stack-fastapi-template
```

Visible phase lines; markdown report on stdout on success; readable blocker on failure.
