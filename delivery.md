# Loadline — delivery (install, first run, distribution)

How a developer gets Loadline onto a machine and points it at *their* repository. Engineering contract: [`tech_doc.md`](./tech_doc.md). This file does not change product behaviour.

---

## 1. Who the user is

Anyone with a git checkout of a runnable HTTP service on their own machine. They run `loadline`, which discovers the repo, boots it with Docker/Compose, load-tests it, investigates bottlenecks, and writes `runs/<id>/report.md`. It does not patch the repository.

Not the user: someone pasting production URLs, connecting a staging environment, or expecting a hosted service. Those are out of scope (§6). Loadline only ever targets the sandbox instance it creates for the run (`tech_doc.md` R6).

---

## 2. Install

Loadline is a **Python 3.12** CLI (Pydantic AI) that drives external mature tools. It is not a Node app.

### Prerequisites (installed by you; `loadline doctor` checks, does not install)

| Prerequisite | Why |
|--------------|-----|
| **Docker or Podman**, rootless preferred | runtime, sandbox, k6 container, probe container |
| **Pinned k6 image** | `doctor` checks the image. A host k6 binary is not required. |
| **git** ≥ 2.36 | read-only metadata |
| **Entire** CLI + graph plugin (optional) | code graph. Without it, ripgrep and `read_file` are used and code intelligence is degraded. |
| **LLM provider key** + `LOADLINE_MODEL` | the Investigator. Checked before any container starts. |
| `NEATLOGS_API_KEY` | traces (hackathon evidence) |
| ≥ 4 logical cores recommended | below that, doctor fails unless `--allow-low-cores` (figures then marked ceiling-limited) |

`loadline doctor` reports: tool versions, isolation tiers available, whether egress denial works, generator ceiling on this host, partner keys (masked), stray resources. Hard failures exit `2`.

### Installation paths

| Path | Notes |
|------|-------|
| `uv tool install 'loadline @ git+https://github.com/<org>/neathacks.git@<tag>'` | primary once tagged |
| `pipx install` from the same URL | alternative |
| clone + `uv sync` + `uv run loadline` | contributors and judges |
| Docker image of Loadline | rejected as primary: it must drive the host container runtime and weakens the isolation story |
| `npx` shim | rejected unless a tested shim is shipped |

### Trust paragraph (goes in the install README)

Loadline builds and runs the repository you point it at inside hardened Docker: no privileged mode, host mounts, `docker.sock`, host network or published ports; resource limits; an internal network with egress denied and checked; cleanup by label. A container is not a complete security boundary against malicious code. Only point Loadline at repositories you would build and run locally. The controls that were applied are printed and recorded.

---

## 3. First run

```bash
cd path/to/any/runnable/repo
loadline run --goal "Find scalability bottlenecks and improve throughput"
```

`--goal` is optional. No config, script, endpoint list or database specification is needed.

### What the user sees

1. **Discovery**: languages, frameworks, services, dependencies, interfaces, launch method, per-capability support levels (`ready/degraded/needs_input/unsupported`).
2. **Environment**: launch plan, policy rewrites (printed diff), isolation tier, egress check, build and boot with health checks.
3. **Workloads**: discovered operations, side-effect classes, which are admitted and why others are excluded, smoke results.
4. **Calibration and load**: generator ceiling, baseline, SLO and its source, capacity brackets.
5. **Investigation**: hypotheses with predictions, experiments, code-scored outcomes, code reads.
6. **Report**: ranked findings with code locations and recommended remediation text (fixing is deferred).
7. **Teardown** and exit code (`tech_doc.md` §16.2).

### If it cannot proceed

It stops with a **named blocker**, the attempts made, and what only the user can supply (e.g., `missing_secret(STRIPE_KEY)`, `unsupported_dependency(<engine>)`, `isolation_insufficient`). Interactive terminals prompt for blocking information; non-interactive runs write `needs_input.json` and exit `9`; answers go in `--answers FILE`. Loadline never substitutes another project or fabricates numbers.

### What they get

`runs/<id>/` (gitignored): `report.md`, `report.json`, `ledger.jsonl`, `profile.json`, `capabilities.json`, `launch_plan*.json`, `workload_plan.json`, `waves/`. Loadline does not modify, merge or push anything in the user's repository.

