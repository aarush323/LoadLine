from unittest.mock import MagicMock

from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel

from loadline.core.ledger import Ledger
from loadline.investigator.agent_factory import build_investigator_agent, default_usage_limits
from loadline.investigator.deps import InvestigationDeps


EXPECTED_TOOLS = frozenset({"repo", "read_file", "run_k6"})


def test_default_usage_limits_are_uncapped():
    limits = default_usage_limits()
    assert limits.request_limit is None
    assert limits.total_tokens_limit is None


def test_investigator_has_exactly_three_tools():
    agent = build_investigator_agent(TestModel(), "system")
    names = {tool.name for tool in agent._function_toolset.tools.values()}
    assert names == EXPECTED_TOOLS


def test_repo_tool_rejects_bad_action(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    deps = InvestigationDeps(
        repo_root=tmp_path,
        run_dir=run_dir,
        run_id="r1",
        ledger=Ledger.open(run_dir, "r1"),
        graph=None,
    )
    ctx = RunContext(deps=deps, model=TestModel(), usage=MagicMock(), prompt=None)
    agent = build_investigator_agent(TestModel(), "system")
    tool_fn = agent._function_toolset.tools["repo"].function
    out = tool_fn(ctx, action="bogus")
    assert "error" in out
