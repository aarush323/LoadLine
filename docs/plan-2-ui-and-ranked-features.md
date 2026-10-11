# Plan 2 — UI, then a ranked backlog

Status: plan only. Start this after plan 1 has a real `report.md`, a real `verification.json`, and a neatlogs trace.
Nothing here is required to submit on Monday 12 Oct 2026.

Plan 1 already prints the before/after table in the terminal and appends it to `report.md`. This plan is about seeing that evidence clearly, and about which later features are worth the time.

---

## 1. The three surfaces that exist today

They do not yet show the same object. That is the main UI defect.

### Terminal (`loadline/ui/run_console.py`)

This is the surface that matches the live pipeline.

During `loadline run` you get phase lines on stderr: Preflight, Boot, Investigate, Report. Boot prints health polls and, on failure, compose status and log tails. Investigate prints tool lines: `repo`, `read_file` path and range, `run_k6` rate and duration, then the k6 result line with experiment id and p95. On success, stdout is the investigator’s `report.md`. Stderr ends with `run_dir` and `report`.

Flags that matter: `--json`, `--quiet`, `--verbose`, `--no-color`, `--no-report-print`, `--fast`, `--skip-investigator`. `loadline report show <run_dir>` reprints the markdown. `loadline dashboard` without `--serve` prints a text summary.

What it cannot show yet: a before/after table. Plan 1 adds that print at the end of `loadline verify`. Until verify exists, the terminal’s last word is the investigator’s prose, which is allowed to be incomplete.

### Web dashboard (`loadline dashboard --serve`, default port 8123)

A localhost server (`loadline/dashboard/server.py`) renders one self-contained HTML page per run (`loadline/dashboard/template.html`, `v3_app.js`, `loadline/dashboard/render.py`). `loadline dashboard --export` writes that page to a file. The index at `/` is a table of runs: id, repo name, state, peak offered, wave count, age. Row click opens `/runs/<id>`.

The run page is one long document with a left rail, not five different apps. The rail anchors are Overview, Code map, Experiments, Evidence ledger, Environment. A command palette (Ctrl/Cmd-K) jumps to those anchors or copies the run id. Design tokens follow `docs/loadline_design_system_v3.md`: warm paper, serif headline, Geist for UI, one dark graph stage.

What a real run can fill today:

| Region | Source | On a live investigator run |
|---|---|---|
| Hero headline and state pill | `report.json` `run_state`, else the ledger | Weak. Live `report.json` is only `run_state` and `source`. The headline is a generic state, not the agent’s verdict sentence. |
| Metric strip | Last and peak `k6_run` rows: offered rps, worst p95, dropped iterations | Real, when `run_k6` succeeded. |
| Pressure charts | One point per `k6_run` wave, offered rps and p95 | Real. Two SVG sparklines sharing an index, not a time axis with timestamps labelled in detail. |
| HTTP operations table | Per-operation fields on the latest wave: p95, error count, achieved rps | Real for operations the agent actually loaded. SLO verdict is only as good as the data on that row. |
| Investigation trail | Ledger events | Shows `k6_run` steps. Hypothesis rows appear only if kind `hypothesis` exists. The live agent does not write that kind. |
| Evidence table | Evidence ids on ledger events | Ids from `k6_run`. `read_file` ranges are not on the ledger. |
| Code map | Up to four operations. If the target repo is still on disk and Entire exposes `HANDLES_ROUTE`, matching handlers are looked up and drawn. Otherwise the map says unavailable and shows the operations only. | Partial. The graph is a neighbourhood sketch, capped at four operations. Static edges are not runtime traces; the footer already says that. |
| Inspector | Selected node: kind, title, a few facts, a finding blurb | The finding blurb looks for ledger kind `finding`, which the live path does not write. The test in `tests/unit/test_web_dashboard.py` fabricates `hypothesis` and `finding` events, so the page looks finished in tests and empty on a real run. |
| Environment table | Profile and run constraints the renderer knows | Partial. Isolation and “not measured” states need to stay visible. |
| Report | Download of `report.md` | The prose is not rendered in the page. |

