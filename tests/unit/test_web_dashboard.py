import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from loadline.cli import main
from loadline.dashboard.render import render_run_page
from loadline.dashboard.server import _Handler


def _make_run(root: Path, run_id: str) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "profile.json").write_text(
        json.dumps({"root": "/nonexistent/repo-xyz", "languages": ["python"], "entrypoints": []})
    )
    events = [
        {"seq": 1, "ts": "2026-10-10T14:32:00+00:00", "kind": "hypothesis",
         "evidence_ids": [], "claim": "widget waits on the pool"},
        {"seq": 2, "ts": "2026-10-10T14:32:20+00:00", "kind": "k6_run",
         "evidence_ids": ["exp-k6-0001"], "experiment_id": "exp-k6-0001", "wave": "agent-k6-1",
         "plan": {"mix": [{"op": {"id": "widget", "selector": {"method": "GET", "path": "/widgets/1"}}}]},
         "result": {"offered_rps": 3.0, "dropped_iterations": 0, "vus_max": 8, "vu_ceiling": 50,
                    "operations": {"widget": {"p95_ms": 801, "error_count": 0, "error_rate": 0.0,
                                              "offered_rps": 3.0, "achieved_rps": 2.9}}}},
        {"seq": 3, "ts": "2026-10-10T14:32:52+00:00", "kind": "k6_run",
         "evidence_ids": ["exp-k6-0002"], "experiment_id": "exp-k6-0002", "wave": "agent-k6-2",
         "plan": {"mix": [{"op": {"id": "widget", "selector": {"method": "GET", "path": "/widgets/1"}}}]},
         "result": {"offered_rps": 20.0, "dropped_iterations": 167, "vus_max": 38, "vu_ceiling": 50,
                    "operations": {"widget": {"p95_ms": 5774, "error_count": 12, "error_rate": 0.03,
                                              "offered_rps": 20.0, "achieved_rps": 14.2}}}},
        {"seq": 4, "ts": "2026-10-10T14:33:01+00:00", "kind": "finding",
         "evidence_ids": ["exp-k6-0002"], "symptom": "widget tail latency climbs with load"},
    ]
    (run_dir / "ledger.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    (run_dir / "report.json").write_text(json.dumps({"run_id": run_id, "run_state": "completed"}))
    (run_dir / "report.md").write_text("# Loadline report\n")
    return run_dir


def test_run_page_uses_measured_data_only(tmp_path: Path):
    run_dir = _make_run(tmp_path / "runs", "aaa111")
    page = render_run_page(run_dir, "aaa111")
    assert page
    assert "__" not in [s for s in __import__("re").findall(r"__[A-Z_]+__", page)]
    for leaked in ("LL-7F2C", "EV-021", "812 ms", "146 req/s", "checkout-api",
                   "Illustrative", "FIRST SLO BREACH", "The system bends at"):
        assert leaked not in page
    for real in ("aaa111", "5774", "/widgets/1", "exp-k6-0002", "agent-k6-2",
                 "repo-xyz", "widget waits on the pool", "widget tail latency climbs"):
        assert real in page
    assert "SLO" in page and "not recorded" in page
    assert "CODE MAP UNAVAILABLE" in page
    assert "window.LOADLINE" in page


def test_run_page_worst_op_beyond_graph_cap(tmp_path: Path):
    """5 ops, worst p95 last: render must not raise and must show it."""
    run_dir = tmp_path / "runs" / "bigops"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "profile.json").write_text(json.dumps({"root": "/nonexistent/repo-xyz"}))
    ops = {f"op{i}": {"p95_ms": 10 + i, "error_count": 0, "error_rate": 0.0,
                       "offered_rps": 5.0, "achieved_rps": 5.0} for i in range(4)}
    ops["laggard"] = {"p95_ms": 9000, "error_count": 1, "error_rate": 0.01,
                      "offered_rps": 5.0, "achieved_rps": 4.0}
    (run_dir / "ledger.jsonl").write_text(json.dumps(
        {"seq": 1, "kind": "k6_run", "evidence_ids": ["exp-k6-0001"],
         "experiment_id": "exp-k6-0001", "wave": "agent-k6-1",
         "plan": {"mix": []},
         "result": {"offered_rps": 5.0, "dropped_iterations": 0, "operations": ops}}
    ) + "\n")
    (run_dir / "report.json").write_text(json.dumps({"run_id": "bigops", "run_state": "completed"}))
    page = render_run_page(run_dir, "bigops")
    assert page
    assert "laggard" in page
    assert "9000" in page


