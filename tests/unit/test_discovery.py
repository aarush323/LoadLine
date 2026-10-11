from pathlib import Path

from loadline.discovery.intake import discover_capabilities, discover_profile, ensure_launch_files


def test_discover_fixture_compose():
    root = Path(__file__).resolve().parents[1] / "fixtures" / "fx-pyhttp-pg"
    profile = discover_profile(root)
    assert profile["compose_files"]
    caps = discover_capabilities(profile)
    assert caps["runtime"]["level"] == "ready"
    assert not caps["blockers"]


def test_ensure_launch_files_recovers_root_compose_after_empty_walk(tmp_path: Path):
    (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    repaired = ensure_launch_files(
        tmp_path,
        {"compose_files": [], "dockerfiles": []},
        compose_file="docker-compose.yml",
        dockerfile="Dockerfile",
    )
    assert repaired["compose_files"] == ["docker-compose.yml"]
    assert repaired["dockerfiles"] == ["Dockerfile"]
    caps = discover_capabilities(repaired)
    assert not caps["blockers"]
