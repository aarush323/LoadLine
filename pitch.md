# neatHack pitch playbook — Loadline

> **Status:** planning document. Every metric, trace URL, screenshot and business number below is a **PLACEHOLDER** (`[FILL: …]`) until a real run produces it. Nothing here may be demonstrated on a result that was not actually measured.
>
> **Engineering authority:** [`tech_doc.md`](./tech_doc.md) · [`mvp.md`](./mvp.md) · [`implementation.md`](./implementation.md) · [`kickoff.md`](./kickoff.md)

**Event source:** [neatHack — AI agent hackathon](https://neatlogs.com/hackathon).

---

## Name options (rename freely)

| Name | Tagline |
|------|---------|
| **Loadline** (working) | Point it at your repo. It finds the scalability bottlenecks and shows the code and the evidence. |
| **Saturation Scout** | Find what caps your service — and the line of code behind it. |
| **RampReason** | Open-model load, evidence-scored hypotheses, code-linked findings. |

---

## 1. Positioning

### 10-second pitch

**Loadline** is a local-first, agentic load tester. `loadline run` in a developer's repository discovers how it runs, boots it in isolated Docker/Compose, generates real workloads with k6, investigates bottlenecks with evidence-scored hypotheses, and reports measured capacity with code-linked findings and recommended remediation. Fixing and verifying is deferred; Loadline never modifies the repo.

### 30-second pitch

Teams need a defensible capacity number and a code-grounded cause, not a chart and a guess. Scripts run load; they do not discover a service they have never seen, tell a slow app apart from a saturated generator or host, or test a causal hypothesis by perturbing one thing. Loadline does all of that behind one command, with no hand-written load scripts, endpoint lists or database config — and when it cannot proceed it says exactly why instead of faking a result.

```bash
loadline run --goal "Find scalability bottlenecks and improve throughput"
```

**"Agent improved"** = two **live** neatlogs runs of two Loadline git revisions on the **same target SHA** (a held-out canary or a fixture). Never replayed data.

### Who is the user and the pain?

| User | Pain |
|------|------|
| Backend/platform engineer with an unfamiliar or legacy service | Weeks of hand-built load scripts, environment wrangling and metric spelunking before any insight |
| Team that wants capacity checks in review | Needs a safe, repeatable, evidence-backed run — not production load |
| Hackathon judge / mentor | Wants to point it at a repo of their choosing and see an honest result |

### Why an agent beats a script

| Script | Loadline |
|--------|----------|
| Fixed ramp against known endpoints | Discovers interfaces, classifies side effects, builds workloads, admits only what is safe |
| One metric view | Separates generator, host, environment and application limits before blaming the app |
| Story from a single chart | Hypothesis → structured prediction → intervention experiment → code-scored outcome |
| "Probably the DB" | Cites file and line only after reading them; confidence is a function of evidence |
| Generic advice | Recommended remediation tied to a located mechanism, with confidence and the experiments behind it |

### Why this wins on the rubric

Weights ([event page](https://neatlogs.com/hackathon)): **Agent 30%** · **Partners 25%** · **Demo 20%** · **Building in public 15%** · **Usefulness 10%**.

| Weight | Concrete artefact |
|--------|-------------------|
| 30% — agent | adaptive investigation on repos it has never seen; hypotheses scored by code; recovery from a rejected experiment or invalid step |
| 25% — partners | **neatlogs**: v0/v1 live traces on the same target SHA + recovery trace. **Entire**: checkpoints on commits + `entire graph` as a code-intelligence adapter used in live runs. **cfo.ai**: `docs/cfo-plan.pdf` |
| 20% — demo | ≤3 min, unfamiliar repo live, all three partners × five elements |
| 15% — building in public | milestone posts (§5) + `docs/building-in-public/links.md` + public commits |
| 10% — usefulness | works on a user's own repo; honest blockers; no fabricated numbers |

---

## 2. Competitive / prior art (honest)

| Prior art | What it does | How Loadline differs |
|-----------|--------------|----------------------|
| Grafana k6 AI assistant / k6 MCP | writes and runs k6 scripts from an editor | Loadline discovers the app and workloads itself, isolates the environment, and investigates causally |
| Deterministic k6 pipelines | metrics collection | no repo discovery, no hypotheses, no code-linked findings |
| Observability-suite AI (alert investigation) | explains production incidents from existing telemetry | Loadline *creates* the load and the telemetry in a sandbox from source; no production access |
| Academic grey-box LLM diagnosis | guesses from metrics | Loadline requires measured predictions and read code ranges before naming a cause |

**Honest scope:** not every repository will run. Loadline detects capabilities, tries alternates, asks only for blocking inputs, and names the blocker (`docs/COVERAGE.md` is generated from adapter manifests and canary results).

---

## 3. Demo video script (≤3:00)

**Requirement:** ≤3 min; neatlogs, Entire and cfo.ai each get **architecture, implementation, runtime, reasoning, result** ([FAQ](https://neatlogs.com/hackathon)).

Canonical on-screen commands (the demo uses the same path any user's repo would):

```bash
loadline analyze <canary-repo>
loadline run --repo <canary-repo> --fast
loadline run --repo tests/fixtures/<fixture> --fast
```

| Time | Beat | On screen | Spoken |
|------|------|-----------|--------|
| 0:00–0:12 | Hook | terminal: `loadline run` in an unfamiliar repo; flash the capability matrix | "Point it at a repo it has never seen. No scripts, no config." |
| 0:12–0:30 | Discovery + safety | capability matrix, launch plan diff, isolation line, egress check | "It discovers the stack, rewrites unsafe launch config, and says what isolation it is using — Docker is not a complete boundary." |
| 0:30–0:50 | Workloads + load | operations with side-effect classes, calibration, bracket | "Real operations from the repo, only safe ones loaded, open-model load, generator and host limits separated from the app." |
| 0:50–1:10 | Reasoning | hypothesis with structured prediction → experiment → scored outcome | "The agent predicts, perturbs one thing, and code decides whether it was right." |
| 1:10–1:22 | Recovery | rejected experiment or invalid step recovered, in the trace | "It recovered from a failed action — see the trace `[FILL: URL]`." |
| 1:22–1:48 | **neatlogs** | arch: agent loop under one WORKFLOW; impl: `wrap(Agent)`; runtime: span tree; reasoning: failed-vs-recovered path; result: v0 vs v1 table `[FILL: tokens/cost/tool errors/findings]` | "Improvement is two live runs of two revisions on the same SHA." |
| 1:48–2:08 | **Entire** | arch: checkpoints + graph adapter; impl: `entire graph query` argv wrapper; runtime: graph output in a live run; reasoning: call-path used for `K` only after `read_file`; result: checkpoint `[FILL]` | "Build-time checkpoints; run-time code graph — ripgrep when the graph lacks a language." |
| 2:08–2:28 | **cfo.ai** | arch: team plan, not an agent tool; impl: export; runtime: n/a; reasoning: cost per run from neatlogs; result: `docs/cfo-plan.pdf` pricing/runway `[FILL]` | "The business plan lives in the repo; the agent never calls cfo.ai." |
| 2:28–2:48 | Report | ranked finding card: measured symptom, code location, alternatives ruled out, confidence breakdown, remediation text, Limitations | "Confirmed findings, hypotheses and measurement limits are kept apart." |
| 2:48–3:00 | Close | `docs/SUBMISSION.md`, repo, `#neatHack` | "Try it on your repo." |

**Honesty beat (optional if time):** a negative fixture ends with `missing_secret(...)` or `policy_refused(...)` rather than a result.

**Shot checklist:** terminal GIF, neatlogs UI (redact keys), `docs/entire/*`, `docs/cfo-plan.pdf`, `report.md` excerpt as text overlay.

---

## 4. Failure → neatlogs → finding (beat sheet)

Fixtures with planted flaws exist to *verify* Loadline; their flaw ids and locations live only in sealed oracles (`tests/oracles/`) and never appear in product logic or agent prompts. The demo narrative therefore describes what the agent measured, not what the author planted.

1. **Discovery and boot** — capability matrix, plan validated, egress verified.
2. **Capacity** — bracket, SLO and its source, limit attribution.
3. **Wrong-layer hypothesis (v0)** — v0 revision over-trusts a correlation or skips the discriminating experiment; trace shows a low-confidence or refuted finding.
4. **v1** — structured predictions and discriminating experiments; ranked finding with code location; comparison table.
5. **Recovery (required)** — an experiment rejected by policy or an invalid step, recovered by the agent; trace URL in `docs/SUBMISSION.md`.
6. **Report** — ranked finding, confidence breakdown, remediation text (fix & verify is deferred).

If a planned recovery does not occur naturally, do not fabricate one; document it in Known limitations and use a real one from a canary.

**Prohibited as evidence:** replayed measurement data posing as a live run; anything produced against a target other than the recorded SHA; results from tuning on held-out canaries.

---

## 5. Building in public plan

Community winner: genuine interest; follower count does not decide; bought likes disqualify ([FAQ](https://neatlogs.com/hackathon)). Scheduling is the team's decision.

Published times (IST): web check-in Sat 10 Oct 8:00 AM · build starts 12:30 PM · X submission Mon 12 Oct 7:00–11:55 PM (quote the official neatlogs post).

Post on milestones (include `#neatHack`, `@neatlogs` where natural). Visual: terminal screenshot/GIF + copy-paste summary from `report.md`.

| Milestone | Template |
|-----------|----------|
| Repo public + problem | "Building Loadline for #neatHack: point it at your repo; it discovers, isolates, load-tests and investigates bottlenecks. @neatlogs [FILL: repo]" |
| First capability matrix on an unfamiliar repo | "Milestone: `loadline analyze` on [FILL: repo] — stack, services, deps, interfaces, and what it *can't* do. #neatHack" |
| First sandboxed boot + teardown | "Milestone: boots [FILL] in a hardened sandbox, egress denied and verified, zero stray resources. A container isn't a full boundary — here's what we claim. #neatHack" |
| First valid capacity bracket | "Milestone: open-model bracket on [FILL], generator/host limits separated. #neatHack" |
| First neatlogs trace | "Milestone: first WORKFLOW trace [FILL: URL]. #neatHack @neatlogs" |
| First sandboxed boot | "Milestone: boots [FILL] in hardened Docker with egress denied and zero stray resources. #neatHack" |
| First scored hypothesis | "Milestone: agent predicted, perturbed, and code scored it [FILL]. #neatHack" |
| Entire checkpoint + graph | "Milestone: Entire checkpoint [FILL: SHA] + graph adapter output. #neatHack" |
| Honest blocker | "Milestone: it refuses with a specific reason instead of a fake result: [FILL]. #neatHack" |
| cfo.ai plan | "Milestone: cost per run [FILL] from neatlogs traces → `docs/cfo-plan.pdf`. #neatHack" |
| Demo/submission | "Video [FILL] · index `docs/SUBMISSION.md` · try `loadline doctor`. #neatHack @neatlogs" |

---

## 6. Final X quote-post template

Window: Mon 12 Oct 2026, 7:00–11:55 PM IST · quote the official neatlogs post.

```
#neatHack @neatlogs

Team: [FILL]
Project: Loadline
Repo: [FILL: URL]
Demo: [FILL: video ≤3m]

Point it at your repo → discovery · isolated Docker run · k6 load · evidence-scored investigation · code-linked report
neatlogs v0/v1 traces · Entire: docs/entire/ · Plan: docs/cfo-plan.pdf

Index: docs/SUBMISSION.md
[quote official post]
```

---

## 7. Evidence checklist

Index everything in `docs/SUBMISSION.md`. Assign owners per row (`[FILL: owner]`).

| Evidence | Path | Notes |
|----------|------|-------|
| Agent improved | SUBMISSION comparison table; neatlogs v0 + v1 URLs | live runs, same target SHA |
| neatlogs used | trace URLs; recovery URL | one WORKFLOW per run; Investigator wrapped |
| Entire used | checkpoint SHA; `docs/entire/*` | `entire enable` before first product commit |
| cfo.ai used | `docs/cfo-plan.pdf` | team-authored; assumptions labelled |
| Agent recovers | recovery trace URL | real failure, not simulated |
| Building in public | `docs/building-in-public/links.md` | `#neatHack` |
| Hackathon commits | public git history | per FAQ |
| Demo video | URL in SUBMISSION | ≤3 min; 3 partners × 5 elements |
| Generality | capability matrix, `docs/COVERAGE.md`, canary report | held-out canaries untouched by tuning |
| Acceptance | L1–L6 results | no-leakage + metamorphic green |
| Run outputs | `runs/<id>/report.md`, `report.json`, `ledger.jsonl` | no fabricated numbers |

---

## 8. cfo.ai business-plan outline (numbers PLACEHOLDER)

`docs/cfo-plan.pdf` — produced by the team in cfo.ai; the agent does not invoke it. Cancel billing after signup per event page. Label `[ASSUMPTION]` everywhere.

- **Customers:** teams shipping services without a performance engineer; platform teams; agencies — `[FILL]`
- **Pricing:** OSS core / Pro `[FILL: $/mo]` / Team `[FILL: $/mo]`
- **COGS per run:** LLM cost from neatlogs exports `[FILL: $/run]`; local compute `[FILL]`; neatlogs ingest `[FILL]`
- **Scenarios:** base vs growth; revenue, gross margin `[FILL]`, runway `[FILL]`
- **GTM:** drop-in CLI + Cursor skill; proof = reproducible runs on the user's own repo

---

## 9. Q&A prep

1. **Does it work on any repo?** — No claim of that. It runs a fallback chain, publishes a coverage matrix, and names the specific blocker when it stops.
2. **Is a container a secure sandbox?** — Not a complete boundary. We use hardened Docker for your own repos and say so; untrusted-code isolation is deferred.
3. **How do you avoid hitting production?** — The only load target is the isolated instance created for the run; URLs found in repo files are data, and egress is denied and verified.
4. **How do you know it isn't overfitted to your demo app?** — No-leakage test, metamorphic renaming, blind sealed-oracle fixtures, held-out canaries.
5. **Who decides if a hypothesis was right?** — Code scores structured predictions; the agent proposes, code disposes.
6. **Prove the agent improved.** — Two live neatlogs runs of two revisions, same target SHA.
7. **What if load tests mutate state?** — Only read-safe operations are loaded; everything else is listed as excluded with the reason. Write workloads are deferred.
8. **Does it fix the code?** — Not in this release; it reports remediation text with confidence. It never modifies or merges into your repo.
9. **How is Entire used?** — Checkpoints during the build. At runtime, `entire graph query` (and `def`, `neighbors`, `impact`) is the code-intelligence adapter. Ripgrep is the fallback when the graph is missing or partial.
10. **cfo.ai in the loop?** — No; business plan in `docs/`.
11. **What does the model see?** — Repo excerpts read by tools, secrets denylisted and redacted; stated in the report's Limitations.
12. **Why k6?** — Mature open-model generator, run as an external process behind a swappable adapter; no custom load generator.

---

## 10. Pitfalls checklist

| Pitfall | Mitigation |
|---------|------------|
| Demo works only on a fixture | demo opens with an unfamiliar canary; fixtures show hypothesis-to-finding |
| Tuning on canaries | hold-outs sealed from adapter work |
| Claiming "sandboxed"/"safe" without the caveat | isolation line printed and recorded |
| Fabricating recovery | use a real failure or omit |
| Replayed data as evidence | live runs only |
| `neatlogs` tags dict / `session_id` | `list[str]` tags; omit `session_id` |
| Entire after first commit | enable before the first product commit |
| Skipping a partner in the video | §3 table enforces 5 elements × 3 partners |
| Late X quote | inside the official window |
| Overclaiming compatibility | coverage matrix + blockers |

*Path: `/home/aarush_linux/projects/neathacks/pitch.md`.*