Buttons that do not do what their label suggests: “All operations” toasts a count, “Fit graph” sets node opacity and toasts, several “view” actions only scroll. The palette cannot start a run or open a verification.

Fonts load from Google. Offline, the page falls back to whatever the browser substitutes. Fine for a local demo, worth self-hosting if this page is the one you record.

### Markdown report

The canonical words of a live run are the investigator’s last message in `report.md`. `loadline/core/report_render.py` can render a structured `ReportModel` (verdict, capacity, findings, limitations) and unit tests cover it. `run_pipeline.py` does not call that renderer. So the dashboard and the structured renderer agree with each other less than either agrees with the agent’s prose.

Plan 1’s comparison section is appended under the prose by code. The dashboard should display that section from `verification.json`, not by scraping the markdown.

---

## 2. What “clearer” means

A person opening the latest run should be able to answer, in order, without reading JSON:

1. Did this run measure anything?
2. Which route got worse, at what offered rate, with which experiment id?
3. Which file lines were read before that claim?
4. If verify ran: did that same route, at that same rate, get better, and was a pull request opened?

If the answer is “not measured” or “hypothesis failed,” the page says that in the hero. It does not borrow a finding from a different event to fill the inspector.

Decoration that does not answer those four questions waits.

---

## 3. UI work, in the order it pays off

Estimates are focused hours after plan 1, for one person who already knows this repo. They assume the verification file from plan 1 exists. They do not include a visual rewrite.

### U1. Hero is the verdict, and verify is a first-class panel

**Time:** 5–7 hours. **Value:** highest. Do this first.

- Parse nothing out of the model’s adjectives. Hero state comes from `report.json` `run_state` and, when present, `verification.json` `verdict`.
- Put the investigator’s first non-empty paragraph under the hero as “Hypothesis,” labelled as prose, visually quieter than the numbers.
- Add a Verification panel above the charts when `verification.json` exists: the same columns as plan 1’s table (call, rate, duration, before, after, control), the verdict word, the branch, and the pull request URL or the sentence “No pull request: hypothesis failed.”
- When verify has not been run, the panel says “Not verified” and does not show a second column of dashes that look like zeros.
- Metric strip keeps using `k6_run` numbers. If a verification after-run exists, the strip gains one line: “Cited metric, before → after” taken from `verification.json` only.

**Test:** extend `tests/unit/test_web_dashboard.py` with a run that has `k6_run` rows and a `verification.json` of `hypothesis_failed`. The HTML contains both p95 numbers and the words “No pull request.” A second case with no verification file does not contain a fake after-number.

### U2. Stop rendering phantom findings

**Time:** 2–3 hours. **Value:** highest honesty per hour.

- If the ledger has no `finding` events, the inspector finding block is omitted, not filled with a placeholder title.
- If there are no `hypothesis` events, the trail does not invent H-01 nodes on the graph. Hypothesis nodes are drawn only from ledger rows.
- Optional small addition in the investigator, only if it stays a pure log: when `read_file` succeeds, append a ledger event `read_file` with path and lines. The evidence table can then list what was read. This is the same data as plan 1’s `reads.jsonl`. Prefer reading `reads.jsonl` in the dashboard so the investigator does not grow a new side channel.
- Code map: if Entire is unavailable, keep the current “map unavailable” copy. Do not draw decorative nodes that look like call edges.

**Test:** the existing fabricated-ledger test can stay as a fixture of those kinds. Add a fixture whose ledger is only `k6_run` and `report_written`, matching `investigator/run.py` and `k6_tool.py`. Assert the HTML does not contain “H-01” or a finding title.

### U3. Render the report and the experiments as themselves

**Time:** 4–6 hours. **Value:** high.

- A Report section shows `report.md` as HTML (headings, tables, code fences). The verification section is already in that file after plan 1; rendering the markdown makes the terminal and the page agree. Sanitize: no inline scripts from the report.
- Experiments become a table, one row per `experiments/*.json`: id, endpoints, rate, duration, p95 per operation, error rate, dropped iterations. Clicking a row scrolls the chart point for that wave and highlights it. The row for the contract’s `experiment_id` and the verify replay are marked Before and After.
- “All operations” opens the full operation table instead of a toast. If there are four or fewer, the button is hidden.

