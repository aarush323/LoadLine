import json
from pathlib import Path

from loadline.core.ledger import Ledger
from loadline.investigator.deps import ReadRange
from loadline.investigator.report_compose import (
    compose_investigation_report,
    load_k6_experiments,
    render_load_evidence_markdown,
)


def _write_experiment(
    run_dir: Path,
    exp_id: str,
    *,
    rate: float,
    duration: int,
    operations: dict,
    endpoints: list[dict],
) -> None:
    exp_dir = run_dir / "experiments"
    exp_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "experiment_id": exp_id,
        "wave": f"agent-k6-{exp_id[-1]}",
        "input": {"endpoints": endpoints, "rate": rate, "duration_s": duration},
        "output": {
            "offered_rps": rate,
            "duration_s": duration,
            "dropped_iterations": 0,
            "operations": operations,
        },
    }
    (exp_dir / f"{exp_id}.json").write_text(json.dumps(record))


def test_load_evidence_degraded_and_control_observation(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    endpoints = [
        {"id": "widget", "method": "GET", "path": "/widgets/1"},
        {"id": "healthz", "method": "GET", "path": "/healthz"},
    ]
    _write_experiment(
        run_dir,
        "exp-k6-0001",
        rate=2,
        duration=10,
        endpoints=endpoints,
        operations={
            "widget": {"count": 20, "p95_ms": 80, "status_counts_reliable": True, "http_status_known": True},
            "healthz": {"count": 20, "p95_ms": 4, "status_counts_reliable": True, "http_status_known": True},
        },
    )
    _write_experiment(
        run_dir,
        "exp-k6-0002",
        rate=8,
        duration=10,
        endpoints=endpoints,
        operations={
            "widget": {"count": 80, "p95_ms": 750, "status_counts_reliable": True, "http_status_known": True},
            "healthz": {"count": 80, "p95_ms": 5, "status_counts_reliable": True, "http_status_known": True},
        },
    )
    md = render_load_evidence_markdown(load_k6_experiments(run_dir, "r1"))
    assert "exp-k6-0001" in md
    assert "exp-k6-0002" in md
    assert "750" in md or "750 ms" in md.replace(" ", "")
    assert "Observed" in md


def test_unreliable_status_shows_integrity_note(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_experiment(
        run_dir,
        "exp-k6-0001",
        rate=2,
        duration=5,
        endpoints=[{"id": "healthz", "method": "GET", "path": "/healthz"}],
        operations={
            "healthz": {
                "count": 10,
                "p95_ms": 4,
                "error_rate": 0.0,
                "status_counts": {},
                "status_counts_reliable": False,
                "http_status_known": False,
            },
        },
    )
    md = render_load_evidence_markdown(load_k6_experiments(run_dir, "r1"))
    assert "Measurement note" in md
    assert "100%" not in md
    assert "HTTP errors" not in md.lower() or "do not treat" in md.lower()


def test_compose_replaces_load_section_preserves_verdict(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    agent = """## Verdict

The widget endpoint slows down under load.

## What happened under load

Measured tables and observations are inserted below by Loadline.

## Affected APIs

GET /widgets/1
"""
    out, meta = compose_investigation_report(
        agent,
        run_dir=run_dir,
        run_id="rid",
        read_ranges=[],
    )
    assert "The widget endpoint slows down" in out
    assert "No k6 experiments were recorded" in out
    assert "## Appendix" in out
    assert meta["experiments"] == []


def test_compose_appendix_lists_experiments(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_experiment(
        run_dir,
        "exp-k6-0001",
        rate=3,
        duration=12,
        endpoints=[{"id": "api", "method": "GET", "path": "/api"}],
        operations={"api": {"count": 30, "p95_ms": 10, "status_counts_reliable": True}},
    )
    agent = "## Verdict\n\nDone.\n\n## What happened under load\n\nstub\n"
    out, _meta = compose_investigation_report(
        agent,
        run_dir=run_dir,
        run_id="rid",
        read_ranges=[ReadRange(path="app/main.py", start_line=1, end_line=40)],
    )
    assert "exp-k6-0001" in out
    assert "offered 3 req/s" in out
    assert "app/main.py" in out
    assert "No fenced code excerpt" in out


def test_compose_from_ledger_k6_run(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ledger = Ledger.open(run_dir, "rid")
    ledger.append(
        "k6_run",
        evidence_ids=["exp-k6-0001"],
        experiment_id="exp-k6-0001",
        wave="agent-k6-1",
        result={
            "offered_rps": 5,
            "duration_s": 8,
            "dropped_iterations": 0,
            "operations": {
                "slow": {"count": 40, "p95_ms": 200, "status_counts_reliable": True},
            },
        },
        plan={"shape": {"rate": 5, "duration": 8}, "mix": [{"op": {"id": "slow", "selector": {"method": "GET", "path": "/slow"}}}]},
    )
    exps = load_k6_experiments(run_dir, "rid")
    assert len(exps) == 1
    assert exps[0].offered_rps == 5
