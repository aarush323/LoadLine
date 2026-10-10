# Loadline setup — one sheet

Everything you need to install Loadline, run it on a target repo, and run the **unreliable production service** blind evaluation. For product context, see [README.md](README.md) and [mvp.md](mvp.md).

---

## 1. Prerequisites

| Tool | Why |
|------|-----|
| **Git** 2.36+ | Repo + Entire Graph |
| **Docker** + Compose | Boot targets in isolation |
| **Python 3.12** | `pyproject.toml` pins `>=3.12,<3.13` |
| **[uv](https://docs.astral.sh/uv/)** | Install deps and run CLI |
| **LLM API key** | Investigator on `loadline run` (OpenAI, Anthropic, or OpenRouter) |

Optional: **Entire CLI** + graph plugin (code search in Investigator `repo` tool). **neatlogs** API key for traces (`NEATLOGS_*` in `.env`).

---

## 2. Install Loadline (this repo)

```bash
git clone git@github.com:aarush323/NeatHacks.git neathacks   # or your fork path
cd neathacks
uv sync
cp .env.example .env
```

Edit `.env` (never commit it):

```bash
# Pick one provider and matching model id, e.g.:
# LOADLINE_MODEL=openai:gpt-4o-mini
# OPENAI_API_KEY=sk-...

# Or OpenRouter:
# LOADLINE_MODEL=openrouter:deepseek/deepseek-v4.1-flash
# OPENROUTER_API_KEY=...

# Optional traces:
# NEATLOGS_API_KEY=...
# NEATLOGS_ENDPOINT=https://ingest.neatlogs.com
```

Sanity check:

```bash
uv run loadline doctor
uv run loadline doctor --check-model   # before first paid run
```

Unit tests (optional):

```bash
uv run pytest tests/unit -q
```

---

## 3. The three CLI commands

All commands run from the **Loadline repo root** with `uv run`.

### `loadline load` — boot config only (no investigator)

Writes `loadline.yaml` under `LOADLINE_HOME` after discover → resolve → **trial boot** (then tear down). Progress on stderr; use `--quiet` to hide it.

```bash
export LOADLINE_HOME="${LOADLINE_HOME:-$HOME/.local/share/loadline}"   # optional; default if unset

uv run loadline load --repo /absolute/path/to/target-repo
uv run loadline load --repo /absolute/path/to/target-repo --write-to-repo   # also .loadline.yaml in repo
```

`run` does **not** call `load`. Use `load` when you want a saved boot config before a full investigation.

### `loadline run` — full pipeline (boot → investigator → report)

```bash
uv run loadline run --repo /absolute/path/to/target-repo
uv run loadline run --repo /absolute/path/to/target-repo --fast      # shorter k6 phases (dev/regression)
uv run loadline run --repo /absolute/path/to/target-repo --verbose   # more boot + tool trace on stderr
uv run loadline run --repo /absolute/path/to/target-repo --no-report-print
```

Artifacts: `$LOADLINE_HOME/runs/<run_id>/` — `report.md`, `report.json`, ledger, k6 outputs. stderr prints `run_dir:` and `report:` when done.

Cleanup labelled Docker objects after a run:

```bash
uv run loadline doctor --cleanup
```

### `loadline dashboard` — browse past runs

```bash
uv run loadline dashboard                              # TTY picker
uv run loadline dashboard --run <run_id_or_prefix>
uv run loadline dashboard --repo unreliable-blind      # filter by path substring
uv run loadline dashboard --serve --port 8123          # local web UI
uv run loadline dashboard --serve --no-browser
uv run loadline dashboard --run <id> --export out.html
uv run loadline report show "$LOADLINE_HOME/runs/<run_id>" --dashboard
```

---

## 4. Reference targets (what works today)

### Unreliable production service (primary integration / blind eval)

Upstream: [Diagnose-and-Fix-an-Unreliable-Production-Service](https://github.com/mitanshu57/Diagnose-and-Fix-an-Unreliable-Production-Service)

**In-tree blind copy (no README in root — use for eval):**

```text
/home/aarush_linux/projects/neathacks/integration/targets/unreliable-blind
```

(Adjust if your clone lives elsewhere; use an **absolute** `--repo` path.)

**First product run (no hints, no manual boot, no external k6):**

```bash
cd /home/aarush_linux/projects/neathacks
set -a && source .env && set +a
export LOADLINE_HOME="/tmp/loadline-unreliable-$(date +%s)"

uv run loadline run --repo /home/aarush_linux/projects/neathacks/integration/targets/unreliable-blind
```

Optional beforehand (same target, saves boot config only):

```bash
uv run loadline load --repo /home/aarush_linux/projects/neathacks/integration/targets/unreliable-blind
```

Keep **`FIX_ENABLED=false`** (buggy path) for the **first** blind run. Do not patch Loadline or the target mid-run.

### FastAPI full-stack template (expected policy blocker)

Pinned under `integration/targets/full-stack-fastapi-template/` (clone per [integration/TARGET.md](integration/TARGET.md)).

Traefik mounts `docker.sock` → Loadline **`policy_refused`** (exit **10**). That is an honest blocker, not a Loadline bug. See [integration/RESULTS.md](integration/RESULTS.md). Do not expect a full report on the stock pin without upstream compose changes (out of scope for “make this one repo pass”).

```bash
uv run loadline run --repo /home/aarush_linux/projects/neathacks/integration/targets/full-stack-fastapi-template --fast
```

### Small regression fixture (CI-style)

```bash
uv run loadline run --repo /home/aarush_linux/projects/neathacks/tests/fixtures/fx-pyhttp-pg --fast
```

### HoH (team app — target repo must expose HTTP in Compose)

**Boundary:** Loadline does not special-case HoH. If Compose had only Kafka/Postgres/Cassandra, Loadline correctly blocked with *no application service*. The **HoH repo** adds an `api` service (`Dockerfile` + `GET /health`) so boot/load/run can proceed. See `docs/LOADLINE.md` in the HoH tree.

```bash
uv run loadline load --repo /home/aarush_linux/projects/HoH
uv run loadline run --repo /home/aarush_linux/projects/HoH --fast
```

First image build is slow (ML stack). Pre-build: `docker compose -f /home/aarush_linux/projects/HoH/docker-compose.yml build api`.

---

## 5. Blind evaluation protocol (unreliable service)

**Objective:** Test whether Loadline’s **single Investigator** finds a real scalability failure from repo knowledge, k6, and code — **without** redesigning Loadline during the first run.

### 5.1 Prepare a blind target (fresh clone)

If you are not using the in-tree `unreliable-blind` copy:

1. Clone upstream into a **temporary** directory (not inside Loadline’s git tree if you want a clean eval log).
2. Create a **blind copy**: same app source, Dockerfile, Compose, DB init, downstream stub, observability — but **remove** README and any doc that reveals the injected failure and root cause.
3. Keep **buggy** config: **`FIX_ENABLED` must not be `true`**.
4. Do **not** give the Investigator the root cause, endpoint shortlist, rates, or diagnosis.
5. Do **not** manually boot, run the repo’s bundled load generator, add `.loadline.yaml`, or run k6 outside Loadline before the first eval.
6. Re-init git in the blind copy if Entire needs it.

Example sketch (paths are yours):

```bash
EVAL=/tmp/loadline-eval-$$
git clone https://github.com/mitanshu57/Diagnose-and-Fix-an-Unreliable-Production-Service.git "$EVAL/upstream"
cp -a "$EVAL/upstream" "$EVAL/blind"
rm -f "$EVAL/blind/README.md" "$EVAL/blind/"*.md   # and any other spoiler docs
# verify FIX_ENABLED is false in compose/env
cd "$EVAL/blind" && git init && git add -A && git commit -m "blind eval copy"
```

### 5.2 Run the current product

From Loadline:

```bash
cd /home/aarush_linux/projects/neathacks
set -a && source .env && set +a
export LOADLINE_HOME="/tmp/loadline-blind-$(date +%s)"

uv run loadline run --repo "$EVAL/blind"
```

Capture: **run id**, `run_dir`, `report.md`, ledger, k6 artifacts, neatlogs trace (if configured).

If a short k6 experiment **hangs** well past its requested duration: inspect Docker/k6 subprocess, stop safely (`docker ps`, `loadline doctor --cleanup`), record as **runner failure** — not an app finding. Do not retry the same hang for ten minutes. Do not patch Loadline or the target until the first run is fully archived.

### 5.3 What the Investigator should discover (acceptance)

Independently, as far as evidence allows:

- Real routes; **`GET /widgets/{id}`** as meaningful work, not only health.
- Entire / `read_file` on handler and call path.
- Valid k6 requests; rates changed from observations (not a fixed script you fed it).
- Degradation from per-operation latency, status counts, offered vs achieved RPS.
- Distinguish app degradation from generator/infra limits.
- Mechanism with **source locations** and experiment ids.
- Honest limits; no fabricated numbers; no “bottleneck” from 404/401 alone.

### 5.4 Oracle check (after first run is preserved)

Only **after** archiving the first run, read upstream docs/source. Known failure: **DB pool exhaustion** — connection held during slow downstream HTTP; pool size 5; queue/timeouts under concurrency.

Pass requires evidence linking **hold time**, **downstream await**, **pool pressure**, and **measured degradation** — not a vague “database slow.”

If the first run is credible and reliable, a **separate** copy with **`FIX_ENABLED=true`**: same workload shape, check symptom improvement. Do not rewrite the first report or feed the oracle into that run.

### 5.5 Final evaluation report (human)

Record:

- Boot/setup success or blocker.
- Endpoints discovered vs load-tested.
- Real k6 rates, latency, errors, generator notes.
- Whether diagnosis matches oracle with code citations.
- Whether report matches ledger/artifacts.
- Root cause of each failure (Loadline vs target vs app).
- Smallest next fix if Loadline failed.

Success = evidence-backed discovery of the intended failure, **or** a precise statement of where the product stopped. Not “booted” or “report exists” alone.

Append results to [integration/RESULTS.md](integration/RESULTS.md) when you finish a formal eval.

---

## 6. Environment variables (quick reference)

| Variable | Purpose |
|----------|---------|
| `LOADLINE_MODEL` | Pydantic AI model id for investigator |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY` | Provider for `LOADLINE_MODEL` |
| `LOADLINE_HOME` | State dir (default `~/.local/share/loadline`) |
| `NEATLOGS_API_KEY` | Optional trace export |
| `LOADLINE_SKIP_INVESTIGATOR` | `1` to boot-only test (integration) |

Target repos may have their own `.env` (e.g. Postgres passwords). Loadline boots those via Compose; do not commit target secrets into Loadline’s repo.

---

## 7. Troubleshooting

| Symptom | Action |
|---------|--------|
| Exit **2** before Docker | Set model key + `LOADLINE_MODEL`; `loadline doctor --check-model` |
| Exit **10** `policy_refused` | Host bind mount (often FastAPI Traefik); see §4 |
| Stuck on `load` / boot | Watch stderr progress; `docker ps`; first pull can take minutes |
| Leftover containers | `uv run loadline doctor --cleanup` |
| Entire graph degraded | `loadline doctor`; Investigator still has ripgrep fallback |

More: [docs/ENTIRE-SETUP-AND-INTEGRATION.md](docs/ENTIRE-SETUP-AND-INTEGRATION.md), [docs/NEATLOGS-SETUP.md](docs/NEATLOGS-SETUP.md) if present.