**Test:** a report containing a `| Before | After |` table appears as a `<table>` in the page. A `k6_run` with two operations produces two rows, with the rates from the JSON.

### U4. Code map tied to the read and the slow operation

**Time:** 6–8 hours. **Value:** high once U2 is honest, medium before that.

- Default selection is the operation named in `verification.json` when that file exists, else the worst p95 operation (already computed in `render_run_page`).
- Inspector shows the `reads.jsonl` ranges whose path matched the handler file, with the line span. “Open source” displays that snippet from the repo if the repo is still on disk, passed through the existing redactor. If the repo is gone, say “repository not available,” which the graph code already does for a missing profile root.
- Keep the four-operation cap, and keep the “+N more” note. Add a list under the graph of the operations that were not drawn, so the cap is visible.
- Pressure-only toggle already dims non-pressure edges. Leave it. Do not add physics, animation, or a second graph library.

**Test:** a temp repo with a file, a `reads.jsonl` range, and a `HANDLES_ROUTE` record is not required for the unit test if graph subprocess is heavy. Unit-test the inspector context builder with a fake handler map: the selected op’s read range is in the HTML, a read of a different file is not shown as that op’s source.

### U5. Run index that matches the loop

**Time:** 2–3 hours. **Value:** medium.

- Index columns: repo, state, peak offered, verification verdict (`improved`, `hypothesis_failed`, `not verified`), when.
- `/api/runs` includes `verification_verdict` so a later client does not scrape HTML.
- Filter box: substring of repo path. The CLI already has `--repo` for the terminal picker; the server should honor `/?repo=`.

**Test:** two fake runs, one with `verification.json`, index HTML shows the verdict word on that row only.

### U6. Terminal verify output, if plan 1’s print feels cramped

**Time:** 2 hours. **Value:** medium. Skip if the plan 1 table is already readable.

- After `loadline verify`, stderr prints the verdict word, then the five-line table, then `pr:` URL or `pr: not opened (<verdict>)`.
- `--json` prints `verification.json` and nothing else.
- Reuse `RunConsole` symbols so verify phases are Boot → Replay → Compare → Pull request, and Pull request is skipped with a clear mark when the verdict is not `improved`.

**Test:** `tests/unit/test_run_console.py` style: a failed hypothesis does not contain a URL.

### U7. Empty, blocked, and refused runs

**Time:** 3–4 hours. **Value:** medium. This is the FastAPI-pin screen.

- A run that stopped at `policy_refused` still has a run directory with attempts (see `persist_blocked_attempts`). The dashboard should open it: hero “Run did not reach measurement,” the blocker summary, `security: true`, and no charts.
- Today `render_run_page` returns an empty page when there is no report and no waves. A policy refusal with only `profile.json` and attempts can fall through that hole. Serve the blocker instead of “not measured (no run artifacts)” when a blocker file exists.
- Copy the blocker sentence verbatim. Do not suggest allowing `docker.sock`.

**Test:** a run dir with a blocker JSON and no ledger renders the summary and does not render the pressure chart.

### U8. Visual polish pass on the current page

**Time:** 4–6 hours. **Value:** medium, and only after U1–U3. A prettier empty inspector is still an empty inspector.

Do this as a restraint pass against `docs/loadline_design_system_v3.md`, not a new system:

- One focal point on first view: the verdict and the before/after (or the pressure chart when verify has not run). Move the code map below the fold on Overview; the rail still jumps to it.
- Serif for the hero sentence only. Numbers in the mono face, with units.
- One signal color, used for an SLO breach or a `hypothesis_failed` / `regressed_control` verdict. A completed run stays ink-on-paper.
- Self-host Geist and Instrument Serif, or drop the Google CSS request so a recorded demo does not depend on a font CDN.
- Check the page at 1280px and at 390px. The rail can collapse to the top at 390px. The chart must remain readable; horizontal scroll on the operations table is acceptable.
- Icon-only buttons keep an accessible name. The ones that only toast either gain a real action in U3 or lose the button.