def test_run_page_empty_dir(tmp_path: Path):
    assert render_run_page(tmp_path / "nope", "nope") == ""
    empty = tmp_path / "empty"
    empty.mkdir()
    assert render_run_page(empty, "empty") == ""


def _serve_tmp(home: Path):
    _Handler.home = home
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _get(port: int, path: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, ""


def test_server_routes(tmp_path: Path):
    import urllib.error

    _make_run(tmp_path / "runs", "aaa111")
    server = _serve_tmp(tmp_path)
    try:
        port = server.server_address[1]
        code, body = _get(port, "/")
        assert code == 200 and "aaa111" in body
        code, body = _get(port, "/runs/aaa111")
        assert code == 200 and "5774" in body
        assert _get(port, "/runs/zzz")[0] == 404
        code, body = _get(port, "/api/runs")
        assert code == 200 and "aaa111" in json.loads(body)[0]["run_id"]
        code, body = _get(port, "/artifacts/aaa111/report.md")
        assert code == 200 and "Loadline report" in body
        assert _get(port, "/nope")[0] == 404
    finally:
        server.shutdown()


def test_dashboard_export_flag(tmp_path: Path, capsys, monkeypatch):
    _make_run(tmp_path / "runs", "aaa111")
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path))
    out = tmp_path / "dash.html"
    assert main(["dashboard", "--run", "aaa", "--export", str(out)]) == 0
    assert "exp-k6-0002" in out.read_text()
    assert main(["dashboard", "--export", str(out)]) == 2


def _write_verification(run_dir: Path, **fields: object) -> None:
    doc = {
        "schema_version": "loadline-verification/1",
        "source_run_id": run_dir.name,
        "experiment_id": "exp-k6-0002",
        "operation_id": "widget",
        "control_operation_id": "health",
        "metric": "p95_ms",
        "direction": "decrease",
        "rate": 20.0,
        "duration_s": 30,
        "endpoint": {"method": "GET", "path": "/widgets/1"},
        "before": {"experiment_id": "exp-k6-0002", "p95_ms": 5774, "error_rate": 0.03, "achieved_rps": 14.2},
        "after": {"experiment_id": "exp-k6-verify-0002", "p95_ms": 900, "error_rate": 0.0, "achieved_rps": 19.1},
        "control_before": {"p95_ms": 5.0, "error_rate": 0.0, "achieved_rps": 4.0},
        "control_after": {"p95_ms": 4.5, "error_rate": 0.0, "achieved_rps": 4.0},
        "verdict": "hypothesis_failed",
        "pr_opened": False,
        "pr_url": "",
        "branch": "loadline/verify-aaa111",
        "patch_paths": ["app/main.py"],
    }
    doc.update(fields)
    (run_dir / "verification.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")


def test_run_page_hypothesis_failed_shows_both_p95_and_no_pr(tmp_path: Path):
    run_dir = _make_run(tmp_path / "runs", "fail111")
    _write_verification(run_dir, verdict="hypothesis_failed", pr_opened=False, pr_url="")
    page = render_run_page(run_dir, "fail111")
    assert page
    assert "5774" in page and "900" in page
    assert "hypothesis failed" in page.lower()
    assert 'id="verification"' in page
    assert 'class="section verify-panel"' not in page
    assert page.count('id="verification"') == 1


