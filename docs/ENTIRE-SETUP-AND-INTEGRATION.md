# Entire & neatHack — development setup vs in-product integration

**Last updated:** 2026-10-10 (IST)  
**Repository:** [github.com/aarush323/NeatHacks](https://github.com/aarush323/NeatHacks) · Entire UI: `https://entire.io/gh/aarush323/NeatHacks`  
**Event sources:** [neatHack](https://neatlogs.com/hackathon) · [Entire @ neatHack 2026](https://hack.entire.io/neathacks-2026/)

This document separates two concerns that judges also separate:

| Layer | Purpose | Who uses it | Hackathon evidence |
|-------|---------|-------------|-------------------|
| **A. Dev toolchain** | Capture *how we built* Loadline in Cursor; checkpoints on git commits; optional graph-assisted coding | Humans + Cursor | Entire checkpoint URL, Sessions on a commit, “Best Use of Entire” creativity |
| **B. Product runtime** | Loadline agent calls `entire graph …` as **tools** while diagnosing a failing API | `loadline` CLI at runtime | `docs/entire/*` artifacts, graph spans in neatlogs traces |

Both are required for the **25% partner** bucket: build/improve with Entire **and** show Entire (or graph output) **in** the product story.

---

## A. Entire for our development (status on this machine)

### A.1 What is already done (2026-10-10)

| Step | Command / artifact | Status |
|------|-------------------|--------|
| Entire CLI | `curl -fsSL https://entire.io/install.sh \| bash` → `~/.local/bin/entire` **v0.11.4** | Done |
| Graph plugin | `entire plugin install graph` → **v0.4.0** | Done |
| Git remote | `origin` → `https://github.com/aarush323/NeatHacks.git`, branch `main` | Done (local only; **not pushed**) |
| Enable Cursor | `entire enable --agent cursor` | Done → `.entire/settings.json`, `.cursor/hooks.json` |
| Graph agent instructions | `entire graph init-agents --repo .` | Done → `.entire/graph-agent.md`, blocks in `AGENTS.md` / `CLAUDE.md` |
| Doctor | `entire graph doctor --json` | Pass (local-only, no egress) |

**PATH:** ensure `export PATH="$HOME/.local/bin:$PATH"` in shell profile (install script may have added completion to `~/.bashrc`).

### A.2 What you already did in Entire Cloud (builder)

- Sign in with GitHub on [entire.io](https://entire.io).
- Connect repository **aarush323/NeatHacks** (shows as `/gh/aarush323/NeatHacks`).

**Personal repos:** the hackathon guide’s “org admin import” step applies to **organizations**. For a user-owned repo, connecting the repo in Entire after GitHub App install on your account is sufficient. If the repo is missing in the UI for up to an hour after first push, wait for sync or re-check GitHub App permissions on `aarush323/NeatHacks`.

### A.3 Checkpoint workflow (dev) — after first local commit

Entire needs **at least one git commit** before session import and reliable checkpoints.

```bash
cd /home/aarush_linux/projects/neathacks
export PATH="$HOME/.local/bin:$PATH"

# 1. Work in Cursor (hooks capture sessionStart/stop, beforeSubmitPrompt, etc.)
# 2. Stage and commit — when prompted, link commit to session (yes)
git add <files>
git commit -m "feat: ..."

# 3. Inspect
entire checkpoint list
entire checkpoint explain HEAD
entire status   # should show sync to origin after push

# 4. Share with judges (after push, public repo)
# https://entire.io/gh/aarush323/NeatHacks/commit/<FULL_SHA>
```

**Push policy:** push when ready for Entire cloud sync and hackathon “commits during event” evidence. This workspace intentionally has **no push yet**.

**Optional later:** `entire import cursor` once HEAD exists (CLI noted history import was skipped until anchor commit).

### A.4 Using Entire Graph while *coding* (not Loadline runtime)

Cursor is instructed (via `AGENTS.md` + `.entire/graph-agent.md`) to run graph CLI **before** grepping:

```bash
entire graph search --repo . --profile full --query "<task in one sentence>"
entire graph def --repo . --symbol <name>
entire graph neighbors --repo . --symbol <name> --relation CALLS --direction out
entire graph impact --repo . --symbol <name>
```

Warm index once per session or in doctor:

```bash
entire graph index --repo . --profile full
```

**Do not** run `entire graph stats` in agent loops (reads local coding transcripts; human-only per `design/13-entire-across-product.md`).

### A.5 Optional Entire features (hackathon)

| Feature | When to use | Loadline relevance |
|---------|-------------|-------------------|
| **Checkpoints** | Every meaningful commit during the build | Primary judge evidence |
| **entire-graph** | Dev + product (`loadline/tools/graph.py`) | Required |
| **Entire Brain** | Cross-session memory, MCP | Stretch; install via [get-brain.sh](https://github.com/entireio/entire-brain) only if time |
| **Trails** | PR-backed agent CI | Feature-flagged; skip unless enabled by Entire team |
| **Agentic Search** | Cloud search over pushed sessions | After push; complements local graph |

**Prize:** “Best Use of Entire” — creative use of Checkpoints, Graph, or Brain ([hack guide](https://hack.entire.io/neathacks-2026/)).

### A.6 neatlogs for our development

**Done 2026-10-10:** `pyproject.toml`, `uv sync`, `loadline/neatlogs_setup.py`, `loadline-neatlogs-probe`, `docs/NEATLOGS-SETUP.md`. Local doctor and MODEL-RT pass without API key.

Remaining (you):

1. `cp .env.example .env` and set `NEATLOGS_API_KEY` from [app.neatlogs.com](https://app.neatlogs.com).
2. `uv run loadline-neatlogs-probe --hosted` and `uv run python -m neatlogs doctor --probe --json`.
3. Wire `init_neatlogs()` + `neatlogs.wrap(Agent)` into `loadline run` at M7.
4. Evidence: two **live** traces (before/after improvement), links in `docs/neatlogs/` or submission doc.

FAQ explicitly encourages using neatlogs **throughout development** ([hackathon FAQ](https://neatlogs.com/hackathon)).

### A.7 cfo.ai (business, not runtime)

Signup at [cfo.ai/neathacks](https://cfo.ai/neathacks); cancel billing immediately after signup per event page. Export business plan (pricing, costs, revenue, runway) into `docs/cfo-plan.pdf` or linked artifact for submission.

---

## B. Entire inside Loadline (application)

Specified in `tech_doc.md` §5.3 and §11.3. Entire is optional. Without it, ripgrep and `read_file` still work and code intelligence is `degraded`.

### B.1 Architecture

```
User → loadline run → Investigator (seven tools)
                          ├─ search_code, code_graph → EntireGraphProvider and ripgrep
                          ├─ read_file, inspect_runtime
                          ├─ declare_hypothesis, run_experiment, record_finding
        neatlogs.wrap(Agent) → traces
        code writes the report from the ledger
```

Entire is **never** a shell for the model. Only `loadline/adapters/codeintel/entire.py` builds argv, caches stdout under `runs/<run_id>/graph_cache/`, and returns capped JSON to the tools.

### B.2 Tools

The Investigator has seven tools (`tech_doc.md` §11.3). Two reach Entire: `search_code` (`entire graph query`, or `search` only as a recorded alias, plus ripgrep) and `code_graph` (`def`, `neighbors`, `impact`, and `HANDLES_ROUTE` only when capabilities list it and S-ENTIRE confirmed it). Flags come from `capabilities --json` and `--help`. Never run `verify`. An empty result is not proof a call is absent. Without Entire, ripgrep and `read_file` answer and the capability is `degraded`. Only `read_file` ranges satisfy the code-located check.

### B.3 Intake path (no LLM)

`loadline analyze` records Entire's version and capabilities. Route-to-handler links come from `HANDLES_ROUTE` only when that relation is listed and S-ENTIRE confirmed it for the language. Otherwise the handler is unknown until ripgrep and `read_file`. File specs stay a separate provenance. The graph cache is `runs/<id>/graph_cache/`.

### B.4 Fix path

Not in this build. Findings carry remediation text (`tech_doc.md` §13). The Investigator does not run `entire graph diff`.

### B.5 Dev vs product Entire — same binary, different callers

| Caller | Invokes |
|--------|---------|
| Cursor, while building Loadline | the commands in §A.4. Those examples are for the coding agent, not for the Loadline adapter. |
| `loadline` | `entire graph query` (or the recorded alias), `def`, `neighbors`, `impact`, under `tech_doc.md` §5.3 |

### B.6 First-hour verification (product)

Spike S-ENTIRE (`implementation.md` S0). On 4–5 repos, record `capabilities --json`, whether `query` or `search` exists, whether `--worktree` exists, whether `edges` is NDJSON, and whether `HANDLES_ROUTE` maps an operation to a handler per language. Do not freeze a flag the installed `--help` does not list.

### B.7 Submission checklist (Entire slice)

- [ ] Public repo with hackathon-dated commits  
- [ ] Checkpoint URL: `https://entire.io/gh/aarush323/NeatHacks/commit/<SHA>`  
- [ ] `docs/entire/`: version, search, neighbors, impact, snapshot or size note  
- [ ] Demo video: checkpoint + `code_graph`/`search_code` answered by Entire in a live `loadline run`  
- [ ] neatlogs trace showing those TOOL spans with `loadline.adapter=entire`  

---

## C. Build order (recommended)

1. **Now (pre-12:30):** Entire dev setup (this doc §A) — **done** except first commit/push.  
2. **M0:** `pyproject.toml`, `loadline doctor` (Entire + neatlogs lines).  
3. **M1:** neatlogs wrap + MODEL-RT.  
4. **P2–P7 (`implementation.md`):** Entire code-intelligence adapter per §B, after spike S-ENTIRE.  
5. **Before submit:** push `main`, verify `entire status`, capture checkpoint links, record two neatlogs traces.  

---

## D. Files to commit together (Entire dev config)

When making the **first** commit (tooling only is OK before 12:30 PM product code):

- `.entire/settings.json`, `.entire/graph-agent.md`, `.entire/.gitignore`
- `.cursor/hooks.json` (Entire Cursor hooks)
- `AGENTS.md`, `CLAUDE.md` (managed graph blocks)
- `docs/ENTIRE-SETUP-AND-INTEGRATION.md`, updated `kickoff.md` / `hackathon.md`

Do **not** commit `.entire/logs/`, `.env`, or API keys.
