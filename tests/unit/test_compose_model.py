import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import yaml

from loadline.config import compose_model as cm


def _repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    base = repo / "compose.yaml"
    base.write_text(yaml.safe_dump({"services": {"web": {"image": "x"}}}))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    return repo, base, run_dir


def test_command_contains_f_base_project_env(tmp_path: Path):
    repo, base, run_dir = _repo(tmp_path)
    (repo / ".env").write_text("A=1\n")
    files = cm.resolve_files(repo, base, None)
    _, env_arg = cm.ensure_runtime_env(repo, run_dir, yaml.safe_load(base.read_text()))
    cmd = cm.build_compose_command(repo, files, env_arg)
    assert "-f" in cmd
    assert str(base) in cmd
    assert "--project-directory" in cmd
    assert str(repo) in cmd[cmd.index("--project-directory") + 1]
    assert "--env-file" in cmd
    # -f must not be omitted.
    assert cmd.count("-f") >= 1


def test_parent_env_absent_from_subprocess_env(tmp_path: Path, monkeypatch):
    repo, base, run_dir = _repo(tmp_path)
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret123")
    env = cm.restricted_env()
    assert "POSTGRES_PASSWORD" not in env
    assert "PATH" in env
    captured: dict = {}

    def fake_run(*a, **k):
        captured["env"] = k.get("env")
        return subprocess.CompletedProcess(args=a, returncode=0, stdout="{}", stderr="")

    with patch("loadline.config.compose_model.subprocess.run", side_effect=fake_run):
        cm.run_compose_config(repo, [base], run_dir / ".env.empty")
    assert captured["env"] is not None
    assert "POSTGRES_PASSWORD" not in captured["env"]


def test_files_unset_does_not_add_override(tmp_path: Path):
    repo, base, run_dir = _repo(tmp_path)
    (repo / "compose.override.yml").write_text(yaml.safe_dump({"services": {"extra": {"image": "y"}}}))
    files = cm.resolve_files(repo, base, None)
    assert files == [base]
    cmd = cm.build_compose_command(repo, files, run_dir / ".env.empty")
    assert "compose.override.yml" not in " ".join(cmd)


def test_rewritten_build_context_under_run_is_invalid(tmp_path: Path):
    repo, base, run_dir = _repo(tmp_path)
    resolved = {"services": {"web": {"build": {"context": str(run_dir)}}}}
    blocker = cm.validate_resolved_paths(repo, run_dir, resolved)
    assert blocker is not None
    assert blocker["code"] == "compose_invalid"


def test_missing_env_rewritten_and_bind_stays(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    base = repo / "compose.yaml"
    base.write_text(
        yaml.safe_dump(
            {
                "services": {
                    "web": {
                        "image": "x",
                        "env_file": [".env.missing"],
                        "volumes": ["./db/init.sql:/docker-entrypoint-initdb.d/init.sql"],
                    }
                }
            }
        )
    )
    (repo / ".env.example").write_text("A=example\n")
    (repo / "db").mkdir()
    (repo / "db" / "init.sql").write_text("select 1;")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    raw = yaml.safe_load(base.read_text())
    runtime, env_arg = cm.ensure_runtime_env(repo, run_dir, raw)
    # Missing env_file rewritten to absolute run-dir path, repo untouched.
    assert not (repo / ".env.missing").exists()
    assert env_arg.is_file()
    assert str(env_arg).startswith(str(run_dir))
    # Bind ./db/init.sql stays under repo → no blocker.
    resolved = {"services": {"web": {"volumes": ["./db/init.sql:/x"]}}}
    assert cm.validate_resolved_paths(repo, run_dir, resolved) is None


def test_docker_compose_config_uses_f_and_env(tmp_path: Path):
    repo, base, run_dir = _repo(tmp_path)
    (repo / ".env").write_text("A=1\n")
    captured: dict = {}

    class Proc:
        returncode = 0
        stdout = yaml.safe_dump({"services": {"web": {"image": "x"}}})
        stderr = ""

    def fake_cmd(cmd, timeout=60):
        captured["cmd"] = cmd
        return Proc()

    with patch("loadline.config.compose_model.docker_cmd", side_effect=fake_cmd):
        resolved, blocker, cmd = cm.docker_compose_config(repo, base, None, run_dir)
    assert blocker is None
    assert resolved is not None
    assert "-f" in captured["cmd"]
    assert "--project-directory" in captured["cmd"]
    assert "--env-file" in captured["cmd"]