def test_run_page_without_verification_does_not_invent_after(tmp_path: Path):
    run_dir = _make_run(tmp_path / "runs", "aaa111")
    page = render_run_page(run_dir, "aaa111")
    assert page
    assert "Not verified" in page or "NOT VERIFIED" in page
    assert 'id="verification"' not in page
    assert "No pull request." not in page
    assert "Cited p95" not in page


def test_run_page_hypothesis_is_full_width_box(tmp_path: Path):
    run_dir = _make_run(tmp_path / "runs", "hypobox")
    (run_dir / "report.md").write_text("## Verdict\n\nThe widget waits on the pool under load.\n")
    page = render_run_page(run_dir, "hypobox")
    assert 'class="hypothesis-box"' in page
    assert 'class="hypothesis-label"' in page
    assert "Investigator hypothesis" in page
    assert "The widget waits on the pool under load." in page


def test_report_code_section_keeps_first_and_last_fence(tmp_path: Path):
    run_dir = _make_run(tmp_path / "runs", "codehalf")
    source = (
        "## Verdict\n\nEndpoint degrades.\n\n"
        "## Code\n\n"
        "Buggy handler holds the connection:\n\n"
        "```python\n"
        "async def buggy():\n    await hold()\n"
        "```\n\n"
        "Pool is tiny:\n\n"
        "```python\n"
        "pool_size = 5\n"
        "```\n\n"
        "Checkout is eager:\n\n"
        "```python\n"
        "await session.connection()\n"
        "```\n\n"
        "Fixed path releases first:\n\n"
        "```python\n"
        "async def fixed():\n    await release()\n"
        "```\n\n"
        "## Next step\n\nUse the fixed path.\n"
    )
    (run_dir / "report.md").write_text(source)
    page = render_run_page(run_dir, "codehalf")
    start = page.find('class="panel report-md"')
    end = page.find("</section>", start)
    report_html = page[start:end]
    assert report_html.count("<pre><code>") == 2
    assert "async def buggy():" in report_html
    assert "async def fixed():" in report_html
    assert "pool_size = 5" not in report_html
    assert "await session.connection()" not in report_html
    assert "2 of 4 excerpts shown. Full Code section is in report.md." in report_html
    assert "Use the fixed path." in report_html
    assert "pool_size = 5" in (run_dir / "report.md").read_text()


def test_index_hides_runs_that_did_not_boot(tmp_path: Path):
    runs = tmp_path / "runs"
    _make_run(runs, "booted01")
    failed = runs / "bootfail"
    failed.mkdir(parents=True)
    (failed / "profile.json").write_text(json.dumps({"root": "/nonexistent/repo-xyz"}))
    (failed / "attempts.json").write_text(json.dumps({
        "attempts": [],
        "blocker": {"code": "boot_failed", "summary": "compose up failed"},
    }))
    missing = runs / "noentry"
    missing.mkdir(parents=True)
    (missing / "profile.json").write_text(json.dumps({"root": "/nonexistent/other"}))
    (missing / "attempts.json").write_text(json.dumps({
        "attempts": [],
        "blocker": {"code": "no_entrypoint", "summary": "No Compose file or Dockerfile was found."},
    }))
    server = _serve_tmp(tmp_path)
    try:
        port = server.server_address[1]
        code, body = _get(port, "/")
        assert code == 200
        assert "booted01" in body
        assert "bootfail" not in body
        assert "noentry" not in body
        payload = json.loads(_get(port, "/api/runs")[1])
        ids = [row["run_id"] for row in payload]
        assert ids == ["booted01"]
        code, direct = _get(port, "/runs/bootfail")
        assert code == 200
        assert "compose up failed" in direct
    finally:
        server.shutdown()


