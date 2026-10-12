from pathlib import Path

from loadline.run_pipeline import RunPipelineResult
from loadline.ui.toggle import apply_toggle_key, toggle_choice
from loadline.ui.workspace import run_session, run_workspace


def test_apply_toggle_key_moves_and_confirms():
    assert apply_toggle_key(0, 2, "\x1b[C") == (1, None)
    assert apply_toggle_key(1, 2, "\x1b[D") == (0, None)
    assert apply_toggle_key(0, 2, "\r") == (0, "confirm")
    assert apply_toggle_key(1, 2, "q") == (1, "abort")


def test_toggle_choice_selects_second_option(tmp_path, capsys):
    idx = toggle_choice(
        "Go?",
        ["Yes", "No"],
        default=0,
        keys=["\x1b[C", "\r"],
        writer=__import__("io").StringIO(),
    )
    assert idx == 1


def test_toggle_choice_abort(capsys):
    idx = toggle_choice(
        "Go?",
        ["Yes", "No"],
        keys=["q"],
        writer=__import__("io").StringIO(),
    )
    assert idx is None


def test_session_load_failure_skips_run(tmp_path):
    ran = {"run": False, "verify": False}

    def load(_repo: Path) -> int:
        return 10

    def run(_repo: Path) -> RunPipelineResult:
        ran["run"] = True
        return RunPipelineResult(exit_code=0)

    def verify(_path: Path, _pr: bool) -> int:
        ran["verify"] = True
        return 0

    code = run_session(
        tmp_path,
        load_fn=load,
        run_fn=run,
        verify_fn=verify,
        toggle_fn=lambda q, o: 0,
    )
    assert code == 10
    assert ran["run"] is False
    assert ran["verify"] is False


def test_session_run_no_skips_run(tmp_path):
    ran = {"run": False}

    def run(_repo: Path) -> RunPipelineResult:
        ran["run"] = True
        return RunPipelineResult(exit_code=0)

    code = run_session(
        tmp_path,
        load_fn=lambda _r: 0,
        run_fn=run,
        verify_fn=lambda _p, _pr: 0,
        toggle_fn=lambda q, o: 1 if "investigation" in q else 0,
    )
    assert code == 0
    assert ran["run"] is False


def test_session_run_failure_skips_verify(tmp_path):
    verified = []

    code = run_session(
        tmp_path,
        load_fn=lambda _r: 0,
        run_fn=lambda _r: RunPipelineResult(exit_code=3, status="investigation_failed"),
        verify_fn=lambda p, pr: verified.append((p, pr)) or 0,
        toggle_fn=lambda q, o: 0,
    )
    assert code == 3
    assert verified == []


def test_session_wires_run_dir_without_pr(tmp_path):
    run_dir = tmp_path / "runs" / "abc123"
    run_dir.mkdir(parents=True)
    seen: list[tuple[Path, bool]] = []

    def toggle(question: str, options: list[str]) -> int:
        if "Verify" in question:
            assert "abc123" in question
            assert options[1] == "Without pull request"
            return 1
        return 0

    code = run_session(
        tmp_path,
        load_fn=lambda _r: 0,
        run_fn=lambda _r: RunPipelineResult(
            exit_code=0,
            run_id="abc123",
            run_dir=run_dir,
            status="completed",
        ),
        verify_fn=lambda p, pr: seen.append((p, pr)) or 0,
        toggle_fn=toggle,
    )
    assert code == 0
    assert seen == [(run_dir, False)]


def test_session_wires_run_dir_with_pr(tmp_path):
    run_dir = tmp_path / "runs" / "zzz999"
    run_dir.mkdir(parents=True)
    seen: list[tuple[Path, bool]] = []

    code = run_session(
        tmp_path,
        load_fn=lambda _r: 0,
        run_fn=lambda _r: RunPipelineResult(
            exit_code=0,
            run_id="zzz999",
            run_dir=run_dir,
            status="completed",
        ),
        verify_fn=lambda p, pr: seen.append((p, pr)) or 0,
        toggle_fn=lambda q, o: 0,
    )
    assert code == 0
    assert seen == [(run_dir, True)]


def test_workspace_missing_path(tmp_path):
    missing = tmp_path / "nope"
    code = run_workspace(
        default_repo=tmp_path,
        ask_path=lambda _d: missing,
        draw=False,
        load_fn=lambda _r: 0,
        run_fn=lambda _r: RunPipelineResult(exit_code=0),
        verify_fn=lambda _p, _pr: 0,
        toggle_fn=lambda q, o: 1,
    )
    assert code == 2
