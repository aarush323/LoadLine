# Loadline — kickoff runbook (bootstrap + pre-kickoff)

**Authority:** [`tech_doc.md`](./tech_doc.md) · **Plan:** [`implementation.md`](./implementation.md) · **Open questions:** [`design/OPEN-QUESTIONS.md`](./design/OPEN-QUESTIONS.md)

### Official event times (reference only)

| | IST |
|--|-----|
| Web check-in opens | **8:00 AM**, 10 Oct 2026 |
| Hackathon / coding may begin | **12:30 PM**, 10 Oct 2026 |
| X quote submission | **12 Oct 2026, 7:00–11:55 PM** |

Pacing and stop-coding time are **your decision**, not this runbook.

---

## Pre-kickoff checklist (no product code)

| # | Action |
|---|--------|
| 1 | Luma registration; **same team name** for all members |
| 2 | Discord [neatlogs.com/discord](https://neatlogs.com/discord) |
| 3 | Web check-in when it opens (**8:00 AM IST** 10 Oct) |
| 4 | `NEATLOGS_API_KEY` → `.env` (never commit) |
| 5 | Choose `LOADLINE_MODEL` + matching provider API key |
| 6 | Docker Engine + Compose v2; **k6**; **Python 3.12** + **uv**; **git ≥2.36** |
| 7 | Read `tech_doc.md` (the contract) and `mvp.md` |
| 8 | **Entire CLI** + graph plugin (see `docs/ENTIRE-SETUP-AND-INTEGRATION.md`) |
| 9 | **cfo.ai** signup at [cfo.ai/neathacks](https://cfo.ai/neathacks); cancel billing immediately per event page |
| 10 | Read `implementation.md` for the build order and cut lines |
| 11 | Keep fixture oracles sealed from production code (`tech_doc.md` §18) |
| 12 | `export PATH="$HOME/.local/bin:$PATH"` so `entire` is on PATH |

---

## Bootstrap sequence (start at 12:30 PM IST or when you choose)

### 1. Repo and tooling

1. Remote `origin` → the team's public repo; branch `main`.
2. Confirm `entire status` shows Cursor enabled; first commit links the checkpoint.
3. `uv init`; dependencies from `design/12-oss-bom.md`; `uv sync`.
4. `.env` for keys; `.gitignore` includes `.env*`, `runs/`, `.venv`.
5. Create `tests/corpus/` (pinned unfamiliar repos, split **tuning / held-out**) and `tests/oracles/` (sealed). Held-out and sealed material is never used for tuning or read by `loadline/`.

### 2. Spikes (P0, `implementation.md`)

Run the spikes in `implementation.md` (S0). Record outcomes in `docs/spikes.md`. Do not start paid agent runs until S-NEATLOGS passes with a stub model.

### 3. Gates before building on a layer

- Do not run any repository's containers before the P3 sandbox tests (hostile plans, egress probe, teardown) pass.
- Do not treat any capacity number as valid before the verdict engine (P4) detects generator-limited and host-saturated cases on purpose-built stress.
- Do not write diagnosis skills that mention a fixture; `test_no_fixture_leakage` enforces it.

---

## Commands reference

```bash
uv run loadline doctor
uv run loadline analyze path/to/repo            # capability matrix, no execution
uv run loadline analyze path/to/repo --boot     # plan + boot + smoke, no load
uv run loadline run --repo path/to/repo --fast
uv run loadline dev ramp ...                    # deterministic low-level tooling for spikes/tests
make acceptance                                 # L1–L6 (scoped, no fix/verify)
```

## What not to do in bootstrap

- No harness swap; no MCP bridge; no custom load generator.
- No committing API keys.
- No tuning against held-out canaries; no reading sealed oracles from `loadline/` code.
- No special cases for a particular app, framework, route or port in core.

---

*Path: `/home/aarush_linux/projects/neathacks/kickoff.md`*
