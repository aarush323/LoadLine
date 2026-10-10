import io
import sys

from loadline.ui.phases import Phase
from loadline.ui.run_console import RunConsole


def test_quiet_suppresses_phase_lines(capsys):
    console = RunConsole(quiet=True)
    console.phase_start(Phase.BOOT)
    console.phase_done(Phase.BOOT)
    captured = capsys.readouterr()
    assert "... Boot" not in captured.err


def test_json_mode_no_stderr_phases(capsys):
    console = RunConsole(json_mode=True)
    console.phase_start(Phase.BOOT)
    console.note("hidden")
    captured = capsys.readouterr()
    assert captured.err == ""


def test_phase_done_prints_ok(capsys):
    console = RunConsole(json_mode=False, quiet=False, no_color=True)
    console.phase_start(Phase.PREFLIGHT)
    console.phase_done(Phase.PREFLIGHT)
    captured = capsys.readouterr()
    assert "ok Preflight" in captured.err


def test_ledger_event_rate_limit(capsys):
    console = RunConsole(no_color=True, verbose=False)
    console.phase_start(Phase.INVESTIGATE)
    for i in range(5):
        console.ledger_event({"kind": "hypothesis", "claim": f"h{i}"})
    captured = capsys.readouterr()
    assert captured.err.count("[investigate]") <= 2
