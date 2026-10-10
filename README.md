# Loadline (NeatHacks)

**Loadline** boots a repo’s app in Docker, load-tests the HTTP APIs, and runs an **Investigator** agent that reads the code and writes an evidence-backed report (or a clear **blocked** reason).

There are **two commands** teammates care about:

| Command | One line |
|---------|----------|
| **`loadline load`** | “Can we boot this repo? Save the boot config.” |
| **`loadline run`** | “Boot it, investigate under load, write the report.” |

`run` does **not** call `load`. You run `load` yourself when you want a saved config before a full run.

---

## Step 0 — your `.env` (Loadline on your laptop)

Before either command, set up **this repo’s** `.env` (copy from `.env.example`). That is **not** the app under test; it is **keys and settings for Loadline**:

- **LLM:** `LOADLINE_MODEL` plus `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` (required for `loadline run`, not for `load` today).
- **Optional:** `NEATLOGS_*` for traces.

Check: `uv run loadline doctor` (add `--check-model` before a real `run`).

The **target app’s** env (Compose, `.env` for Postgres, test users, etc.) is what `load` / `run` figure out when they **boot**—see below.

---

## Workflow: `loadline load`

**Goal:** Prove the repo can boot and **write a small config file** so the next `run` does not have to guess as much. **No LLM investigator. No `report.md`.**

```bash
uv run loadline load /path/to/app-repo
# optional: also copy config into the repo
uv run loadline load /path/to/app-repo --write-to-repo
```

### What happens (steps)

1. **Docker check** — Is the daemon up? If not → `blocked`, stop.
2. **Discover** — Is there a `docker-compose` file or Dockerfile? If neither → `blocked`, stop.
3. **Resolve** — Pick compose file, app service, container port, health path (from repo layout + optional `.loadline.yaml` hints). If Loadline cannot pick a single HTTP app → `blocked`, stop.
4. **Trial boot** — Start the stack, wait until health checks pass, then **tear it down** (`teardown=True`). This boot is thrown away; it is only a proof.
5. **Write config** — Save `loadline.yaml` under Loadline’s home dir (`LOADLINE_HOME/configs/...`). With `--write-to-repo`, also write `.loadline.yaml` in the app repo.

Output is a path like `wrote .../loadline.yaml`, not a performance report.

### Setup agent (planned, not the default path today)

Today, `load` is **deterministic** (steps above only).

We plan a **setup agent** for repos where boot is ambiguous—for example login/auth not described, or unclear “prepare” commands (migrations, seed scripts). That agent would loop with its own small tools (`check_config`, `try_boot`, `write_config`), still **without** running the Investigator or k6 experiments. `loadline run` will **never** call that agent; only `load` will.

Until that lands, use `load` for the trial boot + saved yaml, or hand-edit `.loadline.yaml` when you already know the service/port/health path.

---

## Workflow: `loadline run`

**Goal:** Boot the app **for real**, run the **Investigator** agent, save **`report.md`**, then clean up Docker.

```bash
uv run loadline run /path/to/app-repo
```

### What happens (steps)

1. **Preflight** — Confirm model API keys are set. Missing key → exit before Docker.
2. **Boot** — `boot_and_prepare`: start Compose (using hints, repo `.loadline.yaml`, and/or saved config from `load`). Wait until the app is healthy. Stack **stays running** for the next phase. Failure → **blocker** printed, artifacts under `run_dir`, teardown as needed.
3. **Investigate** — Investigator **agent loop** (see next section). Uses the booted network and only allowed internal hosts.
4. **Report** — The agent’s **last message** is written to `report.md` (and minimal `report.json`). Printed to the terminal unless you pass `--no-report-print`.
5. **Teardown** — Stop containers/networks/volumes labelled for this run.

Optional: `loadline dashboard` / `loadline dashboard --serve` to browse past runs after you have some `run_dir`s.

---

## Investigator agent loop (`loadline run` only)

After boot, one **Pydantic AI** agent runs with **three tools**. This is the “main loop” for capacity investigation.

**Starting prompt (idea):** *The app is booted. Find which endpoints break under load and why, using code and `run_k6`. Your last message is the report.*

### Repeat until the model stops or hits limits

```text
┌─────────────────────────────────────────────────────────┐
│  Agent thinks: which endpoint? what rate? what code?    │
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│  Calls exactly one tool:                                │
│    • repo          • read_file        • run_k6          │
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│  Loadline runs the tool and returns JSON (metrics,      │
│  snippets, graph text, or an error).                    │
└───────────────────────────┬─────────────────────────────┘
                            ▼
                    (loop again)
                            ▼
┌─────────────────────────────────────────────────────────┐
│  Final assistant message → saved as report.md           │
└─────────────────────────────────────────────────────────┘
```

### The three tools (plain English)

| Tool | Use when the agent wants to… |
|------|------------------------------|
| **`repo`** | **Search and navigate code** via Entire Graph (`search`, `def`, `neighbors`, `impact`) or list **`routes`** found in the repo. Ripgrep may back up search if the graph is degraded. |
| **`read_file`** | **Read a line range** from app source in the target repo (for citations in the report). Secret paths like `.env` are refused. |
| **`run_k6`** | **Run one short load experiment**: pick endpoints, a fixed **rate** (req/s), and **duration**. Loadline compiles and runs **k6**, then returns per-operation latency and error metrics. Each call is one experiment—not one long ramp. |

Prompt: `agents/investigator_prompt.md`. Tools: `loadline/investigator/tools.py`.

---

## What is k6?

**[k6](https://k6.io)** is a standard **HTTP load generator**. At a chosen **arrival rate** it sends many requests for a fixed time and records latency and failures.

Loadline does **not** let the model write free-form k6 scripts. The agent only passes a structured plan to **`run_k6`**; Loadline compiles and runs k6 (often in Docker on the same network as the app) and returns numbers the agent can compare across experiments.

**k6 = measurements. Investigator = read code + explain what the numbers mean.**

---

## Typical teammate order

```text
1. uv sync && cp .env.example .env   # your LLM keys
2. uv run loadline doctor --check-model
3. uv run loadline load ./app-repo   # optional but good on a new repo
4. uv run loadline run ./app-repo    # boot → agent loop → report.md
```

---

## Where things live in the repo

| Topic | Path |
|-------|------|
| CLI | `loadline/cli.py` |
| `run` pipeline | `loadline/run_pipeline.py` |
| `load` command | `loadline/load/` |
| Investigator | `loadline/investigator/` |
| k6 compile/run | `loadline/adapters/generator/` |
| Dashboard UI | `loadline/ui/`, `loadline/dashboard/` |
| Product summary | `mvp.md` |

**Partners (hackathon):** Entire (code graph for `repo`), neatlogs (optional tracing), cfo.ai (business plan only).
