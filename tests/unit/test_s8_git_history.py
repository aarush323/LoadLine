import json
import subprocess
from pathlib import Path

import pytest

from tests.eval.acceptance import git_history_claim_allowed
from tests.eval.oracle_io import load_sealed_oracle

TARGET = Path(__file__).resolve().parents[2] / "integration" / "targets" / "full-stack-fastapi-template"
LOCK = Path(__file__).resolve().parents[2] / "integration" / "targets.lock.json"


def test_git_history_oracle_matches_lock_pin():
    oracle = load_sealed_oracle("git-history.sealed.yaml")
    lock = json.loads(LOCK.read_text())
    assert oracle["fix_commit"] == lock["commit"]


@pytest.mark.skipif(not TARGET.is_dir(), reason="reference target not cloned")
def test_git_history_parent_matches_target_repo():
    oracle = load_sealed_oracle("git-history.sealed.yaml")
    parent = subprocess.check_output(
        ["git", "-C", str(TARGET), "rev-parse", f"{oracle['fix_commit']}^"],
        text=True,
    ).strip()
    assert parent == oracle["parent_commit"]


def test_git_history_forbids_fix_only_narrative_without_prediction():
    oracle = load_sealed_oracle("git-history.sealed.yaml")
    finding = {
        "mechanism": "Upgrade to @tanstack/react-table 9 caused the regression",
        "observed_facts": ["package.json names tanstack/react-table"],
    }
    assert not git_history_claim_allowed(
        finding,
        [],
        forbidden_substrings=oracle["forbidden_claim_substrings_without_confirmed_prediction"],
    )
