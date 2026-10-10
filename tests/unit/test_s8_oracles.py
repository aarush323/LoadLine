from pathlib import Path

import yaml

from tests.eval.oracle_io import ORACLES_DIR, list_sealed_oracles, load_sealed_oracle


def test_sealed_oracles_directory_exists():
    assert ORACLES_DIR.is_dir()
    names = [p.name for p in list_sealed_oracles()]
    assert "fx-pyhttp-pg.sealed.yaml" in names
    assert "fx-docker-http.sealed.yaml" in names
    assert "git-history.sealed.yaml" in names


def test_sealed_oracles_parse():
    for path in list_sealed_oracles():
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert data.get("fixture") or data.get("case_id")


def test_load_sealed_oracle_helper():
    data = load_sealed_oracle("hidden-misleading-comment.sealed.yaml")
    assert data["case_id"] == "hidden-misleading-comment"


def test_loadline_does_not_reference_oracles_dir():
    root = Path(__file__).resolve().parents[2]
    loadline = root / "loadline"
    needle = "tests/oracles"
    for path in loadline.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert needle not in text, f"{path} references sealed oracles path"
