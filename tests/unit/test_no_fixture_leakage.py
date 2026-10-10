from pathlib import Path

from loadline.core.leakage import scan_loadline_package


def test_no_fixture_leakage():
    root = Path(__file__).resolve().parents[2]
    hits = scan_loadline_package(root)
    assert hits == []
