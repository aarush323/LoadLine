"""loadline verify without a model or Docker."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from loadline.verify_cmd import (
    _worktree_blocks_patch,
    build_range_diff,
    parse_fix_fence,
    render_comparison,
    render_pr_body,
    verify_run,
)

DIFF = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-value = 1
+value = 2
"""

FENCE = """# Report

```yaml
loadline_fix:
  experiment_id: exp-k6-0003
  operation_id: items
  metric: p95_ms
  direction: decrease
  control_operation_id: health
  path: app.py
  start_line: 1
  end_line: 1
  rationale: one sentence
```
"""


def _git_identity(repo: Path, *args: str) -> None:
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "test"
    env["GIT_AUTHOR_EMAIL"] = "test@example.com"
    env["GIT_COMMITTER_NAME"] = "test"
    env["GIT_COMMITTER_EMAIL"] = "test@example.com"
    subprocess.run(["git", "-C", str(repo), *args], check=True, env=env, capture_output=True, text=True)


def _repo(path: Path) -> None:
    path.mkdir()
    (path / "app.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "add", "app.py"], check=True, capture_output=True)
    _git_identity(path, "commit", "-m", "init")


def _experiment(p95: float, *, health: float = 6.0, dropped: int = 0) -> dict:
    return {
        "experiment_id": "exp-k6-0003",
        "input": {
            "endpoints": [
                {"id": "items", "method": "GET", "path": "/api/items"},
                {"id": "health", "method": "GET", "path": "/health"},
            ],
            "rate": 10,
            "duration_s": 15,
        },
        "output": {
            "dropped_iterations": dropped,
            "operations": {
                "items": {"p95_ms": p95, "error_rate": 0.0, "achieved_rps": 9.8},
                "health": {"p95_ms": health, "error_rate": 0.0, "achieved_rps": 10.0},
            },
        },
    }


def _run_dir(home: Path, repo: Path, experiment: dict, report: str = FENCE) -> Path:
    run_dir = home / "runs" / "abc123"
    (run_dir / "experiments").mkdir(parents=True)
    (run_dir / "experiments" / "exp-k6-0003.json").write_text(json.dumps(experiment), encoding="utf-8")
    (run_dir / "reads.jsonl").write_text(
        json.dumps({"path": "app.py", "start_line": 1, "end_line": 1, "evidence_id": "ev-read-1"}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "profile.json").write_text(json.dumps({"root": str(repo)}), encoding="utf-8")
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    return run_dir


def _after(p95: float, health: float = 7.0) -> dict:
    experiment = _experiment(p95, health=health)
    experiment["experiment_id"] = "exp-k6-0001"
    return experiment


def test_build_range_diff_from_replacement():
    snippet = "1:value = 1\n2:keep = True"
    diff = build_range_diff("app.py", snippet, 1, 1, "value = 2")
    assert "diff --git a/app.py b/app.py" in diff
    assert "-value = 1" in diff
    assert "+value = 2" in diff
    assert "keep = True" in diff


def test_unclosed_fence_at_eof_is_parsed():
    text = (
        "# Report\n\n```yaml\nloadline_fix:\n  experiment_id: exp-k6-0003\n"
        "  operation_id: items\n  metric: p95_ms\n  direction: decrease\n"
        "  control_operation_id: health\n  path: app.py\n  start_line: 1\n"
        "  end_line: 1\n  rationale: one sentence\n"
    )
    fix = parse_fix_fence(text)
    assert fix is not None
    assert fix["experiment_id"] == "exp-k6-0003"
    assert fix["path"] == "app.py"


def test_crlf_only_worktree_is_restored_and_not_blocked(tmp_path: Path):
    repo = tmp_path / "app"
    _repo(repo)
    (repo / "app.py").write_text("value = 1\r\n", encoding="utf-8")
    assert b"\r\n" in (repo / "app.py").read_bytes()
    assert _worktree_blocks_patch(repo) is False
    assert (repo / "app.py").read_bytes() == b"value = 1\n"


def test_missing_fence_does_not_call_the_patch_model(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path))
    repo = tmp_path / "app"
    _repo(repo)
    run_dir = _run_dir(tmp_path, repo, _experiment(400), report="# Report\n\nNo fence.\n")
    calls: list[int] = []

    def patch(*_args):
        calls.append(1)
        return DIFF

    code = verify_run(run_dir, open_pr=True, patch_runner=patch, push_runner=lambda *_a: calls.append(2) or (False, None))
    doc = json.loads((run_dir / "verification.json").read_text(encoding="utf-8"))
    assert code == 0
    assert calls == []
    assert doc["verdict"] == "no_verifiable_fix"
    assert doc["pr_opened"] is False


def test_replay_uses_the_stored_rate_and_can_improve(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path))
    repo = tmp_path / "app"
    _repo(repo)
    run_dir = _run_dir(tmp_path, repo, _experiment(400))
    seen: dict = {}
    pushes: list[str] = []

    def replay(_repo: Path, tool_input: dict):
        seen["input"] = tool_input
        replay_dir = tmp_path / "replay"
        replay_dir.mkdir()
        return {"status": "ok", "experiment": _after(18), "run_id": "replay1", "run_dir": str(replay_dir)}

    code = verify_run(
        run_dir,
        open_pr=True,
        patch_runner=lambda *_a: DIFF,
        replay_runner=replay,
        push_runner=lambda *_a: pushes.append("gh") or (False, None),
    )
    doc = json.loads((run_dir / "verification.json").read_text(encoding="utf-8"))
    assert code == 0
    assert seen["input"]["rate"] == 10
    assert seen["input"]["duration_s"] == 15
    assert seen["input"]["endpoints"][0]["path"] == "/api/items"
    assert doc["verdict"] == "improved"
    assert doc["before"]["p95_ms"] == 400
    assert doc["after"]["p95_ms"] == 18
    assert doc["after"]["experiment_id"] == "exp-k6-verify-0003"
    assert doc["pr_opened"] is False
    assert pushes == ["gh"]
    body = (run_dir / "pr-body.md").read_text(encoding="utf-8")
    assert "400" in body and "18" in body
    assert (repo / "app.py").read_text(encoding="utf-8") == "value = 2\n"


