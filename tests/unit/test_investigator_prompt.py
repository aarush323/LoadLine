from pathlib import Path

from loadline.core.leakage import _forbidden_tokens
from loadline.investigator.prompt import load_investigator_prompt


def test_prompt_lists_three_tools():
    root = Path(__file__).resolve().parents[2]
    text = (root / "agents" / "investigator_prompt.md").read_text()
    assert "action=routes" in text
    assert "run_k6(endpoints" in text
    assert "read_file(path" in text
    assert "run_k6(endpoints" in text
    assert "{{BOARD}}" not in text
    loaded = load_investigator_prompt(root)
    assert loaded == text


def test_prompt_has_no_fixture_tokens():
    root = Path(__file__).resolve().parents[2]
    text = (root / "agents" / "investigator_prompt.md").read_text()
    for token in _forbidden_tokens(root):
        assert token not in text
