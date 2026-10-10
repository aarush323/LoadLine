"""Report JSON model (tech_doc.md §14)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Tag = Literal["measured", "projected", "hypothesis"]


@dataclass
class ReportNumber:
    value: str
    unit: str
    evidence_id: str
    tag: Tag = "measured"


@dataclass
class ReportModel:
    schema_version: str = "loadline-report/1"
    run_id: str = ""
    run_state: str = "completed"
    incomplete_reason: str | None = None
    measured: list[ReportNumber] = field(default_factory=list)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    capacity: dict[str, Any] = field(default_factory=dict)
    experiment_log: list[dict[str, Any]] = field(default_factory=list)
    attribution_primary: str | None = None
    prose_blocks: list[str] = field(default_factory=list)

    def all_digit_tokens(self) -> set[str]:
        import json
        import re

        blob = json.dumps(self.to_dict(), sort_keys=True)
        return set(re.findall(r"\d+\.?\d*", blob))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "run_state": self.run_state,
            "incomplete_reason": self.incomplete_reason,
            "measured": [
                {"value": m.value, "unit": m.unit, "evidence_id": m.evidence_id, "tag": m.tag} for m in self.measured
            ],
            "hypotheses": self.hypotheses,
            "findings": self.findings,
            "limitations": self.limitations,
            "capacity": self.capacity,
            "experiment_log": self.experiment_log,
            "attribution_primary": self.attribution_primary,
            "prose_blocks": self.prose_blocks,
        }


def primary_attribution_blocks_app_bottleneck(primary: str | None, prose: str) -> bool:
    if primary not in ("host", "generator"):
        return False
    lower = prose.lower()
    if "no application bottleneck" in lower or "not established" in lower:
        return False
    banned = ("application bottleneck", "app bottleneck", "bottleneck is the application")
    return any(phrase in lower for phrase in banned)
