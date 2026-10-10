"""Prediction scoring with ledger events (tech_doc.md §11.4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loadline.core.ledger import Ledger
from loadline.core.prediction_evaluator import Comparator, Outcome, score_prediction

KNOWN_READOUTS = frozenset(
    {
        "p95_ms",
        "p50_ms",
        "throughput_rps",
        "err_rate",
        "cpu_util",
        "throttle_ratio",
        "implied_concurrency",
        "dep_latency",
        "dep_calls_per_req",
    }
)


@dataclass(frozen=True)
class PredictionSpec:
    prediction_id: str
    readout: str
    comparator: Comparator
    baseline: float
    observed: float
    unit: str
    samples: int
    valid_verdict: bool
    magnitude: float | None = None


def score_prediction_ledger(ledger: Ledger, spec: PredictionSpec) -> dict[str, Any]:
    if spec.readout not in KNOWN_READOUTS:
        return ledger.append(
            "prediction_rejected",
            evidence_ids=[f"ev-pred-{spec.prediction_id}"],
            prediction_id=spec.prediction_id,
            reason=f"unknown readout: {spec.readout}",
            allowed_readouts=sorted(KNOWN_READOUTS),
        )

    outcome: Outcome = score_prediction(
        spec.comparator,
        spec.baseline,
        spec.observed,
        spec.unit,
        magnitude=spec.magnitude,
        samples=spec.samples,
        valid_verdict=spec.valid_verdict,
    )
    return ledger.append(
        "prediction_scored",
        evidence_ids=[f"ev-pred-{spec.prediction_id}"],
        prediction_id=spec.prediction_id,
        readout=spec.readout,
        comparator=spec.comparator,
        baseline=spec.baseline,
        observed=spec.observed,
        unit=spec.unit,
        outcome=outcome,
        samples=spec.samples,
    )
