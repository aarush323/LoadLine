import json
from pathlib import Path

from loadline.core.ledger import Ledger


def test_ledger_append_has_required_fields(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ledger = Ledger.open(run_dir, "abc123")
    ev = ledger.append("baseline_finished", evidence_ids=["ev-1"], verdict="pass")
    assert ev["run_id"] == "abc123"
    assert ev["seq"] == 1
    assert "ts" in ev
    line = (run_dir / "ledger.jsonl").read_text().strip()
    parsed = json.loads(line)
    assert parsed["kind"] == "baseline_finished"
