import json
from pathlib import Path

from loadline.core.ledger import Ledger
from loadline.core.report_render import build_report_model, render_markdown, write_report


def test_report_includes_investigate_steps_not_baseline_only(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "bracket.json").write_text(
        json.dumps({"status": "generator_limited", "lo": 2500.0, "capacity_rps": 2500.0})
    )
    waves = run_dir / "waves" / "baseline"
    waves.mkdir(parents=True)
    (waves / "telemetry.json").write_text(json.dumps({"verdict": "pass", "attribution": [], "series": []}))
    ledger = Ledger.open(run_dir, "r1")
    ledger.append(
        "baseline_finished",
        evidence_ids=["ev-k6-throughput"],
        throughput_rps=2.0,
        successful_samples=200,
        verdict="pass",
    )
    ledger.append(
        "experiment_finished",
        experiment_kind="rate_step",
        evidence_ids=["ev-k6-throughput"],
        verdict="pass",
        rate=2500,
        throughput_rps=2500.0,
        plan_shape={"rate": 2500, "duration": 30},
    )
    model = build_report_model(run_dir, "r1")
    md = render_markdown(model)
    assert "rate_step" in md
    assert "2500" in md
    assert "investigator not run" not in md.lower()
    assert model.capacity.get("capacity_rps") == 2500.0
    assert model.run_state == "generator_limited"
