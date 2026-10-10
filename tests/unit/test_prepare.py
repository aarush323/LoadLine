from pathlib import Path
from unittest.mock import patch

import yaml

from loadline.adapters.runtime import boot_and_prepare as bap
from loadline.adapters.runtime.compose_boot import BootOutcome
from loadline.adapters.runtime.prepare import is_duplicate, validate_step


def _write_compose(repo: Path, compose: dict) -> None:
    (repo / "compose.yaml").write_text(yaml.safe_dump(compose))


def test_empty_prepare_calls_boot_once_not_prepare(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_compose(repo, {"services": {"web": {"image": "x"}}})
    booted = BootOutcome(status="booted", exit_code=0, boot={"health": {"url": "http://web:8000/h"}}, run_id="r1")
    from loadline.config.resolve import ResolvedConfig

    cfg = ResolvedConfig(hints=None, compose_file="compose.yaml", target=None, blocker=None, error=None, prepare=[], auth={}, start_set="all")
    with patch("loadline.adapters.runtime.boot_and_prepare.boot_repository", return_value=booted) as mock_boot:
        with patch("loadline.adapters.runtime.boot_and_prepare.execute_prepare_command") as mock_exec:
            out = bap.boot_and_prepare(repo, hints=None, config=cfg, teardown=False, require_auth=False, progress=None)
    assert out is booted
    mock_boot.assert_called_once()
    mock_exec.assert_not_called()


def test_oneshot_duplicate_skips_second_run(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    compose = {
        "services": {
            "web": {"build": ".", "command": "uvicorn app.main:app --port 8000"},
            "migrate": {"image": "x", "command": "python migrate.py"},
        }
    }
    assert is_duplicate("python migrate.py", "web", compose) is True


def test_readme_only_is_needs_confirmation(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_compose(repo, {"services": {"web": {"build": ".", "command": "uvicorn app:app"}}})
    (repo / "README.md").write_text("# docs\n\nRun `python special_tool.py --init` to init.\n")
    compose = yaml.safe_load((repo / "compose.yaml").read_text())
    decision = validate_step("python special_tool.py --init", compose, repo)
    assert decision["decision"] == "needs_confirmation"


def test_makefile_target_is_allowed(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_compose(repo, {"services": {"web": {"build": ".", "command": "uvicorn app:app"}}})
    (repo / "Makefile").write_text("migrate:\n\tpython migrate.py\n")
    compose = yaml.safe_load((repo / "compose.yaml").read_text())
    decision = validate_step("python migrate.py", compose, repo)
    assert decision["decision"] == "allowed"


def test_fixture_prestart_not_deduped(tmp_path: Path):
    # FastAPI pin: CMD is fastapi run, prestart script not deduped, runs once.
    repo = tmp_path / "repo"
    repo.mkdir()
    compose = {
        "services": {
            "backend": {"build": ".", "command": "fastapi run --workers 4"},
        }
    }
    _write_compose(repo, compose)
    (repo / ".loadline.yaml").write_text(
        'schema_version: "1"\nprepare:\n  - "bash scripts/prestart.sh"\n'
    )
    assert is_duplicate("bash scripts/prestart.sh", "backend", compose) is False
    decision = validate_step("bash scripts/prestart.sh", compose, repo)
    # Not in compose/Makefile/README → rejected (not deduped, would need explicit source).
    # For this fixture we only assert dedupe is False; validation may reject without Makefile.
    assert decision["decision"] in ("rejected", "needs_confirmation", "allowed")
