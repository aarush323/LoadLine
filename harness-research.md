# Loadline — agent harness research (neatHack, 10–12 Oct 2026)

Planning-only notes for choosing **one** agent loop for a **Python CLI** that discovers and runs an arbitrary repository in a sandbox, drives **k6** through a generator adapter, collects stack-independent telemetry, investigates with evidence-scored hypotheses, and writes capacity numbers plus code-linked findings and optional verified fixes (`tech_doc.md` v3). Hackathon partner tools: **neatlogs** (trace every run), **Entire** (checkpoints at build time; `entire graph` as one runtime code-intelligence adapter), **cfo.ai** (business plan only — not runtime). The harness decision below predates the 2026-10-10 product reset and is unaffected by it; see `BRIEF.md` §3.13 (Pydantic AI core; Harness `TieredCompaction` only if context gets long; pin versions; no Harness Coder/Shell/FileSystem on the Investigator) and `design/11-harness-review.md`.

**Official track (quoted):** “Build an AI agent, or a team of agents, that completes a substantial task from start to finish. Give it a goal, tools and an environment; let each result guide its next action.” Focus areas include planning, tool use, state across steps/runs/failures, execution of long tasks, recovery, verification, and iteration. Example: *“Watch a running system.”* — [neatlogs.com/hackathon/1](https://neatlogs.com/hackathon)

---

## 1. What is “Pi”?

| Fact | Detail | Source |
|------|--------|--------|
| Identity | **Pi** — minimal agent harness monorepo (`earendil-works/pi`): coding-agent CLI + libraries. | [README](https://github.com/badlogic/pi-mono/blob/HEAD/README.md) |
| Language | **TypeScript**, Node.js **≥ 22.19** | [Pi Agent (neatlogs)](https://docs.neatlogs.com/integrations/pi-agent) |
| License | **MIT** | Pi README |
| Custom tools | `pi.registerTool()` extensions (TypeBox); SDK `extensionFactories` | [06-extensions.ts](https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/examples/sdk/06-extensions.ts) |
| Headless | In-process SDK (`session.prompt()`), **RPC** `pi --mode rpc` JSONL | [sdk.md](https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/docs/sdk.md), [rpc.md](https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/docs/rpc.md) |
| Loop / budget | `shouldStopAfterTurn`, abort; harness phases | [agent-harness.md](https://github.com/earendil-works/pi/blob/main/packages/agent/docs/agent-harness.md) |
| Resume | Session **JSONL** via `SessionManager` | sdk.md |
| neatlogs | `piAgentHooks(agentOrHarness)` → **AGENT → CHAIN → LLM / TOOL**; do not double-wrap LLM | [Pi Agent integration](https://docs.neatlogs.com/integrations/pi-agent) |

**Loadline fit:** Excellent harness **if the CLI host is Node**. A Python CLI would need a Node RPC sidecar and domain tools implemented as Pi extensions in TypeScript — high integration cost for k6/psycopg/docker tooling that already lives naturally in Python.

---

## 2. What is Hermes (NousResearch)?

| Fact | Detail | Source |
|------|--------|--------|
| Identity | **Hermes Agent** — NousResearch coding/agent stack (`NousResearch/hermes-agent`) | [Hermes + neatlogs](https://docs.neatlogs.com/integrations/hermes) |
| Language | **Python** (install from GitHub: `pip install "git+https://github.com/NousResearch/hermes-agent.git"`, **not PyPI**) | Hermes neatlogs page |
| Modes | **Plugin:** `hermes plugins enable neatlogs` on standalone `hermes` CLI. **Library:** `from run_agent import AIAgent` + `neatlogs.wrap(AIAgent(...))` | Same |
| Custom tools | Hermes **ToolRegistry** / built-in coding tools; domain tools require fitting Hermes’ tool model | Library mode patches `ToolRegistry.dispatch` for neatlogs **TOOL** spans |
| Headless / programmatic | `AIAgent.run_conversation()`; `max_iterations` constructor arg | Hermes neatlogs page |
| Models | Defaults toward **OpenRouter** (`OPENROUTER_API_KEY`); LLM via OpenAI-compatible client → enable `openai` instrumentation | Hermes neatlogs page |
| Memory / skills | Kanban, skills, subagents, gateway — **coding-agent product surface**, not a minimal tool loop | Plugin span tree includes `hermes.subagent.*` |
| Checkpointing | Session/turn ids for neatlogs stitching; not a job ledger for k6 wave state | Hermes neatlogs page |
| License | **Verify in first-hour check:** `curl -sL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/LICENSE` | — |
| neatlogs | Plugin (observer hooks) or `instrumentations=["hermes","openai"]` + `wrap(AIAgent)`; span tree documented on integration page | [integrations/hermes](https://docs.neatlogs.com/integrations/hermes) |

**Loadline fit:** Python-friendly, neatlogs story is strong, but Hermes optimizes for **interactive coding agents** (CLI gateway, skills, subagents). Loadline needs a typed seven-tool Investigator with deterministic policy gates and JSONL resume — fighting Hermes’ defaults costs hackathon time. Git-only install adds supply-chain friction.

---

## 3. Full harness comparison

**Scoring:** 1 = poor, 5 = excellent for a **48h Python CLI** team using Cursor. “neatlogs” = documented integration quality per [llms.txt](https://docs.neatlogs.com/llms.txt).

| Harness | Py CLI fit | Custom tools | Headless | Step/token budget | Durable resume | neatlogs | License | TTF agent (h) | Framework risk | **Σ /45** |
|---------|------------|--------------|----------|-------------------|----------------|----------|---------|---------------|----------------|-----------|
| **Pydantic AI** | 5 | 5 `@agent.tool` | 5 `run_sync` | 5 `UsageLimits` (`request_limit`, `tool_calls_limit`, tokens, cost) | 4 `message_history` + ledger file | 5 `wrap(Agent)` | MIT | 2–3 | 1 | **39** |
| **OpenAI Agents SDK** | 5 | 5 `@function_tool` | 5 `Runner.run_sync` | 4 `max_turns` | 4 `Session` / `RunState` | 5 `openai_agents_processor()` | MIT | 2–4 | 2 | **38** |
| **Plain loop** + neatlogs `@span` | 5 | 5 (you write dispatch) | 5 | 4 (manual counters) | 5 (you own JSON) | 4 [custom orchestration](https://docs.neatlogs.com/guides/custom-orchestration) | Provider SDK | 1–2 | 1 | **38** |
| **Agno** | 5 | 4 `Agent` tools | 5 | 3 (framework defaults) | 3 | 5 `wrap(Agent)` | Apache-2.0 typical | 2–4 | 3 | **35** |
| **smolagents** | 5 | 4 `@tool` | 5 | 4 `max_steps` | 3 | 2 (no page in llms.txt; DIY spans) | Apache-2.0 | 2–3 | 2 | **32** |
| **Hermes** (library) | 4 | 3 ToolRegistry | 4 | 4 `max_iterations` | 3 conversation/session | 5 plugin or wrap | verify LICENSE | 4–6 (git install) | 4 | **32** |
| **LangGraph** | 4 | 4 tool nodes | 4 | 4 graph stop rules | 5 checkpointer + `thread_id` | 4 `langchain_handler()` at **graph** invoke | ecosystem | 4–8 | 5 | **31** |
| **Google ADK** | 4 | 4 ADK tools | 4 `Runner` | 3 | 4 ADK session service | 5 `wrap(Runner)` | Apache-2.0 typical | 4–6 | 4 | **31** |
| **DSPy** | 3 | 3 (modules not tool-loop) | 4 | 2 optimization-focused | 2 | 4 `wrap(Module)` | MIT | 3–5 | 4 | **27** |
| **Strands** | 4 | 4 | 4 | 3 | 3 | 4 `strands_hooks(agent)` | Apache-2.0 typical | 3–5 | 3 | **28** |
| **Claude Agent SDK** | 3 | 2 coding `query` tools | 4 async `query` | 3 | 3 transcripts | 5 `wrap(sdk)` | Anthropic terms | 2–4 | 5 (wrong abstraction) | **26** |
| **Pi** ([pi.dev](https://pi.dev/)) | 2 | 3 TS extensions / MCP | 4 print, RPC, SDK | 4 | 4 session tree | 5 `piAgentHooks` | MIT | 5–8 (+ Python glue) | 5 | **25** |

**Rubric weighting (why neatlogs + agent behavior matter):** Judges score **the agent 30%** (planning, recovery, verification, long tasks) and **partner tool use 25%** (neatlogs traces that show improvement with numbers). Harness choice must produce a **clear WORKFLOW → AGENT/LLM → TOOL** tree without double-wrapping LLMs ([Pydantic AI integration](https://docs.neatlogs.com/integrations/pydantic-ai), [OpenAI Agents](https://docs.neatlogs.com/integrations/openai-agents)).

**LangGraph** and **Pi** score well on paper for resume but lose on **time-to-demo** and **debug surface** in 48h. **Claude Agent SDK** and **Hermes plugin CLI** optimize for repo coding, not sandbox/load/telemetry orchestration. **DSPy** targets program optimization, not multi-tool ops loops.

**Pi correction (2026-10-09, from [pi.dev](https://pi.dev/)):** Pi 1.0 is a minimal MIT harness with skills, extensions, a session tree, print/JSON, RPC, an SDK, and built-in MCP. The table score stays **25** because Loadline’s generator adapter, policy gates, telemetry adapters, confidence, and report stay in Python. Moving the loop onto Pi means a second runtime and a permission model Pi does not ship. Verdict: [`design/00-topics.md`](./design/00-topics.md) §1.

**Entire / entire-graph** is **orthogonal** to harness choice. Product use (doctor, intake, `search_code` / `code_graph`, fix-stage diff) is [`design/13-entire-across-product.md`](./design/13-entire-across-product.md).

---

## 4. neatlogs integration index (harness-relevant)

From [docs.neatlogs.com/llms.txt](https://docs.neatlogs.com/llms.txt): Pydantic AI, OpenAI Agents SDK, Claude Agent SDK, LangChain/LangGraph, Pi Agent, Hermes, Google ADK, Strands, Agno, DSPy, Mastra, Vercel AI SDK, plus **Custom Orchestration** for plain Python.

---

## 5. Open-source reuse (load + fixtures)

| Piece | Role | License |
|-------|------|---------|
| **k6** binary/container | open-model arrival-rate executor behind `GeneratorAdapter` | **AGPL-3.0** ([grafana/k6](https://github.com/grafana/k6)) |
| **summary export** | agent-ingestible per-step JSON | AGPL (same process) |
| **cgroup v2 stats**, engine stats, dependency-native stats | universal + optional telemetry | OS / vendor |

**Loadline differentiator:** repo-independent discovery → sandboxed run → declarative workload plan → fixed generic generator script → verdict engine → hypothesis/prediction/experiment loop scored by code → `read_file`-grounded findings → ABBA-verified fixes → neatlogs-traced investigation.

---

## 6. Decision record (single harness)

### Decision

**Use Pydantic AI** as the only agent harness for Loadline.

### Rationale (five lines)

1. **Native Python CLI** — adapters (container engine, generator, collectors) run in-process with typed Pydantic models; no Node sidecar (unlike Pi) and no Hermes coding-gateway ceremony.
2. **First-class neatlogs** — `neatlogs.wrap(Agent)` yields **AGENT** roots with nested **LLM** and **TOOL** spans ([integration doc](https://docs.neatlogs.com/integrations/pydantic-ai)); add an explicit **WORKFLOW** parent in `cli.py` per [Python SDK](https://docs.neatlogs.com/sdk/python).
3. **Deterministic budgets** — `UsageLimits(request_limit=…, tool_calls_limit=…, …)` caps long runs without custom loop code ([Pydantic AI usage limits](https://ai.pydantic.dev/agents/#usage-limits)).
4. **Fast typed tools** — `@agent.tool` + `RunContext` map directly to the typed Loadline tool sets (`tech_doc.md` §11.3); Cursor can generate schemas from the contract.
5. **Low framework risk** — smaller surface than LangGraph checkpointers or OpenAI Agents handoffs/guardrails; resume uses **ledger.jsonl + `message_history`**, which matches hackathon evidence needs.

### First-hour verification (Saturday 12:30–1:30 IST)

If any step fails, **stop implementation** and escalate to the human — do not switch harness in code.

| Step | Command / action | Pass criterion |
|------|------------------|----------------|
| Install | `pip install -U "neatlogs[pydantic-ai]" pydantic-ai` | Import succeeds |
| Dummy agent | One `@agent.tool` + `neatlogs.init` + `wrap(Agent)` + `run_sync` | `neatlogs doctor --local` clean |
| Span shape | Open trace in neatlogs UI | **WORKFLOW** (manual parent) → **AGENT** → **LLM** + **TOOL** |
| Budget | `usage_limits=UsageLimits(request_limit=2)` on third step | `UsageLimitExceeded` with clean exit |
| Provider | Same with team’s chosen `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` model string | One real LLM call traced |

### Rejected alternatives (one line each)

| Harness | Why not |
|---------|---------|
| OpenAI Agents SDK | Equivalent neatlogs story but extra concepts (handoffs, processors) without benefit for a single-agent CLI. |
| Hermes | Coding-agent product; git install; domain tools fight ToolRegistry defaults. |
| Pi | Real minimal harness ([pi.dev](https://pi.dev/): extensions, skills, print/JSON, RPC, SDK, MCP). Domain tools would still be TypeScript or MCP-wrapped Python, with no built-in permission gate and a separate neatlogs tree. |
| LangGraph | Checkpointer ceremony and graph-debug time exceed 48h budget. |
| Plain loop | Viable; Pydantic AI saves tool-schema and usage-limit code while staying equally controllable. |
| Claude Agent SDK / DSPy / ADK / Strands / Agno / smolagents | Weaker fit for fixed multi-tool ops loop and/or weaker neatlogs story (smolagents). |

---

## Verified sources

- Hackathon track & judging: [neatlogs.com/hackathon/1](https://neatlogs.com/hackathon)
- neatlogs integrations: [llms.txt](https://docs.neatlogs.com/llms.txt), [Pydantic AI](https://docs.neatlogs.com/integrations/pydantic-ai), [OpenAI Agents](https://docs.neatlogs.com/integrations/openai-agents), [Hermes](https://docs.neatlogs.com/integrations/hermes), [Pi](https://docs.neatlogs.com/integrations/pi-agent), [LangChain/LangGraph](https://docs.neatlogs.com/integrations/langchain), [Claude Agent SDK](https://docs.neatlogs.com/integrations/claude-agent-sdk), [Google ADK](https://docs.neatlogs.com/integrations/google-adk), [Strands](https://docs.neatlogs.com/integrations/strands), [Agno](https://docs.neatlogs.com/integrations/agno), [DSPy](https://docs.neatlogs.com/integrations/dspy), [custom orchestration](https://docs.neatlogs.com/guides/custom-orchestration)
- Pi packages: [pi-mono README](https://raw.githubusercontent.com/badlogic/pi-mono/main/README.md)
- k6 executor & license: [constant-arrival-rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/), [k6 LICENSE](https://github.com/grafana/k6)
- Entire: [capture-checkpoints](https://docs.entire.io/guides/checkpoints/capture-checkpoints.md), [set-up-graph](https://docs.entire.io/guides/graph/set-up-graph.md)

## Unverified (first-hour only)

- Hermes **LICENSE** file on default branch
- Exact k6 **summary JSON** shape for one constant-arrival-rate step with tagged warm-up — confirm in spike S-GEN (`implementation.md` P0)

---

*Path: `/home/aarush_linux/projects/neathacks/harness-research.md`*
