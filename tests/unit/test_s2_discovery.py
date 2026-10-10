from pathlib import Path
from unittest.mock import patch

from loadline.cli import main
from loadline.discovery.intake import discover_capabilities, discover_profile


def _write_compose_repo(tmp_path: Path) -> Path:
    (tmp_path / "compose.yaml").write_text(
        "services:\n  web:\n    image: example/web\n    command: uvicorn app:app --host 0.0.0.0\n"
    )
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    (tmp_path / "requirements.txt").write_text("fastapi\npsycopg2\n")
    return tmp_path


def test_discover_compose_and_manifests_in_temp_repo(tmp_path: Path):
    root = _write_compose_repo(tmp_path)
    profile = discover_profile(root)
    assert profile["compose_files"] == ["compose.yaml"]
    assert any(m["kind"] == "pyproject.toml" for m in profile["manifests"])
    assert any(e["source"] == "compose" for e in profile["entrypoints"])
    assert any(c["library"] == "postgres" for c in profile["dependency_clients"])
    assert profile["contradictions"]
    caps = discover_capabilities(profile)
    assert caps["runtime"]["level"] == "ready"
    assert caps["contradictions"]


def test_ci_workflow_is_evidence_not_executed(tmp_path: Path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text(
        """
name: CI
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
    steps:
      - run: pytest -q
"""
    )
    (tmp_path / "compose.yaml").write_text("services:\n  app:\n    image: x\n")

    import inspect

    import loadline.discovery.intake as intake_mod

    ci_source = inspect.getsource(intake_mod._ci_workflows)
    assert "subprocess" not in ci_source
    assert "Popen" not in ci_source

    profile = discover_profile(tmp_path)
    assert profile["ci_workflows"]
    assert profile["ci_workflows"][0]["evidence_only"] is True
    assert profile["ci_workflows"][0]["jobs"][0]["run_commands"] == ["pytest -q"]


def test_external_urls_classified_with_target_guard_kinds(tmp_path: Path):
    (tmp_path / "README.md").write_text(
        "Dev at http://localhost:8000 and prod at https://bucket.s3.amazonaws.com/x\n"
    )
    profile = discover_profile(tmp_path)
    kinds = {u["kind"] for u in profile["external_urls"]}
    assert "local_dev" in kinds
    assert "external" in kinds


def test_analyze_json_exits_zero_without_docker(tmp_path: Path):
    _write_compose_repo(tmp_path)
    with patch("loadline.adapters.runtime.docker_runner.docker_cmd") as mock_docker:
        code = main(["analyze", str(tmp_path), "--json"])
    assert code == 0
    mock_docker.assert_not_called()
