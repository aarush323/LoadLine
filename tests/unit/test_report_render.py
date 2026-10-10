import json
from pathlib import Path

import pytest

from loadline.core.ledger import Ledger
from loadline.core.report_model import ReportModel, ReportNumber
from loadline.core.report_render import (
    ReportRenderError,
    build_report_model,
    mark_investigation_incomplete,
    render_markdown,
    validate_report_digits,
    write_report,
)


def _seed_run(run_dir: Path, run_id: str) -> None:
    (run_dir / "bracket.json").write_text(
        json.dumps(
            {
                "status": "bracketed",
                "lo": 5.0,
                "hi": 10.0,
                "capacity_rps": 5.0,
            }
        )
    )
    waves = run_dir / "waves" / "baseline"
    waves.mkdir(parents=True)
    tele = {
        "verdict": "invalid(measurement_gap)",
        "attribution": [{"limit": "host", "rank": 1, "summary": "host saturated", "evidence_ids": ["ev-host-cpu"]}],
        "series": [
            {
                "name": "throughput_rps",
                "unit": "req/s",
                "entity": "generator",
                "kind": "rate",
                "coverage": 1.0,
                "evidence_id": "ev-k6-throughput",
                "points": [{"t": 0.0, "value": 5.0}],
            }
        ],
    }
    (waves / "telemetry.json").write_text(json.dumps(tele))
    ledger = Ledger.open(run_dir, run_id)
    ledger.append(
        "baseline_finished",
        evidence_ids=["ev-k6-throughput"],
        throughput_rps=5.0,
        successful_samples=20,
        verdict="invalid(measurement_gap)",
    )


def test_report_render_fails_on_stray_digit(tmp_path: Path):
    model = ReportModel(run_id="r1", measured=[ReportNumber("5", "req/s", "ev-k6-throughput")])
    model.limitations = ["no digits here"]
    md = render_markdown(model)
    with pytest.raises(ReportRenderError):
        validate_report_digits(md + "\n999 stray", model)


def test_incomplete_run_still_writes_report(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _seed_run(run_dir, "run42")
    md_path, json_path = mark_investigation_incomplete(run_dir, "run42", "budget exhausted")
    assert md_path.is_file() and json_path.is_file()
    model = build_report_model(run_dir, "run42")
    assert model.run_state == "investigation_incomplete"
    assert model.findings == []
    assert model.limitations
    assert "budget exhausted" in md_path.read_text()


def test_host_attribution_blocks_application_bottleneck_wording():
    from loadline.core.report_model import primary_attribution_blocks_app_bottleneck

    assert primary_attribution_blocks_app_bottleneck("host", "The application bottleneck is the database.")
    assert not primary_attribution_blocks_app_bottleneck(
        "host", "No application bottleneck was established from the baseline evidence."
    )


def test_write_report_recomputes_from_waves(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _seed_run(run_dir, "run7")
    md_path, json_path = write_report(run_dir, "run7")
    data = json.loads(json_path.read_text())
    assert data["run_state"] == "completed"
    assert "Limitations" in md_path.read_text() or "limitations" in md_path.read_text().lower()
