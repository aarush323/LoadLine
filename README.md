# Loadline

Loadline boots a target application in isolated Docker, generates HTTP load with [k6](https://k6.io), and runs an investigator agent that reads the repository and produces an evidence-backed capacity report—or a named blocker when the run cannot proceed.

Install from this repository (Python package; no PyPI release).

## Requirements

| Requirement | Notes |
|-------------|--------|
| [Python 3.12](https://www.python.org/) | `>=3.12,<3.13` per `pyproject.toml` |
| [uv](https://docs.astral.sh/uv/) | Dependency install and CLI entrypoint |
| [Git](https://git-scm.com/) 2.36+ | Target repos and [Entire](https://docs.entire.io/) graph indexing |
| [Docker](https://docs.docker.com/) + Compose v2 | Boot, k6 sidecars, labelled teardown |
| LLM provider credentials | Required for `loadline run` (`LOADLINE_MODEL` + matching API key) |

Optional: [neatlogs](https://neatlogs.com) ingest key for run traces (`NEATLOGS_*` in `.env`).

## Install and configure

```bash
git clone https://github.com/aarush323/NeatHacks.git
cd NeatHacks
uv sync
cp .env.example .env
```

Edit `.env` in this repo (not the application under test):

- `LOADLINE_MODEL` — Pydantic AI model id (e.g. `openai:gpt-4o-mini`, `anthropic:claude-sonnet-4-20250514`, or an OpenRouter id).
- Provider key matching the model — `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `OPENROUTER_API_KEY`.
- Optional: `NEATLOGS_API_KEY`, `NEATLOGS_ENDPOINT`.

Verify the environment:

```bash
uv run loadline doctor
uv run loadline doctor --check-model   # provider call; may incur billing
```

`doctor` does not install system packages or mutate the host. `doctor --cleanup` removes containers and networks labelled `loadline.run=*`.

## Commands

All paths below use `--repo` with an **absolute** path to the application repository.

```bash
uv run loadline load  --repo /absolute/path/to/app
uv run loadline run   --repo /absolute/path/to/app
uv run loadline dashboard
uv run loadline dashboard --serve --port 8123
```

| Command | Purpose |
|---------|---------|
| `loadline load` | Trial boot, resolve compose/service/health, write saved boot config. No investigator, no `report.md`. |
| `loadline run` | Boot for investigation, agent loop under load, write `report.md`, teardown. Does not invoke `load`. |
| `loadline dashboard` | Browse prior runs (TTY or `--serve` web UI). |

Common flags: `run --fast`, `run --verbose`, `load --write-to-repo`, `load --quiet`.

Detailed workflows: [setup.md](setup.md). Product scope: [mvp.md](mvp.md).

## What `loadline run` does

1. **Preflight** — Model and API key checks before Docker.
2. **Boot** — Start Compose (hints, `.loadline.yaml`, and/or config from a prior `load`). Wait for health; keep the stack up for experiments.
3. **Investigate** — Single [Pydantic AI](https://ai.pydantic.dev/) agent with a fixed tool surface (see below).
4. **Report** — Final assistant message written to `report.md` under `$LOADLINE_HOME/runs/<run_id>/`.
5. **Teardown** — Remove labelled containers, networks, and volumes for this run.

The agent does not patch the target repository or open pull requests; remediation stays in the report for engineers to implement.

## Investigator tools

| Tool | Role |
|------|------|
| `repo` | Code navigation via [Entire Graph](https://docs.entire.io/cli-reference/graph) (`search`, `def`, `neighbors`, `impact`) and route discovery; ripgrep fallback when graph coverage is degraded. |
| `read_file` | Line-bounded reads from app source for citations; secret paths refused. |
| `run_k6` | One structured load experiment per call—endpoints, fixed arrival rate, duration. Loadline compiles and runs k6 (pinned image) on the internal network and returns latency and error metrics. |

Prompt: `agents/investigator_prompt.md`. Implementation: `loadline/investigator/`.

k6 supplies measurements; the investigator interprets them against code. The model does not author arbitrary k6 scripts.

## What `loadline load` does

Deterministic pipeline: Docker check → compose/Dockerfile discovery → service and health resolution → trial boot with teardown → write `loadline.yaml` under `LOADLINE_HOME/configs/`. Optional `--write-to-repo` copies `.loadline.yaml` into the target repo.

Use `load` before `run` when you want a saved boot configuration on a new repository.

## Stack

| Component | Use in Loadline |
|-----------|-----------------|
| [k6](https://k6.io/docs/) | HTTP load generation (declarative plans, Docker execution) |
| [Entire](https://docs.entire.io/) | Repository code graph for the `repo` tool |
| [Pydantic AI](https://ai.pydantic.dev/) | Investigator agent runtime |
| [neatlogs](https://neatlogs.com) | Optional workflow tracing |
| Docker Compose | Target boot and sandbox networking |

## Repository layout

| Area | Path |
|------|------|
| CLI | `loadline/cli.py` |
| `run` pipeline | `loadline/run_pipeline.py` |
| `load` command | `loadline/load/` |
| Investigator | `loadline/investigator/` |
| k6 adapter | `loadline/adapters/generator/` |
| Run dashboard | `loadline/dashboard/`, `loadline/ui/` |
| Marketing site | `website/` |

## Typical sequence

```bash
uv sync && cp .env.example .env
uv run loadline doctor --check-model
uv run loadline load  --repo /absolute/path/to/app
uv run loadline run   --repo /absolute/path/to/app
```

Further evaluation targets and operator notes: [setup.md](setup.md).
