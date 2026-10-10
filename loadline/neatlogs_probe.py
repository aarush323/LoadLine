"""MODEL-RT: one traced agent turn with a tool (no paid LLM when using TestModel)."""

from __future__ import annotations

import argparse
import sys

import neatlogs
from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel

from loadline.neatlogs_setup import init_neatlogs, shutdown_neatlogs
from loadline.neatlogs_workflows import TRACING_SELF_TEST
from loadline.settings import get_settings


def _build_probe_agent() -> Agent[None, str]:
    agent = Agent(
        TestModel(custom_output_text="probe-ok"),
        system_prompt="Neatlogs MODEL-RT probe.",
    )

    @agent.tool
    def echo_probe(_ctx: RunContext[None], message: str) -> str:
        return f"echo:{message}"

    return agent


def run_local_probe() -> str:
    """Traced WORKFLOW → AGENT → TOOL without a provider API key."""
    load_dotenv()
    init_neatlogs(
        workflow_name=TRACING_SELF_TEST,
        run_id="model-rt-local",
        fast=True,
        require_api_key=False,
    )

    agent = neatlogs.wrap(_build_probe_agent())
    with neatlogs.trace("loadline neatlogs probe", kind="WORKFLOW"):
        result = agent.run_sync("Call echo_probe with message neatHack")
    shutdown_neatlogs()
    return str(result.output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Loadline neatlogs MODEL-RT probe")
    parser.add_argument(
        "--hosted",
        action="store_true",
        help="Require NEATLOGS_API_KEY and export trace (then run neatlogs doctor --probe)",
    )
    args = parser.parse_args()

    load_dotenv()
    if args.hosted:
        init_neatlogs(
            workflow_name=TRACING_SELF_TEST,
            run_id="model-rt-hosted",
            fast=True,
            require_api_key=True,
        )
        model = get_settings().loadline_model
        agent = neatlogs.wrap(
            Agent(model, system_prompt="Reply in one short sentence."),
        )

        @agent.tool
        def ping(_ctx: RunContext[None]) -> str:
            return "pong"

        with neatlogs.trace("loadline neatlogs hosted probe", kind="WORKFLOW"):
            out = agent.run_sync("Call ping once, then say done.")
        print(out.output)
        shutdown_neatlogs()
        print("Hosted probe finished. Run: uv run python -m neatlogs doctor --probe --json")
        return

    try:
        out = run_local_probe()
    except Exception as exc:
        print(f"PROBE_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(out)
    print("Local MODEL-RT OK (TestModel). Next: set NEATLOGS_API_KEY and run with --hosted")


if __name__ == "__main__":
    main()
