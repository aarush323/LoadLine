from pathlib import Path
from unittest.mock import patch

from loadline.cli import main
from loadline.run_pipeline import RunPipelineResult


def test_bare_loadline_non_tty_prints_help(capsys, monkeypatch):
    monkeypatch.setattr("loadline.cli.is_tty", lambda _stream: False)
    code = main([])
    captured = capsys.readouterr()
    assert code == 2
    assert "usage:" in captured.out.lower()


def test_bare_loadline_tty_opens_workspace(monkeypatch):
    monkeypatch.setattr("loadline.cli.is_tty", lambda _stream: True)
    called = {}

    def fake_workspace(**kwargs):
        called["normalize"] = kwargs.get("normalize")
        return 0

    monkeypatch.setattr("loadline.ui.workspace.run_workspace", fake_workspace)
    assert main([]) == 0
    assert called["normalize"] is not None


def test_run_json_stdout_no_progress_on_stderr(capsys, tmp_path):
    fake = RunPipelineResult(
        exit_code=0,
        status="baseline_only",
        run_id="abc",
        run_dir=tmp_path,
        report_md=tmp_path / "report.md",
        phases=[],
    )
    (tmp_path / "report.md").write_text("# Loadline report\n")
    with patch("loadline.cli.run_loadline", return_value=fake):
        code = main(["run", "--repo", str(tmp_path), "--json", "--no-report-print"])
    captured = capsys.readouterr()
    assert code == 0
    assert "exit_code" in captured.out
    assert "... Boot" not in captured.err


def test_report_show_prints_markdown(capsys, tmp_path):
    (tmp_path / "report.md").write_text("# hello\n")
    code = main(["report", "show", str(tmp_path)])
    captured = capsys.readouterr()
    assert code == 0
    assert "# hello" in captured.out
