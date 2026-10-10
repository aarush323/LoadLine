from pathlib import Path

from loadline.ui.phases import Phase
from loadline.ui.run_console import RunConsole


def test_investigate_event_only_during_investigate(capsys):
    console = RunConsole(json_mode=False, quiet=False, run_dir=Path("/tmp/x"))
    console.phase_start(Phase.INVESTIGATE)
    console.investigate_event("agent", "→ repo routes")
    out = capsys.readouterr().err
    assert "[investigate]" in out
    assert "repo routes" in out


def test_ledger_k6_run_emits(capsys):
    console = RunConsole(json_mode=False, quiet=False, verbose=True, run_dir=Path("/tmp/x"))
    console.phase_start(Phase.INVESTIGATE)
    console.ledger_event(
        {
            "kind": "k6_run",
            "experiment_id": "exp-k6-0001",
            "wave": "agent-k6-1",
            "result": {
                "offered_rps": 10,
                "dropped_iterations": 0,
                "operations": {"health": {"p95_ms": 20}},
            },
        }
    )
    out = capsys.readouterr().err
    assert "k6" in out
    assert "exp-k6-0001" in out
