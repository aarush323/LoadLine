# 13 — Entire across the product

Runtime use of `entire graph`, as specified in `tech_doc.md` §5.3 and §15. Setup while building is `docs/ENTIRE-SETUP-AND-INTEGRATION.md`.

Entire is the code-graph provider. Ripgrep covers literal search when Entire is missing or the language is unsupported, and that capability is `degraded`. The Investigator does not use checkpoints. Checkpoints are partner evidence only.

CLI reference: [entire-graph](https://docs.entire.io/cli-reference/graph). Flags marked *verify* are confirmed with `entire graph <cmd> --help` in spike S-ENTIRE. If `--format` is missing, parse text and still save raw stdout.

Entire is a subprocess. No model ever gets a shell or picks the binary. `adapters/codeintel/entire.py` owns every argv.

## 1. Command use

| Question | Command | Caller |
|----------|---------|--------|
| Installed? language support? | `version`, `doctor`, `capabilities` | `loadline doctor`, adapter `applicability` |
| Warm cache | `index` | adapter `index()` (analyze/run start) |
| Where is the handler/region for this plain sentence? | `query` (or `search` if that is the only installed command, recorded as an alias) | `search_code` |
| Declaration and location | `def` | `code_graph` |
| Callers, callees, routes | `neighbors`; `HANDLES_ROUTE` only when capabilities list it and S-ENTIRE confirmed it | `code_graph` |
| Blast radius | `impact` | `code_graph` |
| Bulk edges | `edges` (NDJSON, diagnostics only) | not sent to the model |
| Session checkpoints for judges | `entire enable` + git commits | humans/git hooks |

**Never call:** `graph verify` (executes a command with the user's privileges) and `graph stats` (reads local coding-agent transcripts).

## 2. Shared subprocess rules

| Rule | Value |
|------|-------|
| Binary | `ENTIRE_BIN` or `entire` |
| Repo | always `--repo <root>` (the user's repo for analysis; the fix worktree for fixes) |
| Tree | working tree for queries (post-patch visible); committed tree only for `snapshot` unless `--worktree` is passed for re-export |
| Profile | `--profile full` on `search`/`index` |
| Format | `--format json` where supported (*verify*); `snapshot` NDJSON |
| Timeouts | search 20 s, def 15 s, neighbors 15 s, impact 20 s, snapshot 45 s, index 60 s, doctor/version/capabilities 10 s |
| Env to child | `PATH`, `HOME`, `ENTIRE_*` only; drop variables whose names contain KEY/TOKEN/SECRET/PASSWORD |
| Raw output | saved under `runs/<id>/graph_cache/` before parsing |
| Model payload | ≤5 hits, snippet ≤800 chars each; full bodies stay on disk |
| Cache key | `(git HEAD, dirty flag, op, canonical args)` |
| Failure | non-zero, timeout or unparseable → `ok: false`. Callers use ripgrep and `read_file`. An empty result is not proof that a call is absent. |

## 3. Tool surface (merged; see `tech_doc.md` §11.3)

- `search_code` — semantic mode runs `entire graph query` when the installed binary has `query`. If it has only `search`, that command is used and recorded as `command_alias: search`. Literal mode is ripgrep.
- `code_graph` — `def`, `neighbors`, `impact`, and `HANDLES_ROUTE` only when capabilities list it and spike S-ENTIRE confirmed it for that language. There is no tree-sitter fallback.
- `read_file{path, start, end}` — the only source of citable ranges; denylist and redaction apply.

A hit is a pointer; only `read_file` ranges satisfy the `K` check.

## 4. Intake use (no LLM)

At startup: `version`, then `capabilities --json`. Ranked search is `query` (or the recorded `search` alias). `HANDLES_ROUTE` is queried only when capabilities list it and S-ENTIRE confirmed it for the language. File specs and the live OpenAPI document stay separate facts. Languages Entire does not support are `degraded`; ripgrep and `read_file` are the fallback. `edges` is NDJSON and is not sent to the model. If the working tree is dirty, pass `--worktree` when that flag exists.

## 5. Fix use

Before `apply_patch`, the Fixer needs a successful `code_graph impact` on the changed symbols, or a recorded `graph_unavailable` for that language. After a fix commit in the worktree: `entire graph diff --repo <worktree> --base <run_sha> --head HEAD` → `runs/<id>/fix/<finding>/graph-diff.txt` (evidence of what changed, not of improvement). `entire graph explain` on test-failure stderr may enrich the Fixer's test-failure feedback (output capped 4,000 chars).

## 6. Doctor lines

`entire version`; `entire graph doctor`; `entire graph capabilities` (languages semantic vs syntax-only); plugin installed; Git ≥2.36. Failure of any ⇒ Entire adapter `unsupported` (not a hard doctor failure).

## 7. Partner evidence

- `entire enable --agent cursor` before the first product commit; checkpoints on commits during the build.
- `docs/entire/`: version, capabilities, one search, one neighbors/impact output from a **live run on a canary or fixture**, snapshot size note. No secrets.
- neatlogs shows adapter TOOL spans (`code_graph`, `search_code`) with `loadline.adapter=entire|ripgrep`.

## 8. Error codes

`GRAPH_UNAVAILABLE`, `GRAPH_UNSUPPORTED_LANGUAGE`, `GRAPH_SYNTAX_ONLY`, `GRAPH_INDEX_SKIPPED`, `GRAPH_EMPTY`, `GRAPH_AMBIGUOUS`, `GRAPH_NO_NEIGHBORS`, `GRAPH_TIMEOUT`, `GRAPH_PARSE`. None aborts a run.

## 9. First-hour verification (S-ENTIRE)

On three repos in different languages: `index`, `search` (one sentence about route handlers), `def` on a found symbol, `neighbors` out, `impact`, `snapshot`. Record flags and output shapes; freeze the field mapping in the adapter; note per-language support in `docs/spikes.md`.
