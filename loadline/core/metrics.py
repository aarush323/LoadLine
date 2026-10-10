"""MetricSeries model (tech_doc.md §10.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

NOT_MEASURED = "not measured (field absent)"

MetricKind = Literal["gauge", "counter", "rate"]


@dataclass(frozen=True)
class MetricPoint:
    t: float
    value: float | str


@dataclass
class MetricSeries:
    name: str
    unit: str
    entity: str
    kind: MetricKind
    points: list[MetricPoint] = field(default_factory=list)
    coverage: float = 0.0
    evidence_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "unit": self.unit,
            "entity": self.entity,
            "kind": self.kind,
            "points": [{"t": p.t, "value": p.value} for p in self.points],
            "coverage": self.coverage,
            "evidence_id": self.evidence_id,
        }
