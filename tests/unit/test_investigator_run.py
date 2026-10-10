import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic_ai.models.test import TestModel

from loadline.core.ledger import Ledger
from loadline.investigator.run import run_investigation_sync


def test_investigator_completes_with_test_model(tmp_path: Path):
    repo = Path(__file__).resolve().parents[2]
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    report_text = "## Report\n\nTest endpoint held at 10 rps.\n"
    with patch("loadline.investigator.run.wrap_agent", side_effect=lambda a, **_: a):
        result = run_investigation_sync(
            repo_root=repo,
            run_dir=run_dir,
            run_id="live-mock",
            model=TestModel(
                call_tools=[],
                custom_output_text=report_text,
            ),
            boot={"services": [{"name": "web"}], "network": "n"},
            allowed_hosts=frozenset({"web"}),
            network="n",
        )
    assert result.status == "completed"
    assert (run_dir / "report.md").read_text() == report_text
    assert not any(e.get("kind") == "finding" for e in Ledger.open(run_dir, "live-mock").events())


def test_provider_failure_investigation_incomplete(tmp_path: Path):
    repo = Path(__file__).resolve().parents[2]
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    from contextlib import asynccontextmanager

    agent = AsyncMock()

    @asynccontextmanager
    async def failing_stream(*_args, **_kwargs):
        raise ConnectionError("provider failure")
        yield  # pragma: no cover

    agent.run_stream_events = failing_stream

    with patch("loadline.investigator.run.build_investigator_agent", return_value=agent):
        with patch("loadline.investigator.run.wrap_agent", side_effect=lambda a, **_: a):
            result = run_investigation_sync(
                repo_root=repo,
                run_dir=run_dir,
                run_id="fail1",
                model=TestModel(),
                boot={},
            )
    assert result.status == "investigation_incomplete"
    ledger = Ledger.open(run_dir, "fail1")
    assert ledger.events_of("investigation_incomplete")
    assert ledger.events_of("report_written")
    assert "Investigation incomplete" in (run_dir / "report.md").read_text()
