import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import MagicMock

from pydantic_ai.messages import FunctionToolCallEvent, ToolCallPart
from pydantic_ai.run import AgentRunResult, AgentRunResultEvent

from loadline.investigator.run import _run_agent_with_trace


class _FakeAgent:
    def __init__(self, events):
        self._events = events

    @asynccontextmanager
    async def run_stream_events(self, *_args, **_kwargs):
        async def _gen():
            for ev in self._events:
                yield ev

        class _Stream:
            def __aiter__(self):
                return _gen()

        yield _Stream()


def test_run_agent_with_trace_emits_tool_lines(tmp_path: Path):
    async def _run() -> None:
        console = MagicMock()
        console.verbose = False
        call = FunctionToolCallEvent(
            part=ToolCallPart(tool_name="repo", args=json.dumps({"action": "routes"}), tool_call_id="c1"),
        )
        result = AgentRunResult(output="done")
        agent = _FakeAgent([call, AgentRunResultEvent(result)])
        out = await _run_agent_with_trace(agent, MagicMock(), MagicMock(), console)
        assert str(out.output) == "done"
        assert console.investigate_event.called
        summary = console.investigate_event.call_args[0][1]
        assert "repo routes" in summary

    asyncio.run(_run())
