"""Comparator and patch gate. No model, no Docker."""

from pathlib import Path

from loadline.investigator.deps import ReadRange
from loadline.investigator.run import persist_reads
from loadline.investigator.tools import read_file
from loadline.verification import (
    changed_paths,
    judge_replay,
    metrics_from_experiment,
    patch_rejection,
    range_covered,
)
from tests.unit.test_investigator_tools import _ctx


def _row(p95: float, err: float = 0.0, rps: float = 10.0) -> dict:
    return {"p95_ms": p95, "error_rate": err, "achieved_rps": rps}


def test_flat_p95_is_hypothesis_failed():
    verdict = judge_replay(
        metric="p95_ms",
        cited_before=_row(400),
        cited_after=_row(390),
        control_before=_row(8),
        control_after=_row(8),
    )
    assert verdict == "hypothesis_failed"


def test_cited_flat_while_other_route_improves_is_hypothesis_failed():
    verdict = judge_replay(
        metric="p95_ms",
        cited_before=_row(400),
        cited_after=_row(400),
        control_before=_row(80),
        control_after=_row(10),
    )
    assert verdict == "hypothesis_failed"


def test_control_regression():
    verdict = judge_replay(
        metric="p95_ms",
        cited_before=_row(400),
        cited_after=_row(30),
        control_before=_row(10),
        control_after=_row(40),
    )
    assert verdict == "regressed_control"


def test_improved_when_cited_drops_and_control_holds():
    verdict = judge_replay(
        metric="p95_ms",
        cited_before=_row(400),
        cited_after=_row(30),
        control_before=_row(10),
        control_after=_row(11),
    )
    assert verdict == "improved"


def test_model_digit_is_ignored():
    experiment = {
        "output": {
            "operations": {
                "items": {"p95_ms": 410, "error_rate": 0.0, "achieved_rps": 9.8},
            }
        }
    }
    prose = "The model claimed p95: 12 after the change."
    before = metrics_from_experiment(experiment, "items")
    assert "12" in prose
    assert before["p95_ms"] == 410


def test_compose_and_dockerfile_diffs_are_rejected():
    compose = "diff --git a/docker-compose.yml b/docker-compose.yml\n--- a/docker-compose.yml\n+++ b/docker-compose.yml\n"
    docker = "diff --git a/Dockerfile b/Dockerfile\n--- a/Dockerfile\n+++ b/Dockerfile\n"
    assert patch_rejection(compose, "app.py")
    assert patch_rejection(docker, "app.py")
    assert "docker-compose.yml" in changed_paths(compose)


def test_loadline_yaml_env_change_is_not_a_patch():
    diff = (
        "diff --git a/.loadline.yaml b/.loadline.yaml\n"
        "--- a/.loadline.yaml\n"
        "+++ b/.loadline.yaml\n"
        "+env:\n"
        "+  FIX_ENABLED: 'true'\n"
    )
    reason = patch_rejection(diff, ".loadline.yaml")
    assert reason
    assert patch_rejection(diff, "app.py")


def test_read_range_must_cover_contract_lines():
    reads = [{"path": "app.py", "start_line": 1, "end_line": 20, "evidence_id": "ev-read-1"}]
    assert range_covered("app.py", 12, 18, reads)
    assert not range_covered("app.py", 12, 40, reads)
    assert not range_covered("other.py", 12, 18, reads)


def test_persist_reads_writes_evidence_id(tmp_path: Path):
    src = tmp_path / "app.py"
    src.write_text("a\nb\nc\n")
    ctx = _ctx(tmp_path)
    out = read_file(ctx, "app.py", 1, 2)
    assert out["evidence_id"] == "ev-read-1"
    path = persist_reads(ctx.deps.run_dir, ctx.deps.read_ranges)
    line = path.read_text(encoding="utf-8").strip()
    assert '"path":"app.py"' in line
    assert '"start_line":1' in line
    assert '"end_line":2' in line
    assert '"evidence_id":"ev-read-1"' in line
    assert isinstance(ctx.deps.read_ranges[0], ReadRange)
