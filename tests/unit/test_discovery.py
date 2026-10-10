from pathlib import Path

from loadline.discovery.intake import discover_capabilities, discover_profile


def test_discover_fixture_compose():
    root = Path(__file__).resolve().parents[1] / "fixtures" / "fx-pyhttp-pg"
    profile = discover_profile(root)
    assert profile["compose_files"]
    caps = discover_capabilities(profile)
    assert caps["runtime"]["level"] == "ready"
    assert not caps["blockers"]
