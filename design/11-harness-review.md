# 11 — Harness and tracing decisions (Pydantic AI, neatlogs)

Contract: `tech_doc.md` D17, §11, §15. Re-checked for v3: the harness choice is unaffected by the product reset; the tool counts, load engine wording and agent roster are updated.

## 1. Decisions

1. **Harness:** Pydantic AI **core only** (`Agent`, `@agent.tool`, `prepare_tools`, `history_processors`, `UsageLimits`, `output_validator`, `message_history`). Not the `pydantic-ai-harness` package/`Coder()`, not Pi, Hermes, OpenClaw, OpenHands/Goose. Reasons: typed tool schemas, validators and limits we need for deterministic ownership (R5), Python-native embedding next to adapters, documented neatlogs integration, low version-churn risk during the window.
2. **Agents:** one Pydantic AI agent, the Investigator, under one workflow trace per `loadline run`. No shell or filesystem tools. Every tool is ours and typed (`tech_doc.md` §11.3).
3. **Load engine:** k6 behind `GeneratorAdapter` (open-model `constant-arrival-rate`, `dropped_iterations` as the generator-limit signal). Locust remains a *possible* generator adapter for Python-scripted journeys; it is not part of the MVP and its tool names (`spawn_users`, `RunController`, `campaign_id`) are not our API.
4. **MCP:** no Loadline MCP server (cut). Pydantic AI can consume MCP, unused here.
5. **neatlogs correlation:** `neatlogs.init(workflow_name="loadline", tags=[...])` with `list[str]` tags (`"neatHack"`, `run_id:<id>`, `agent_profile:<v0|v1>`, `fast:<bool>`); `neatlogs.wrap(Agent)` for each agent; a manual `WORKFLOW` parent span per CLI invocation; **no `session_id`** (standalone CLI); TOOL span attributes `loadline.result_id`, `loadline.ok`, `loadline.experiment_kind` (non-namespaced custom attributes). High-volume series stay in the ledger/evidence store; only summaries and ids reach the model and spans.
6. **Hackathon verification before relying on any of this:** S-NEATLOGS spike (wrap three agents, tag shape, WORKFLOW parent) with a stub model.

## 2. What the product reset changed here

| Item | v2 | v3 |
|------|----|----|
| Tool list | eight tools | seven Investigator tools (`tech_doc.md` §11.3) |
| Load engine statement | k6 only; Locust cut | k6 default adapter; others optional adapters |
| Harness scope | one agent | three agents, one trace |
| Policy | `policy.py` before tools | `core/policy/*` (TargetGuard, SandboxPolicy, ExperimentPolicy) |

## 3. Verification commands (P0)

| Check | Pass |
|-------|------|
| `pip install -U "neatlogs[pydantic-ai]" pydantic-ai` then import | imports succeed |
| Stub-model run with three wrapped agents | one WORKFLOW trace with three AGENT children locally (`neatlogs doctor --local`) |
| `inspect.signature(neatlogs.init)` | `tags` is a list parameter |
| k6 step summary export | per-step metrics populated (S-GEN) |

## 4. Open items

Pin `pydantic-ai` and `neatlogs` versions after the P0 spike passes (`design/12-oss-bom.md`). Whether to expose `loadline.experiment_kind` as a searchable attribute: yes (helps judges filter experiment spans).
