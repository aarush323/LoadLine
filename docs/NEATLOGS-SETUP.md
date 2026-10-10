# neatlogs setup (Loadline)

**Refs:** [Python SDK](https://docs.neatlogs.com/sdk/python) · [Pydantic AI](https://docs.neatlogs.com/integrations/pydantic-ai) · [Wizard alternative (this path)](https://docs.neatlogs.com/docs/quickstart/wizard) · contract in `tech_doc.md` §14.

## Stuck on “Send your first trace” / Settings locked?

Neatlogs **onboards in this order**:

1. You land on a page that says something like **“Send your first trace”** and **“Connect your app below”**.
2. **The ingest API key is on that page** (Copy / Reveal / inside the sample code block) — **not** under Settings yet.
3. After the first trace arrives, Settings (including API Keys) unlocks.

So you are **not** supposed to open Settings first. Scroll the onboarding / connect screen until you see **Project API key** (or similar) and copy it into `.env`:

```bash
NEATLOGS_API_KEY=paste_what_you_copied
```

Then from this repo:

```bash
uv run send-first-trace
```

Alternative (same idea): `uv run python -m neatlogs doctor --probe --json`

If the onboarding page truly shows **no** key anywhere, use **Node 20+** once (not TypeScript in your app): `npx @neatlogs/wizard@latest` — it can walk sign-in and instrumentation ([wizard docs](https://docs.neatlogs.com/docs/quickstart/wizard)). Or ask in [neatlogs Discord](https://neatlogs.com/discord) / neatHack support — this is a product onboarding gap, not something you fix in Python code without a key.

## You do **not** need TypeScript in this repo

The hackathon paste that shows:

```text
NEATLOGS_API_KEY=<your-project-api-key>
```

is a **placeholder**. Do **not** paste that string as the key.

| Goal | What to use |
|------|-------------|
| **Get an ingest API key** | Browser only: [app.neatlogs.com](https://app.neatlogs.com) → project **e5d97cf1-860e-4b1e-86da-ac908a8c3a3f** → **Settings → API Keys** → copy key ([wizard docs](https://docs.neatlogs.com/docs/quickstart/wizard) say the same). |
| **Auto-instrument the repo** | Optional: `npx @neatlogs/wizard@latest` (needs **Node ≥ 20**, not TypeScript in your app). We already did manual Python setup below. |
| **CLI to list traces / create keys** | Optional: [neatlogs-cli](https://docs.neatlogs.com/cli) (`npm install -g neatlogs-cli@0.2.0`) + `neatlogs auth login`. |

This project is **Python + Pydantic AI** only. Instrumentation lives in `loadline/neatlogs_setup.py` and `loadline/neatlogs_probe.py`.

### Stack (Step 2 summary)

- **One service:** repo root `loadline` package (`pyproject.toml`).
- **LLM entry points (workflow names):**
  - `capacity-investigation` — future `loadline run` (CLI one-shot).
  - `tracing-self-test` — `uv run loadline-neatlogs-probe` (bootstrap).
- **Framework:** Pydantic AI via `neatlogs.wrap(Agent(...))` only ([integration guide](https://docs.neatlogs.com/integrations/pydantic-ai)).
- **Ingest:** `NEATLOGS_ENDPOINT=https://ingest.neatlogs.com` (US).

## 1. Install

```bash
cd /home/aarush_linux/projects/neathacks
uv sync
```

## 2. API key (browser)

```bash
cp .env.example .env
```

1. Sign in at [app.neatlogs.com](https://app.neatlogs.com).
2. Open project `e5d97cf1-860e-4b1e-86da-ac908a8c3a3f`.
3. **Settings → API Keys** → create or copy an **ingest** / SDK key.
4. Put the real value in `.env` as `NEATLOGS_API_KEY=...` (no quotes required unless the shell needs them).

EU project: use [eu.app.neatlogs.com](https://eu.app.neatlogs.com) and set `NEATLOGS_ENDPOINT=https://eu.ingest.neatlogs.com`.

## 3. Doctor

**Local (no key):**

```bash
uv run python -m neatlogs doctor --local --json
```

**Hosted (after key in `.env`):**

```bash
uv run python -m neatlogs doctor --probe --json
```

## 4. MODEL-RT

**Local (no LLM cost, no export without key):**

```bash
uv run loadline-neatlogs-probe
```

**Export a trace (key + optional `LOADLINE_MODEL` + `OPENAI_API_KEY`):**

```bash
uv run loadline-neatlogs-probe --hosted
```

Then confirm in the Neatlogs dashboard under workflow **tracing-self-test**.

## 5. When `loadline run` ships

- `init_neatlogs(workflow_name="capacity-investigation", ...)`
- `neatlogs.wrap(agent)` inside `neatlogs.trace("loadline run", kind="WORKFLOW")`
- `shutdown_neatlogs()` on every CLI exit path

Tags: `neatHack`, `run_id:…`, `loadline_rev:…`, `fast:…` — no `session_id` in tags (see `tech_doc.md` §14).
