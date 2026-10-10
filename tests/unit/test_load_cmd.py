from pathlib import Path
from unittest.mock import patch

import yaml

from loadline.adapters.runtime.compose_boot import BootOutcome
from loadline.config.fingerprint import config_dir_for_repo
from loadline.load import load_repo
from loadline.ui.run_console import RunConsole


def _repo_with_compose(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "compose.yaml").write_text(
        yaml.safe_dump({"services": {"web": {"build": ".", "ports": ["8000:8000"]}}})
    )
    return repo


def test_load_writes_home_not_repo(tmp_path: Path, monkeypatch):
    repo = _repo_with_compose(tmp_path)
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path / "home"))

    class Proc:
        returncode = 0
        stdout = "{}"
        stderr = ""

    booted = BootOutcome(
        status="booted",
        exit_code=0,
        boot={"health": {"url": "http://web:8000/health"}, "run_dir": str(tmp_path / "run")},
        run_id="r1",
    )
    from loadline.config.resolve import ResolvedConfig
    from loadline.config.target import Target

    cfg = ResolvedConfig(
        hints=None,
        compose_file="compose.yaml",
        target=Target(service="web", port=8000, health_path="/health", origin="http://web:8000/health"),
        blocker=None,
        error=None,
        prepare=[],
        auth={},
        start_set="all",
    )
    with patch("loadline.adapters.runtime.docker_runner.docker_cmd", return_value=Proc()):
        with patch("loadline.config.resolve.resolve", return_value=cfg):
            with patch(
                "loadline.discovery.intake.discover_profile",
                return_value={"compose_files": ["compose.yaml"], "dockerfiles": []},
            ):
                with patch(
                    "loadline.adapters.runtime.boot_and_prepare.boot_and_prepare",
                    return_value=booted,
                ) as mocked_boot:
                    code = load_repo(repo, write_to_repo=False)
                    mocked_boot.assert_called_once()
    assert code == 0
    out = config_dir_for_repo(repo) / "loadline.yaml"
    assert out.is_file()
    assert not (repo / ".loadline.yaml").is_file()
    data = yaml.safe_load(out.read_text())
    assert data["app_service"] == "web"
    assert data["meta"]["fingerprint"]


def test_fingerprint_mismatch_warns_but_boots(tmp_path: Path, monkeypatch):
    repo = _repo_with_compose(tmp_path)
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path / "home"))
    out_dir = config_dir_for_repo(repo)
    out_dir.mkdir(parents=True)
    (out_dir / "loadline.yaml").write_text(
        yaml.safe_dump(
            {
                "compose_file": "compose.yaml",
                "app_service": "web",
                "container_port": 8000,
                "health_path": "/health",
                "compose": {"start_set": "all"},
                "prepare": [],
                "auth": {},
                "meta": {"fingerprint": "stale"},
            }
        )
    )
    from loadline.config.fingerprint import check_fingerprint_warning

    warn = check_fingerprint_warning(repo)
    assert warn is not None
    assert "warning" in warn.lower()
    booted = BootOutcome(status="blocked", exit_code=10, blocker={"code": "x"}, run_id="r1")
    with patch("loadline.run_pipeline.boot_and_prepare", return_value=booted) as mocked:
        from loadline.run_pipeline import run_loadline

        result = run_loadline(repo, require_auth=False)
        mocked.assert_called_once()
    assert result.exit_code == 10


def test_load_prints_progress_on_stderr(capsys, tmp_path: Path, monkeypatch):
    repo = _repo_with_compose(tmp_path)
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path / "home"))

    class Proc:
        returncode = 0
        stdout = "{}"
        stderr = ""

    booted = BootOutcome(
        status="booted",
        exit_code=0,
        boot={"health": {"url": "http://web:8000/health"}, "run_dir": str(tmp_path / "run")},
        run_id="r1",
    )
    from loadline.config.resolve import ResolvedConfig
    from loadline.config.target import Target

    cfg = ResolvedConfig(
        hints=None,
        compose_file="compose.yaml",
        target=Target(service="web", port=8000, health_path="/health", origin="http://web:8000/health"),
        blocker=None,
        error=None,
        prepare=[],
        auth={},
        start_set="all",
    )
    ui = RunConsole(quiet=False, verbose=False, json_mode=False)
    with patch("loadline.adapters.runtime.docker_runner.docker_cmd", return_value=Proc()):
        with patch("loadline.config.resolve.resolve", return_value=cfg):
            with patch(
                "loadline.discovery.intake.discover_profile",
                return_value={"compose_files": ["compose.yaml"], "dockerfiles": []},
            ):
                with patch(
                    "loadline.adapters.runtime.boot_and_prepare.boot_and_prepare",
                    return_value=booted,
                ):
                    with patch("loadline.load.agent.should_call_agent", return_value=False):
                        code = load_repo(repo, write_to_repo=False, console=ui)
    assert code == 0
    err = capsys.readouterr().err
    assert "loadline load" in err
    assert "Resolve:" in err
    assert "Boot" in err
    assert "Write config" in err


def test_load_quiet_hides_progress(capsys, tmp_path: Path, monkeypatch):
    repo = _repo_with_compose(tmp_path)
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path / "home"))

    class Proc:
        returncode = 0
        stdout = "{}"
        stderr = ""

    from loadline.config.resolve import ResolvedConfig

    cfg = ResolvedConfig(
        hints=None,
        compose_file="compose.yaml",
        target=None,
        blocker={"summary": "No application service found in compose."},
        error=None,
        prepare=[],
        auth={},
        start_set="all",
    )
    ui = RunConsole(quiet=True, verbose=False, json_mode=False)
    with patch("loadline.adapters.runtime.docker_runner.docker_cmd", return_value=Proc()):
        with patch("loadline.config.resolve.resolve", return_value=cfg):
            with patch(
                "loadline.discovery.intake.discover_profile",
                return_value={"compose_files": ["compose.yaml"], "dockerfiles": []},
            ):
                code = load_repo(repo, console=ui)
    assert code == 10
    err = capsys.readouterr().err
    assert "blocked:" in err
    assert "loadline load" not in err
    assert "trace:" not in err


def test_cli_load_quiet_flag(capsys, tmp_path: Path):
    from loadline.cli import main

    with patch("loadline.load.load_repo", return_value=0) as mocked:
        code = main(["load", "--repo", str(tmp_path), "--quiet"])
    assert code == 0
    _, kwargs = mocked.call_args
    assert kwargs.get("console") is not None
    assert kwargs["console"].quiet is True


def test_cli_has_run_load_no_setup():
    import loadline.cli as cli

    src = Path(cli.__file__).read_text()
    assert '"load"' in src or "'load'" in src
    assert '"run"' in src or "'run'" in src
    assert "setup" not in src or 'add_parser("setup")' not in src
    assert 'add_parser("setup")' not in src
    assert "add_parser('setup')" not in src
    # Functional: load parser exists, setup does not.
    import argparse

    # Re-parse minimal args to ensure load is accepted (mock to avoid docker).
    from unittest.mock import patch

    with patch("loadline.load.load_repo", return_value=0):
        assert cli.main(["load", "--repo", "."]) == 0
