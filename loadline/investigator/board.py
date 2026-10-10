"""Investigation board from ledger and wave artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from loadline.core.experiment_policy import EXPERIMENT_KINDS
from loadline.core.ledger import Ledger
from loadline.core.predictions import KNOWN_READOUTS


def build_board(run_dir: Path, run_id: str, *, goal: str = "capacity") -> str:
    ledger = Ledger.open(run_dir, run_id)
    bracket_path = run_dir / "bracket.json"
    bracket: dict = {}
    if bracket_path.is_file():
        bracket = json.loads(bracket_path.read_text())
    baseline = ledger.events_of("baseline_finished")
    wave_summaries: list[str] = []
    waves_root = run_dir / "waves"
    if waves_root.is_dir():
        for child in sorted(waves_root.iterdir()):
            tele_path = child / "telemetry.json"
            if not tele_path.is_file():
                continue
            tele = json.loads(tele_path.read_text())
            wave_summaries.append(f"{child.name}: verdict={tele.get('verdict', 'unknown')}")
    lines = [
        f"goal: {goal}",
        f"legal_experiment_kinds: {', '.join(EXPERIMENT_KINDS)}",
        f"allowed_readouts: {', '.join(sorted(KNOWN_READOUTS))}",
        f"bracket: {bracket if bracket else 'not measured (no bracket.json)'}",
        f"baseline: {baseline[-1] if baseline else 'not measured (no baseline)'}",
        f"waves: {wave_summaries or ['none']}",
        "note: generator_limited means the load generator could not deliver the offered rate; "
        "that is not application capacity. capacity_rps in bracket is the highest valid pass.",
    ]
    return "\n".join(lines)
