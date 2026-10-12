"""loadline load, hint writes, compose merge, and home-config load."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import yaml
from pydantic_ai.models.test import TestModel

from loadline.adapters.runtime.compose_boot import BootOutcome, _COMPOSE_PROFILE, _compose_cmd, boot_repository
from loadline.adapters.runtime.compose_merge import load_project_compose
from loadline.config.fingerprint import config_dir_for_repo
from loadline.load import load_repo
from loadline.load_cmd import load_repository
from loadline.setup_agent import build_setup_agent, hints_from_boot, write_hints_file
from loadline.ui.run_console import RunConsole


def _booted() -> BootOutcome:
    return BootOutcome(
        status="booted",
        exit_code=0,
        boot={
            "health": {"status": "ok", "path": "/healthz"},
            "app_service": "app",
            "container_port": 8000,
            "compose_file": "docker-compose.yml",
        },
    )


def test_hints_from_boot_omit_env():
    doc = hints_from_boot(_booted().boot or {})
    assert doc["app_service"] == "app"
    assert doc["health_path"] == "/healthz"
    assert doc["container_port"] == 8000
    assert "env" not in doc


def test_write_hints_rejects_command(tmp_path: Path):
    ok, err = write_hints_file(tmp_path, {"schema_version": "1", "command": "uvicorn app:app"})
    assert not ok
    assert "command" in err


def test_write_hints_rejects_env_and_socket(tmp_path: Path):
    ok, err = write_hints_file(tmp_path, {"schema_version": "1", "env": {"A": "1"}})
    assert not ok
    assert "env" in err
    ok, err = write_hints_file(tmp_path, {"schema_version": "1", "compose_file": "has-docker.sock"})
    assert not ok
    assert not (tmp_path / ".loadline.yaml").exists()


def test_load_writes_successful_hints(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("loadline.load_cmd.boot_repository", lambda *a, **k: _booted())
    code = load_repository(tmp_path, require_auth=False)
    assert code == 0
    text = (tmp_path / ".loadline.yaml").read_text(encoding="utf-8")
    assert "app_service: app" in text
    assert "health_path: /healthz" in text
    assert "env:" not in text
    assert "FIX_ENABLED" not in text


def test_empty_no_entrypoint_does_not_call_setup(tmp_path: Path, monkeypatch):
    calls: list[int] = []
    blocked = BootOutcome(
        status="blocked",
        exit_code=10,
        blocker={
            "code": "no_entrypoint",
            "summary": "No Compose file or Dockerfile was found.",
            "retryable": True,
            "security": False,
        },
    )
    monkeypatch.setattr("loadline.load_cmd.boot_repository", lambda *a, **k: blocked)

    def runner(repo, outcome):
        calls.append(1)
        return outcome

    code = load_repository(tmp_path, require_auth=False, setup_runner=runner)
    assert code == 10
    assert calls == []


def test_policy_refused_does_not_call_setup(tmp_path: Path, monkeypatch):
    calls: list[int] = []
    refused = BootOutcome(
        status="blocked",
        exit_code=10,
        blocker={
            "code": "policy_refused",
            "summary": "service proxy has a host bind mount",
            "retryable": False,
            "security": True,
        },
    )
    monkeypatch.setattr("loadline.load_cmd.boot_repository", lambda *a, **k: refused)

    def runner(repo, outcome):
        calls.append(1)
        return outcome

    code = load_repository(tmp_path, require_auth=False, setup_runner=runner)
    assert code == 10
    assert calls == []
    assert not (tmp_path / ".loadline.yaml").exists()


def test_retryable_blocker_calls_setup_once(tmp_path: Path, monkeypatch):
    calls: list[str] = []
    blocked = BootOutcome(
        status="blocked",
        exit_code=10,
        blocker={"code": "boot_failed", "summary": "config failed", "retryable": True, "security": False},
    )
    monkeypatch.setattr("loadline.load_cmd.boot_repository", lambda *a, **k: blocked)

    def runner(repo, outcome):
        calls.append(outcome.blocker["code"])
        return _booted()

    code = load_repository(tmp_path, require_auth=False, setup_runner=runner)
    assert code == 0
    assert calls == ["boot_failed"]
    assert "health_path: /healthz" in (tmp_path / ".loadline.yaml").read_text(encoding="utf-8")


def test_setup_tools_are_only_config_boot_and_hints():
    agent = build_setup_agent(TestModel())
    names = set(agent._function_toolset.tools)
    assert names == {"read_config", "try_boot", "write_hints"}


def test_merge_uses_both_compose_files(tmp_path: Path, monkeypatch):
    (tmp_path / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "compose.override.yaml").write_text(
        "services:\n  web:\n    command: from-override\n",
        encoding="utf-8",
    )
    captured: dict[str, list[str]] = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)

        class Proc:
            returncode = 0
            stdout = '{"services": {"web": {"command": "from-override"}}}'
            stderr = ""

        return Proc()

    monkeypatch.setattr("loadline.adapters.runtime.compose_merge.subprocess.run", fake_run)
    data, err = load_project_compose(tmp_path, tmp_path / "compose.yaml")
    assert err is None
    assert data is not None
    assert data["services"]["web"]["command"] == "from-override"
    assert captured["argv"].count("-f") == 2


def test_compose_profile_is_passed_to_docker(tmp_path: Path, monkeypatch):
    captured: dict[str, list[str]] = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)

        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        return Proc()

    monkeypatch.setattr("subprocess.run", fake_run)
    token = _COMPOSE_PROFILE.set("edge")
    try:
        _compose_cmd("proj", tmp_path / "compose.yaml", tmp_path, ["ps"])
    finally:
        _COMPOSE_PROFILE.reset(token)
    argv = captured["argv"]
    assert argv[argv.index("--profile") + 1] == "edge"


def test_compose_timeout_returns_failed_process(tmp_path: Path, monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["docker"], timeout=kwargs.get("timeout") or 1)

    monkeypatch.setattr("subprocess.run", fake_run)
    proc = _compose_cmd("proj", tmp_path / "compose.yaml", tmp_path, ["up"], timeout=3)
    assert proc.returncode == 124
    assert "timed out after 3s" in proc.stderr


def test_compose_config_failure_is_retryable(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path / "home"))
    (tmp_path / "compose.yaml").write_text("services:\n  app:\n    image: x\n", encoding="utf-8")
    monkeypatch.setattr(
        "loadline.adapters.runtime.compose_boot.load_project_compose",
        lambda repo, path: (None, "config failed"),
    )
    outcome = boot_repository(tmp_path, teardown=True, require_auth=False)
    assert outcome.blocker is not None
    assert outcome.blocker["retryable"] is True
    assert outcome.blocker["security"] is False
    assert outcome.blocker["code"] == "boot_failed"



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
