# neatHack build log

Sources checked on 2026-10-10: [neatlogs.com/hackathon](https://neatlogs.com/hackathon). Canonical FAQ snapshot: `hackathon_knows.md`. Facts not on the live page are marked pending. This log does not establish eligibility.

Published event facts, as of 2026-10-10:

- neatHack is an online hackathon. Official schedule: **build October 10–12, 2026**; code must be written between start (October 10) and deadline (October 12). Kickoff call is 9:00 AM IST on October 10. Building starts 12:30 PM IST. Web check-in opens 8:00 AM IST.
- Planning beforehand is allowed. All code must be written between the start on October 10 and the deadline on October 12. Finished or half-built projects cannot be brought into the event.
- One track: "Build an agent that works (literally)." Example tasks are ideas, not separate tracks. One example is "Watch a running system."
- Every project must use neatlogs, Entire, and cfo.ai, each with a clear role. The demo must cover all three. neatlogs and Entire are for building and improving the agent. cfo.ai is for pricing, costs, revenue, and runway. The business plan goes in the submission.
- The project-local neathack skill does not impose those partner requirements. The live event page does.
- Come solo or in a team of 1–4. Every member registers on Luma with the same team name. Each person joins only one team.
- Registration: https://luma.com/s5blr882. Official chat: https://neatlogs.com/discord
- AWS credits: first 200 teams to complete web check-in. Dollar amount pending. Crustdata: 5,000 credits to everyone participating. Bedrock is listed as a building resource. Redemption steps pending.
- Dodo Payments credits are for the top three only. TheVibeFounder is the kickoff host. Neither is a required integration.
- This setup does not register, deploy, or submit the project.

## Project

The contract is `tech_doc.md`. `mvp.md` is the short form. `implementation.md` is the build order.

**Loadline** is the working name until the builder renames it. `loadline run` in a runnable repository discovers the system, boots it with Docker/Compose, load-tests it, investigates bottlenecks, and writes an evidence-backed report or a named blocker. It does not patch the repository, does not target production, and does not invent a result when it cannot proceed.

The problem: engineers with an unfamiliar service need a defensible capacity number and a code-grounded cause without hand-building load scripts, environments and telemetry. Also, when virtual users wait on the server, a slow target silently lowers the offered load, so the breaking point never shows up; Loadline uses an open-model arrival rate.

In scope (see `mvp.md` for tiers):

- Core platform with adapters for Docker/Compose runtime, HTTP workloads, k6, observability and code intelligence (fix/verify deferred), a policy engine (sandbox, target guard, experiment legality), an evidence ledger, and a report.
- k6 (external process or container, AGPL, unmodified) behind a generator adapter; open-model `constant-arrival-rate`.
- Python package and CLI; one Pydantic AI Investigator agent with seven tools (see `BRIEF.md`).
- Stack-independent telemetry (client, cgroups, host, generator, logs) plus optional dependency/app/profiler adapters.
- Findings that cite file and line only after `read_file` returns the range; confidence is a pure function of measured checks.
- Acceptance: three independent fixtures with sealed oracles, negative fixtures, a discovery corpus, held-out canaries, and metamorphic/no-leakage tests.

Out of the product:

- Hosted service, web UI, auto-merge, attaching to arbitrary running or production systems, a custom load generator, model-written load scripts.
- cfo.ai as a runtime tool (business plan only, produced in cfo.ai for submission).
- Any claim that every repository works.

In the product (partner + architecture):

- **Entire** as one code-intelligence adapter (`entire graph` subprocess) plus checkpoints during the build (`design/13-entire-across-product.md`).
- **neatlogs** via `neatlogs.wrap(Agent)` on all agents under one WORKFLOW trace.

## Team

Pending. No names or handles have been chosen for publication.

## Stack

**Repository (local git, not pushed):** [github.com/aarush323/NeatHacks](https://github.com/aarush323/NeatHacks) · Entire: `https://entire.io/gh/aarush323/NeatHacks`

**Dev toolchain (2026-10-10):** Entire CLI 0.11.4, `entire-graph` plugin 0.4.0, Cursor hooks enabled, graph agent instructions in `.entire/graph-agent.md`. See `docs/ENTIRE-SETUP-AND-INTEGRATION.md`.

**Application:** `pyproject.toml` + `loadline/` package for neatlogs bootstrap (2026-10-10). Full CLI/agent code still at kickoff. neatlogs SDK installed via `uv sync`; see `docs/NEATLOGS-SETUP.md`.

The builder named neatlogs project `e5d97cf1-860e-4b1e-86da-ac908a8c3a3f`. `NEATLOGS_API_KEY` is still unset. `.env.example` lists the variable name with an empty value. `.gitignore` ignores `.env` and `.env.*` except `.env.example`. The real key has not been written into the repo.

## Build log

### 2026-10-08 — Setup session (completed)

Completed:

- Read the workspace. It was empty: no README, agent instructions, source, git repository, or existing `hackathon.md`.
- Read the two published event pages listed above.
- Installed the neatHack build-log skill at `.cursor/skills/neathack/SKILL.md`. Cursor documents project skills at `.cursor/skills/`, so that path was used instead of `.agents/skills/`. Nothing was installed globally. No earlier skill file existed to preserve.
- Added `.gitignore` entries for env files.
- Created this log.

Not done, because there is no application to instrument:

- No language or framework integration.
- No SDK install.
- No tracing initialization.
- No sample trace was sent. No private or production data was sent.

Planned, not started: the agent itself, its stack, and neatlogs tracing. Those belong to the October 10–11 build window if this project is entered.

### 2026-10-08 — Pre-event setup continued (completed)

The builder asked to finish setup before the hackathon and to trace an agent. The published rule still says planning is allowed and project code must be written on October 10–11. This session did not add application code, an SDK, or a trace.

Completed:

- Re-read `.cursor/skills/neathack/SKILL.md`. Left it unchanged.
- Re-checked https://neatlogs.com/hackathon/1. Submission form, exact deadline, and timezone are still pending. The pre-event code rule is unchanged.
- Re-scanned the workspace. Still one service root with no manifest and no LLM, agent, or tool entry point. No second service from workspace config, compose, or nested manifests.
- Added `.env.example` with an empty `NEATLOGS_API_KEY`. Did not create `.env`.

Decisions not inferred:

- Project name, purpose, and problem: still pending.
- Team names or handles: still pending.
- Language and framework: still pending. Nothing was chosen on the builder's behalf.

Tests that ran:

- Environment check: `NEATLOGS_API_KEY` unset. The value was not printed.
- File and manifest search: no application entry point.

Blocked:

- SDK install and initialization: no Python, TypeScript, or Go service exists to instrument. Installing one now would be pre-event project code.
- Safe sample run and hosted probe: no app, no SDK, and no real API key. No request was sent to neatlogs. No private data was sent.

Failure that remains: the key block was the placeholder `<your-project-api-key>`. It was not stored. A real key still has to be copied from the neatlogs dashboard into an uncommitted `.env` or the shell.

### 2026-10-08 — Event page snapshot saved (completed)

The builder pasted the neatHack event page and asked for it to be saved. Completed: wrote `hackathon_knows.md` from that paste only. FAQ answers 02–08, evidence rows, and resource URLs were not in the paste, so they are marked missing there rather than filled in. No application code, SDK, trace, or submission.

### 2026-10-09 — Scope review (planned, not locked)

The builder shared a rough capacity-agent draft and asked for a simpler end-to-end scope, with evals removed. No application code was written.

Checked:

- Re-read `.cursor/skills/neathack/SKILL.md`. It is a build log. It does not require Entire or cfo.ai.
- Re-fetched https://neatlogs.com/hackathon/1. Partner tools, five judging weights, IST times, and the X quote-post submission are now published. `hackathon_knows.md` is marked stale.
- Composer research: [rules](fc83a63b-8bda-400f-8498-5b6af5ebae80), [sponsor tools](608d5cb9-9a80-45d4-9fc0-290d51bd1e7c), [scope cut](f114a91c-2ed7-4b37-bbbd-4c5b5fe8a3e2). The k6 researcher was aborted. Arrival-rate and license were then checked on Grafana's k6 docs and the grafana/k6 LICENSE file.
- k6 `ramping-arrival-rate` is documented as an open-model executor. Iterations start on a schedule while VUs are free. `dropped_iterations` counts iterations that could not start. The k6 license file is AGPL-3.0. Running the official binary as a separate process is the intended use. Vendoring or modifying k6 was not chosen.

Planning docs written the same evening, with no product code: `mvp.md` ([spec review](6bb7866f-5675-4950-b0ec-b80bb7d45376)), `harness-research.md` ([harness research](2e8704ab-ceff-46d9-98bc-01f6fe2b63f7)), and `pitch.md` ([pitch worker](dfdff927-1ca3-4970-944a-b05e68fff29a)). These are planning artifacts dated 2026-10-09. They are not evidence that code was written during the event.

Harness decision, 2026-10-09: Pydantic AI, one choice. Hermes, Pi, OpenAI Agents SDK, Claude Agent SDK, LangGraph, Google ADK, Strands, Agno, DSPy, smolagents, and a plain loop were compared in `harness-research.md` ([tech lead](ceb422be-0ee2-42c5-9fd6-b3ee9ad53957)). The design is in `tech_doc.md`, and `mvp.md` was tightened to match. Reference target flaws are locked: F1 N+1 on `GET /api/items`, F2 blocking sync DB work in an async `GET /api/items/{item_id}`, and D1 a verbose-logging decoy. Not verified by running anything yet. The Saturday first-hour spike either confirms tracing and the step cap or stops and asks the human.

Resolved 2026-10-10: live page schedule is build **October 10–12** with code deadline **October 12** (FAQ). Plan to the Oct 12 submission window.

Design swarm, 2026-10-09 evening, planning docs only and no code. Twelve stage docs are in `design/` (repo analysis, load model, environment, HLD/LLD, agent reasoning, diagnosis skills, reporting, fix agent, robustness, adversarial review, harness fact-check, open-source bill of materials). A consolidation pass produced the authoritative `tech_doc.md`, a tighter `mvp.md`, `kickoff.md` (first-hour runbook), and `design/OPEN-QUESTIONS.md`. Key decisions: Pydantic AI core as the only harness, k6 on the host with an open-model arrival rate, eight tools, two live neatlogs runs for the "agent improved" evidence, report as Markdown plus JSON only. The pasted outside harness analysis was fact-checked; its Locust, MCP bridge, and Pydantic AI Harness suggestions were rejected. Unproven and to be tested in the first hour: per-stage k6 metrics, Compose CPU limit enforcement, neatlogs tag format, Entire graph coverage of FastAPI routes. These docs are planning artifacts dated 2026-10-09, not evidence of code written during the event.

The builder then kept the product separate from the model, Entire, and cfo.ai. Locked plan: one Compose stack, one k6 script, one Python CLI, four tools, one snapshot, one report. The flaw is a Saturday-morning spike. Entire, cfo.ai, and the model provider stay outside that loop. Still pending: public name, team, and which flaw the spike keeps.

### 2026-10-09 — Harness and Entire scope (planned, not built)

The builder asked whether Pydantic AI plus a custom loop is enough, or whether the product should run on Pi or a heavier harness, and asked to document Entire with no gaps before the build window. No application code, SDK install, or trace.

Checked:

- [pi.dev](https://pi.dev/): Pi is a minimal MIT harness (extensions, skills, print/JSON, RPC, SDK, MCP, session tree). It does not ship a permission gate or sub-agents.
- [entire-graph CLI](https://docs.entire.io/cli-reference/graph): `search`, `def`, `neighbors`, `impact`, `snapshot`, `index`, `doctor`, `capabilities`, `diff`, `explain`. `verify` and `stats` are out of scope.

Decisions (plan only):

- Product runtime stays Pydantic AI. Pi is not adopted. Recorded in `design/00-topics.md` and the `tech_doc.md` decision log.
- Entire is used across doctor, analyze, four graph tools, a literal `search_text` fallback, and the fix stage. Recorded in `design/13-entire-across-product.md`. Investigation allowlist is 12 tools.
- Confidence cap stays 0.85 from `read_file`. Graph hits do not raise it. The skill draft’s 0.75 same-host cap is not the contract.

Not done: no `pyproject.toml`, no Entire binary check, no test run.

### 2026-10-09 — Agent context for virtual users (planned, not built)

Repo knowledge for sending load is the manifest `example_path`, not an Entire repo map. Entire graph tools run after a route fails. Presentation is four layers: static rules, a 1 500-character digest each turn, on-demand tools, and a wave observation after k6. Written to `design/14-agent-context.md`. No application code.

### 2026-10-10 — neatlogs bootstrap (completed)

Completed:

- `pyproject.toml` with `neatlogs[pydantic-ai]==1.4.26`, `pydantic-ai==2.54.0`; `uv sync` → `.venv`.
- `loadline/neatlogs_setup.py` (init tags per §14), `loadline/neatlogs_probe.py` + `loadline-neatlogs-probe` CLI.
- `docs/NEATLOGS-SETUP.md`; expanded `.env.example`.
- `uv run python -m neatlogs doctor --local --json` — pass.
- `uv run loadline-neatlogs-probe` — local MODEL-RT pass (TestModel).

Blocked on builder:

- `NEATLOGS_API_KEY` not in environment; no `.env` file yet. Hosted probe and `doctor --probe` pending key.

### 2026-10-10 — Hackathon docs, git remote, Entire dev setup (completed)

The builder asked to align docs with the live hackathon page, connect [NeatHacks](https://github.com/aarush323/NeatHacks), and complete Entire for development (without pushing).

Completed:

- Re-fetched [neatlogs.com/hackathon](https://neatlogs.com/hackathon): build **Oct 10–12**, submit **Oct 12 7:00–11:55 PM IST**, $19k prize pool, five judging weights unchanged. Rewrote `hackathon_knows.md` as canonical snapshot; archived Oct 8 paste in appendix.
- Wrote `docs/ENTIRE-SETUP-AND-INTEGRATION.md` (dev checkpoints vs Loadline `entire graph` tools).
- Installed Entire CLI **0.11.4** to `~/.local/bin`; `entire plugin install graph` **0.4.0**; `entire graph doctor --json` pass.
- `git init`, `origin` → NeatHacks, branch `main`. **No push.**
- `entire enable --agent cursor` → `.entire/settings.json`, `.cursor/hooks.json`.
- `entire graph init-agents --repo .` → `.entire/graph-agent.md`, `AGENTS.md`, `CLAUDE.md`.
- Updated `kickoff.md`, `.gitignore` (`runs/`, `.venv`), neathack skill URL.

Not done:

- First git commit (Entire checkpoints need one anchor; builder has not asked to commit yet).
- `git push` (explicitly deferred).
- neatlogs SDK / application code (still pre–12:30 PM product work).
- `entire import cursor` (waiting on anchor commit).

Tests that ran:

- `entire version`, `entire status`, `entire graph doctor --json` (local-only).

### 2026-10-10 — Product direction reset: repository-independent platform (planned, not built)

The builder issued a "product direction reset" after finding that the plan had overfit to one FastAPI + PostgreSQL reference stack. Direction: Loadline must work on an unfamiliar runnable repository with no hand-written load scripts, endpoint lists or database configuration; the reference application may demonstrate it, never cause it to work. No product code was written for this change; it is a documentation rewrite only.

Completed (docs only):

- Backed up the previous docs to `.archive-pre-reset/` (non-authoritative; the workspace has no history for the untracked files).
- Rewrote `tech_doc.md` as v3: core plus five adapter families, per-capability support levels with a fallback chain and named blockers, isolation tiers T0–T3 with an explicit "a container is not a complete boundary" statement, `SandboxPolicy`/`TargetGuard`, declarative workload plans, side-effect classes with write safeguards, stack-independent telemetry, hypothesis/prediction/experiment loop scored by code, six-boolean confidence, fix-and-verify with ABBA statistics, never-merge, fixtures/corpus/canaries/metamorphic acceptance.
- Rewrote `mvp.md`, `implementation.md` (dependency-ordered phases with gates and cut lines), `delivery.md`, `kickoff.md`, `pitch.md`, `design/00`–`13` and `design/OPEN-QUESTIONS.md`; lightly edited `harness-research.md` and `docs/ENTIRE-SETUP-AND-INTEGRATION.md`; replaced the old Locust-based product spec with a superseded stub; retired `design/14-agent-context.md`.
- Resolved cross-document conflicts (tool counts, CLI flags, exit codes, confidence rules, load engine). The list is in `design/10-review.md`.

**Scope lock, same day (12:49 PM IST):** the builder narrowed scope to five deliverables — point at a repo (reuse Docker config), run in isolation with Docker/Compose, generate and adapt load with k6 (specs, tests, source; smoke first), investigate agentically without recognising planted flaws, and an evidence-backed report. Fix & verify, the environment-planner agent, non-Docker runtimes, isolation above hardened Docker, non-HTTP protocols, write workloads and several experiment kinds are deferred. `mvp.md` and `implementation.md` were rewritten to match. Later the same day the build brief was merged into the body of `tech_doc.md`; that file is the contract.

**Contract folded into `tech_doc.md`, same day (13:18 IST, cleaned up after):** the build brief was merged into the body of `tech_doc.md`. That file is the only contract. Changes recorded there: a `baseline` stage and `investigation_incomplete` terminal state; no scripted/fallback policy; Investigator cut to seven tools with a four-section board; Entire Graph + ripgrep via `EntireGraphProvider`; Postgres-first dependency adapters; CPU-limit rule; one `[PROJECTED]` report section; git-history evaluation cases; corpus cut to 4–5 repos; no in-app EnvPlanner; one portable `loadline-run` Agent Skill after standalone `analyze --boot --json` is reliable. Investigator prompt saved at `agents/investigator_prompt.md`. Docs updated; no code written, no spike run.

Not done, and not claimed:

- No code, no spike has run, nothing was tested against any repository. Every capability, threshold and Tier is a plan.
- Coverage claims: none. Compatibility is to be measured on a corpus and held-out canaries; the contract says Loadline will not claim every repo works.
- The committed 2026-10-09 entries above describe the superseded scope and are kept as history.

## Demo

Pending. No demo URL or run instructions exist.

## Known limitations and next steps

- Scope was reset on 2026-10-10 to a repository-independent platform (`tech_doc.md` v3). It is a plan; no product code implements it yet.
- `NEATLOGS_API_KEY` is still unset. Tracing waits for the agent, which starts on October 10.
- The 2026-10-08 page paste no longer matches the live rules.

Next steps for the builder:

1. Answer the open questions in `design/OPEN-QUESTIONS.md`: model, fixture stacks and authorship, corpus and held-out canaries, isolation tier available for the demo, and the cfo.ai path.
2. Register, join Discord, and complete web check-in at 8:00 AM IST on October 10 if AWS credits matter.
3. Put the real neatlogs key in an uncommitted `.env`. Do not send it in chat.
4. Start the product at 12:30 PM IST on October 10.

## Submission

Confirmed on the live page as of 2026-10-09:

- One project per team, as a public quote post of the official neatlogs post on X. The Submit on X button appears during the window. Opening a draft does not submit.
- Window: October 12, 7:00–11:55 PM IST. Late submissions are not judged. Winners announced October 16.
- Quote post includes team, name, project, public repository, and demo link. Supporting evidence lives in the repository.
- Demo video of three minutes or less. It must cover neatlogs, Entire, and cfo.ai: architecture, implementation, runtime, reasoning, and result for each.
- Public repository. Judges must be able to verify commits made during the hackathon.
- Judging weights: the agent 30%, use of neatlogs, Entire, and cfo.ai 25%, demo video 20%, building in public 15%, usefulness and originality 10%.
- Evidence the page names: two neatlogs traces for "the agent improved"; trace links or screenshots; Entire checkpoints or entire-graph output; a cfo.ai business plan; a run that recovers from a failed action; public posts tagged #neatHack; commits dated during the hackathon.
- Cash: 1st $2,000, 2nd $1,000, 3rd $500, plus Dodo Payments credits of $5,000, $3,000, and $1,000. Community winner $500, scored separately. Each placed winner also gets 3 months of neatlogs Pro, listed as worth $1500. Prize pool on the page: $19,000 USD including credits.
- Community winner: genuine interest during the event. Follower count does not decide it. Bought likes or bots disqualify a team.
- Conduct: harassment, spam, or plagiarism means removal.

Outstanding:

- Official X post URL: pending until the submission window.
- AWS credit amount and redemption steps: pending.
- cfo.ai credit delivery: the page says the neatHack team provides credits directly. Signup may require a card, with instructions to cancel billing immediately. Exact credit steps pending.
- Contest repo: [aarush323/NeatHacks](https://github.com/aarush323/NeatHacks) (local only until push). Nothing submitted yet.

### 2026-10-08 — Setup validation (completed)

Verified:

- Workspace listing: empty except the files added in this session.
- `NEATLOGS_API_KEY` presence check only: unset. The value was not printed.
- Event pages fetched and used as the source for the facts above.

Blocked:

- Safe sample run of the app: no app, entry point, or dependency manifest exists.
- neatlogs SDK doctor, local or probe: no SDK is installed, because no Python, TypeScript, or Go service exists to instrument.
- Hosted trace check: blocked by the missing SDK and the unset API key. No request was sent to neatlogs.