**Test:** no new data test. Browser check: open a fixture run, confirm the verdict is the first text, tab to the palette, Escape closes it, and the verification table is visible without scrolling past the graph on a desktop viewport. Plan 1’s user rule applies: exercise the page, do not stop at a screenshot.

### U9. Live dashboard while a run is in progress

**Time:** 1.5–2.5 days. **Value:** low for the hackathon, real for the product.

The server is read-only and renders once per request. A live view means tailing `ledger.jsonl` (polling is enough) and re-rendering the trail. Do not start this until U1 exists, or the live view will stream k6 points into a page that still has no verdict model.

### Explicitly not in the UI pass

- A chat panel wrapped around the investigator.
- Animating the graph as if edges were traces.
- Recomputing a second verdict in JavaScript. The page displays `verification.json` and ledger fields.
- Replacing the CLI. The CLI remains the way a run starts.

---

## 4. Feature backlog

Ranked for after the Monday submission, when you pick from this list. Value is usefulness to someone pointing Loadline at a repo, scored 1–5. Hackathon value is scored separately so a high product idea is not confused with a Monday idea. “Depends” names the plan 1 artifact that must exist first.

| Rank | Feature | Time | Product value | Hackathon value | Depends | Why it is here |
|---|---|---|---|---|---|---|
| 1 | U1–U3 above: verdict, real experiments, no phantom findings | 1–2 days | 5 | 4, only as a nicer recording of artifacts you already have | `verification.json`, `experiments/*.json` | Makes the loop legible. Does not create new evidence. |
| 2 | Persist and show `reads.jsonl` on the inspector (U4) | 6–8 h | 5 | 3 | Plan 1 reads file | Connects the number to the lines the agent actually opened. |
| 3 | Blocked-run page for `policy_refused` (U7) | 3–4 h | 4 | 4 if the demo includes the FastAPI pin | Attempt JSON already written on refusal | The refusal is a feature. The UI should show it as clearly as a chart. |
| 4 | `loadline report show` prints the verification table when the file exists | 2 h | 4 | 3 | Plan 1 | Same truth as the dashboard, for a terminal demo. |
| 5 | Second replay for noise, surfaced as `inconclusive` when the two after-numbers disagree | 4–6 h | 4 | 2 | Plan 1 comparator | Stops a lucky single k6 sample from opening a pull request. Plan 1 already specifies the rule; this is the implementation if the first replay ships alone. |
| 6 | Apply the hint keys that are still ignored, with tests: `compose_profile`, `command`, `env`, `exclude_operations`, SLO | 1 day | 4 | 3 if your non-fixture repo needs one of them | Plan 1 `load` | Plan 1 already says to wire the ones the demo repo hits and to list the others as `hints_ignored`. Finishing the rest is the follow-through. |
| 7 | Healthcheck shapes the regex still misses, driven by a saved `test:` string from a repo that failed | 2–4 h each shape | 3 | 3 only for that repo | A failed boot log | One regex per real healthcheck. No catalogue of frameworks in production code. |
| 8 | Recovery trace as a first-class neatlogs story: a denied tool call, then a successful one, visible in the trail | 3–5 h | 3 | 4 | A real trace | Judges look for “agent improved.” The trail should show the failed step instead of hiding it. |
| 9 | Structured findings written by code from the ledger, using the existing `ReportModel` renderer, with the agent prose kept as a quoted section | 1.5–2 days | 5 | 2 | Stable experiment schema | This is how the report stops being only a last message. It is a large change next to the investigator. Do it after the verify loop has been trusted once. Do not let the renderer invent findings the ledger does not contain. |
| 10 | Kind-aware experiments (`isolate`, `mix_ablation`) actually changing the k6 plan the agent runs | 2–3 days | 4 | 1 | A measured baseline worth isolating | `build_measurement_plan` is tested and unused. Turning it on changes the investigator’s behavior. Worth doing when you want causal isolation beyond “same k6 again.” Not worth doing to decorate Monday. |
| 11 | Prediction scoring shown in the UI (`supported` / `refuted` from `loadline/core/predictions.py`) | 1–2 days | 4 | 2 | Ledger events that the live tools do not write today | The scoring code exists. The live tool path does not emit `prediction_scored`. Wiring it is an investigator change. Schedule it with rank 9, not as a badge on the dashboard. |
| 12 | Operation proposer that is not a no-op, still smoke-tested and read-safe | 2 days | 3 | 1 | Boot already finds routes | `operation_proposer.py` returns the list unchanged. Useful when discovery misses routes. Risky if it proposes writes. Keep the read-safe gate. |
| 13 | Auth flows beyond the sealed `default_user` profile already in `run.py` | 1–2 days | 4 | 2 | A repo whose interesting route is behind login | The FastAPI pin needs this, and the pin is refused at boot before auth matters. Do it for the next repo that boots and returns 401, not to unblock `docker.sock`. |
| 14 | Postgres row counts already attempted in compose boot, shown in the environment panel when measured | 3–4 h | 3 | 1 | A booted Postgres | The adapter exists. The UI should show the number or “not measured,” including the reason. |
| 15 | MySQL, Mongo, Redis adapters | 2–4 days each | 3 | 0 | Postgres path stays honest | Named out of scope in `mvp.md`. Rank them only after a user repo is actually blocked on that database. |
| 16 | Export a single HTML file that includes the verification panel (`dashboard --export`) | 2 h, once U1 exists | 3 | 3 | U1 | Useful for the video if the live server is awkward to record. The export path already writes the current page. |
| 17 | Run-to-run list for the same repo: last five peak p95 values | 4 h | 3 | 1 | More than one real run | Easy to fake a trend. Only plot runs whose operation id and rate match. Otherwise it is a different test. |
| 18 | CI job: unit tests plus the sock-refusal fixture, no model key | half a day | 4 | 2 | Chunk 1 tests | Keeps the sandbox from rotting after the hackathon. |
| 19 | Live browser progress (U9) | 2 days | 3 | 1 | U1 | Nice. Does not change a verdict. |
| 20 | A larger frontend (client router, component kit, accounts) | 1–2 weeks | 2 | 0 | A stable JSON API | `mvp.md` deferred `report.html`. The current server-rendered page can get to U8 without a new app. A new frontend before the verify JSON is stable will drift from the ledger. |
| 21 | GraphQL, gRPC, WebSocket, Kubernetes, write-heavy load, soak, USL fit | weeks | 2 | 0 | The HTTP loop is trusted | Out of scope in `mvp.md`. Revisit when an HTTP verify has opened a real pull request more than once. |
| 22 | Letting the FastAPI template boot by allowing `docker.sock` | — | 0 | 0 | — | Not a feature. The demo says the pin was refused. |

