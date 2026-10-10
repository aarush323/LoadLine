"""Build Pydantic AI Investigator agent (repo, read_file, run_k6)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits

from loadline.investigator.deps import InvestigationDeps
from loadline.investigator.neatlogs_attrs import annotate_tool_span
from loadline.investigator.tools import RunK6Input, read_file, repo, run_k6_tool

logger = logging.getLogger(__name__)


def build_investigator_agent(model: Any, system_prompt: str) -> Agent[InvestigationDeps, str]:
    agent: Agent[InvestigationDeps, str] = Agent(
        model,
        system_prompt=system_prompt,
        output_type=str,
        deps_type=InvestigationDeps,
    )

    @agent.tool(name="repo")
    def repo_tool(
        ctx: RunContext[InvestigationDeps],
        action: str,
        query: str = "",
        symbol: str = "",
    ) -> dict:
        if action not in ("search", "def", "neighbors", "impact", "routes"):
            return {"error": "action must be search, def, neighbors, impact, or routes"}
        out = repo(ctx, action, query=query, symbol=symbol)
        return annotate_tool_span(out, adapter="entire")

    @agent.tool(name="read_file")
    def read_file_tool(ctx: RunContext[InvestigationDeps], path: str, start_line: int, end_line: int) -> dict:
        return annotate_tool_span(read_file(ctx, path, start_line, end_line))

    @agent.tool(name="run_k6")
    def run_k6_agent_tool(ctx: RunContext[InvestigationDeps], payload: RunK6Input) -> dict:
        return annotate_tool_span(run_k6_tool(ctx, payload), adapter="k6")

    return agent


def wrap_agent(
    agent: Agent[InvestigationDeps, str],
    *,
    run_id: str | None = None,
    fast: bool = False,
) -> Agent[InvestigationDeps, str]:
    try:
        import neatlogs

        from loadline.neatlogs_setup import LOADLINE_WORKFLOW, init_neatlogs, neatlogs_initialized
        from loadline.settings import get_settings

        settings = get_settings()
        if settings.neatlogs_api_key:
            if not neatlogs_initialized():
                init_neatlogs(
                    settings,
                    workflow_name=LOADLINE_WORKFLOW,
                    run_id=run_id,
                    fast=fast,
                    require_api_key=False,
                )
            return neatlogs.wrap(agent)
    except Exception as exc:
        logger.warning("neatlogs wrap skipped: %s", type(exc).__name__)
    return agent


def default_usage_limits() -> UsageLimits:
    return UsageLimits(request_limit=None, total_tokens_limit=None)
