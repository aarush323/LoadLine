import json
from pathlib import Path

from loadline.cli import main
from loadline.ui.run_index import match_runs, scan_runs


def _make_run(root: Path, run_id: str, repo: str, offered: float, dropped: int = 0) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "profile.json").write_text(json.dumps({"root": repo}))
    (run_dir / "ledger.jsonl").write_text(
        json.dumps(
            {
                "seq": 1,
                "kind": "k6_run",
                "evidence_ids": ["exp-k6-0001"],
                "experiment_id": "exp-k6-0001",
                "wave": "agent-k6-1",
                "result": {
                    "offered_rps": offered,
                    "dropped_iterations": dropped,
                    "operations": {"widget": {"p95_ms": 99, "error_count": 0}},
                },
            }
        )
        + "\n"
    )
    (run_dir / "report.json").write_text(json.dumps({"run_id": run_id, "run_state": "completed"}))
    return run_dir


def test_scan_runs_newest_first_and_fields(tmp_path: Path):
    runs = tmp_path / "runs"
    _make_run(runs, "aaa111", "/repos/unreliable-blind", 3.0)
    _make_run(runs, "bbb222", "/repos/checkout-api", 20.0, dropped=5)
    summaries = scan_runs(runs)
    assert [s.run_id for s in summaries] == ["bbb222", "aaa111"]
    assert summaries[0].repo_name == "checkout-api"
    assert summaries[0].peak_rps == 20.0
    assert summaries[0].dropped == 5
    assert summaries[0].waves == 1


def test_scan_runs_repo_filter_and_prefix_match(tmp_path: Path):
    runs = tmp_path / "runs"
    _make_run(runs, "aaa111", "/repos/unreliable-blind", 3.0)
    _make_run(runs, "aab333", "/repos/checkout-api", 5.0)
    filtered = scan_runs(runs, repo_filter="checkout")
    assert [s.run_id for s in filtered] == ["aab333"]
    assert len(match_runs(scan_runs(runs), "aaa")) == 1
    assert len(match_runs(scan_runs(runs), "aa")) == 2
    assert match_runs(scan_runs(runs), "zzz") == []


def test_dashboard_json_and_run_prefix(tmp_path: Path, capsys, monkeypatch):
    runs = tmp_path / "runs"
    _make_run(runs, "aaa111", "/repos/unreliable-blind", 3.0)
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path))
    assert main(["dashboard", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [r["run_id"] for r in payload] == ["aaa111"]
    assert main(["dashboard", "--run", "aaa"]) == 0
    out = capsys.readouterr().out
    assert "RESULT · run aaa111" in out
    assert "VALIDITY · LIMITATIONS" in out


def test_dashboard_no_match_and_picker_non_tty(tmp_path: Path, capsys, monkeypatch):
    runs = tmp_path / "runs"
    _make_run(runs, "aaa111", "/repos/unreliable-blind", 3.0)
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path))
    assert main(["dashboard", "--run", "zzz"]) == 2
    assert "no run matches" in capsys.readouterr().err
    assert main(["dashboard"]) == 2
    captured = capsys.readouterr()
    assert "aaa111" in captured.out
    assert "--run" in captured.err