---

## 5. How to choose after Monday

Pick in this order unless a real repo blocks you earlier:

1. U1, U2, U3 (the page tells the truth about the loop).
2. U7 if the refusal screen is embarrassing next to the success screen.
3. U4 and U5.
4. Rank 9 (structured report) only when you are willing to touch report generation again.
5. Rank 6 for whatever `hints_ignored` the next repo actually prints.
6. Leave ranks 15, 20, 21, and 22 alone until the sentence “the cited route got faster at the same rate, and the pull request says so” has happened on two different repos.

If a feature’s demo requires a number the ledger does not store, it does not go on the page. The page catches up to the run. It does not get ahead of it.

---

## 6. Browser check when you do build U1

After U1–U3, with `loadline dashboard --serve` and a run that has `verification.json`:

- Open the index, open the run, read the verdict without scrolling.
- Confirm the before and after rates are identical and match `experiments/<id>.json`.
- Open a second run that never verified. Confirm there is no after column.
- Open a `policy_refused` run once U7 exists. Confirm the docker.sock sentence is the headline and there is no chart.
- Narrow the window to a phone width. The table scrolls or stacks. The verdict remains text, not a clipped serif overflow.
- Keyboard: Cmd/Ctrl-K opens the palette, Escape closes it, Enter jumps.

A single screenshot of the hero is not this check.
