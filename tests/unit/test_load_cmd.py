"""loadline load, hint writes, and compose merge."""

import subprocess
from pathlib import Path

from pydantic_ai.models.test import TestModel

from loadline.adapters.runtime.compose_boot import BootOutcome, _COMPOSE_PROFILE, _compose_cmd, boot_repository
from loadline.adapters.runtime.compose_merge import load_project_compose
from loadline.load_cmd import load_repository
from loadline.setup_agent import build_setup_agent, hints_from_boot, write_hints_file


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