def test_flat_patch_does_not_push(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path))
    repo = tmp_path / "app"
    _repo(repo)
    run_dir = _run_dir(tmp_path, repo, _experiment(400))
    pushes: list[str] = []

    def replay(_repo: Path, _tool_input: dict):
        replay_dir = tmp_path / "replay"
        replay_dir.mkdir()
        return {"status": "ok", "experiment": _after(390, health=6), "run_id": "replay1", "run_dir": str(replay_dir)}

    verify_run(
        run_dir,
        open_pr=True,
        patch_runner=lambda *_a: DIFF,
        replay_runner=replay,
        push_runner=lambda *_a: pushes.append("gh") or (True, "https://example.invalid/pull/1"),
    )
    doc = json.loads((run_dir / "verification.json").read_text(encoding="utf-8"))
    assert doc["verdict"] == "hypothesis_failed"
    assert doc["pr_opened"] is False
    assert pushes == []
    assert "improved" not in render_comparison(doc)
    assert render_pr_body(doc) is None
    assert not (run_dir / "pr-body.md").exists()


def test_healthy_baseline_does_not_raise_the_rate_or_call_the_model(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path))
    repo = tmp_path / "app"
    _repo(repo)
    run_dir = _run_dir(tmp_path, repo, _experiment(12))
    calls: list[int] = []
    code = verify_run(run_dir, patch_runner=lambda *_a: calls.append(1) or DIFF)
    doc = json.loads((run_dir / "verification.json").read_text(encoding="utf-8"))
    assert code == 0
    assert calls == []
    assert doc["verdict"] == "hypothesis_failed"
    assert "not raised" in doc["reason"]
    assert doc["rate"] == 10


def test_loadline_repo_is_refused(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path))
    loadline_repo = Path(__file__).resolve().parents[2]
    run_dir = _run_dir(tmp_path, loadline_repo, _experiment(400))
    calls: list[int] = []
    code = verify_run(run_dir, patch_runner=lambda *_a: calls.append(1) or DIFF)
    assert code == 2
    assert calls == []


def test_oversized_diff_is_not_applied(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path))
    repo = tmp_path / "app"
    _repo(repo)
    run_dir = _run_dir(tmp_path, repo, _experiment(400))
    huge = "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n" + "".join(
        f"+line {i}\n" for i in range(81)
    )
    verify_run(run_dir, patch_runner=lambda *_a: huge, replay_runner=lambda *_a: {"status": "ok"})
    doc = json.loads((run_dir / "verification.json").read_text(encoding="utf-8"))
    assert doc["verdict"] == "no_verifiable_fix"
    assert "80" in doc["reason"]
    assert (repo / "app.py").read_text(encoding="utf-8") == "value = 1\n"