---

## 4. Cursor skill / prompt (distribution into *their* repo)

One portable `loadline-run` skill (`skills/loadline-run/SKILL.md`). It is written after `analyze --boot --json` and the `.loadline.yaml` schema in `tech_doc.md` §16.3 are tested. No MCP server and no marketplace package in this build. `loadline skills install` copies that one file to `~/.agents/skills/loadline-run/` and, for Claude Code, to `~/.claude/skills/loadline-run/`. It does not install a second workflow per host.

### The skill instructs

1. Check `loadline --version` and `loadline doctor`. Explain what is missing. Do not invent install commands or claim a PyPI package.
2. Confirm the repo is the user's own. Otherwise stop.
3. Run `loadline analyze --boot --json` and parse it. If the JSON is malformed, stop and show the raw blocker.
4. Change `.loadline.yaml` only when `retryable` is true and `remediation` names a key from `tech_doc.md` §16.3. Smallest edit. No other keys. No application source edits. No sandbox changes.
5. Ask the user for a missing secret. Do not write the secret into `.loadline.yaml` or the chat.
6. Retry at most twice after the first boot attempt, and only if the file or the user's answer changed. Re-read the new JSON each time.
7. On success, run `loadline run` and summarise that run's `report.md`: status, measured capacity, findings with locations, projected values, hypotheses, limitations, `investigation_incomplete` if that is the state. Do not invent a trace URL.

### The skill forbids

- Passing production, staging or any discovered URL to Loadline (there is no target-URL flag).
- Running `docker compose up` on the user's real project to "help" a load test.
- Editing application source, Compose, or Dockerfiles to force a boot. `.loadline.yaml` is the only file it may change, and only via keys the boot JSON names.
- Weakening the sandbox (privileged mode, host mounts, `docker.sock`, published ports, egress) to make a boot succeed.

---

## 5. What is supported — stated honestly

Support is per capability (`tech_doc.md` §5.5). Not every repository will run. The outcome is a report or a named blocker.

## 6. Out of scope

| Out of scope | Notes |
|--------------|-------|
| Hosted SaaS, GitHub App/PR bot | local CLI only |
| Fix & verify, auto-merge, PR creation | deferred / never merge |
| Non-HTTP protocols, write workloads, non-Docker runtimes, stronger isolation tiers | deferred |
| Load against production/shared staging/arbitrary URLs | R6; not in the product surface |
| Non-service repos (libraries, mobile/desktop apps, GPU or batch-only workloads) | `not_a_service` / `no_interface` blockers |
| Systems requiring proprietary infrastructure Loadline cannot provision | `needs_input`/`external_dependency` blockers; stubs are labelled |
| `report.html`, dashboards | Tier C |

---

## 7. Judge/reviewer path

1. Clone the hackathon repo, `uv sync`, run `loadline doctor`.
2. `loadline analyze <any repo>` — read the capability matrix.
3. `loadline run` on a Compose/Dockerfile HTTP repo of their choice from the canary list, then on a fixture (`tests/fixtures/*`).
4. Open `runs/<id>/report.md` and the neatlogs link in the partner section.
5. Check `docs/COVERAGE.md` and the acceptance results.

## 8. Evidence checklist (hackathon submission)

- [ ] Public repo with hackathon-dated commits (judges verify).
- [ ] Two neatlogs traces of two Loadline revisions on the same target SHA ("agent improved").
- [ ] A neatlogs trace showing recovery from a failed action (boot repair or rejected experiment).
- [ ] Entire checkpoints and `entire graph` output (`docs/entire/*`).
- [ ] cfo.ai plan exported (`docs/cfo-plan.pdf`).
- [ ] Demo video ≤3 minutes covering neatlogs, Entire, cfo.ai (architecture, implementation, runtime, reasoning, result).
- [ ] Acceptance results (L1–L6) and canary report in the repo.
- [ ] X quote post during 12 Oct 7:00–11:55 PM IST (details in `hackathon.md`).

*Path: `/home/aarush_linux/projects/neathacks/delivery.md`*