def test_k6_only_ledger_has_no_hypothesis_placeholder(tmp_path: Path):
    run_dir = tmp_path / "runs" / "k6only"
    run_dir.mkdir(parents=True)
    (run_dir / "profile.json").write_text(json.dumps({"root": "/nonexistent/repo-xyz"}))
    (run_dir / "ledger.jsonl").write_text(json.dumps(
        {"seq": 1, "kind": "k6_run", "evidence_ids": ["exp-k6-0001"],
         "experiment_id": "exp-k6-0001", "wave": "agent-k6-1",
         "plan": {"mix": [{"op": {"id": "widget", "selector": {"method": "GET", "path": "/x"}}}]},
         "result": {"offered_rps": 5.0, "dropped_iterations": 0,
                    "operations": {"widget": {"p95_ms": 40, "error_count": 0, "error_rate": 0.0,
                                             "offered_rps": 5.0, "achieved_rps": 5.0}}}}
    ) + "\n")
    (run_dir / "report.json").write_text(json.dumps({"run_id": "k6only", "run_state": "completed"}))
    (run_dir / "report.md").write_text("## Verdict\n\nThe endpoint waits on a pool.\n")
    page = render_run_page(run_dir, "k6only")
    assert page
    assert "H-01" not in page
    assert "No finding was recorded" not in page
    assert "The endpoint waits on a pool." in page


def test_report_markdown_table_renders(tmp_path: Path):
    run_dir = _make_run(tmp_path / "runs", "mdtbl")
    (run_dir / "report.md").write_text(
        "## Verification\n\n"
        "| | Before | After |\n"
        "|---|---|---|\n"
        "| p95 | 5710 ms | 1423 ms |\n"
    )
    page = render_run_page(run_dir, "mdtbl")
    assert page
    assert "<table>" in page
    assert "5710 ms" in page and "1423 ms" in page
    assert 'id="report"' in page


def test_index_shows_verdict_on_verified_row_only(tmp_path: Path):
    import urllib.error

    verified = _make_run(tmp_path / "runs", "ver111")
    _write_verification(verified, verdict="improved", pr_opened=True,
                        pr_url="https://example.invalid/pull/1")
    _make_run(tmp_path / "runs", "plain22")
    server = _serve_tmp(tmp_path)
    try:
        port = server.server_address[1]
        code, body = _get(port, "/")
        assert code == 200
        assert "ver111" in body and "plain22" in body
        assert "improved" in body
        assert body.count("not verified") >= 1
        code, body = _get(port, "/?repo=repo-xyz")
        assert code == 200 and "ver111" in body
        code, body = _get(port, "/?repo=no-such-repo")
        assert code == 200 and "No runs match" in body
        code, body = _get(port, "/api/runs")
        assert code == 200
        payload = json.loads(body)
        by_id = {row["run_id"]: row for row in payload}
        assert by_id["ver111"]["verification_verdict"] == "improved"
        assert by_id["plain22"]["verification_verdict"] is None
    finally:
        server.shutdown()


def test_blocked_run_renders_without_chart_or_docker_sock(tmp_path: Path):
    run_dir = tmp_path / "runs" / "blocked1"
    run_dir.mkdir(parents=True)
    (run_dir / "profile.json").write_text(json.dumps({"root": "/nonexistent/repo-xyz"}))
    (run_dir / "attempts.json").write_text(json.dumps({
        "attempts": [{"n": 1, "signature": "compose", "result": "blocked"}],
        "blocker": {
            "code": "policy_refused",
            "summary": "host docker socket is not allowed",
            "security": True,
            "remediation": ["bind-mount docker.sock into the sandbox"],
        },
    }))
    page = render_run_page(run_dir, "blocked1")
    assert page
    assert "did not reach measurement" in page.lower()
    assert "host docker socket is not allowed" in page
    assert "security refusal" in page.lower()
    assert "docker.sock" not in page
    assert '<svg class="chart-svg"' not in page
    assert 'id="pressure"' in page and "section hidden" in page
