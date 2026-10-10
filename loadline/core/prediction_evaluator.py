"""Score predictions on valid steps (tech_doc.md §11.4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from loadline.constants import MIN_SAMPLES, NOISE_ABS_MS, NOISE_REL

Comparator = Literal["gt", "lt", "ge", "le", "within", "changes_by", "unchanged"]
Outcome = Literal["confirmed", "refuted", "inconclusive"]


@dataclass(frozen=True)
class StepReadout:
    """One measurement used for prediction scoring."""

    readout: str
    value: float
    unit: str
    samples: int
    valid_verdict: bool  # pass or fail


def within_noise(baseline: float, observed: float, unit: str) -> bool:
    if baseline == 0 and observed == 0:
        return True
    denom = max(abs(baseline), abs(observed), 1e-9)
    rel = abs(observed - baseline) / denom
    if rel < NOISE_REL:
        return True
    if unit in ("ms", "milliseconds", "s", "seconds"):
        ms = observed if unit.startswith("m") else observed * 1000
        ms0 = baseline if unit.startswith("m") else baseline * 1000
        return abs(ms - ms0) < NOISE_ABS_MS
    return False


def score_prediction(
    comparator: Comparator,
    baseline: float,
    observed: float,
    unit: str,
    *,
    magnitude: float | None = None,
    samples: int,
    valid_verdict: bool,
) -> Outcome:
    if not valid_verdict or samples < MIN_SAMPLES:
        return "inconclusive"
    delta = observed - baseline
    noise = within_noise(baseline, observed, unit)
    if comparator == "unchanged":
        return "confirmed" if noise else "inconclusive"
    if comparator == "changes_by":
        return "confirmed" if not noise else "inconclusive"
    if comparator == "within":
        return "confirmed" if noise else "refuted"
    if magnitude is not None:
        target = magnitude
    else:
        target = 0.0
    if comparator == "gt":
        return "confirmed" if delta > target and not noise else ("inconclusive" if noise else "refuted")
    if comparator == "ge":
        return "confirmed" if delta >= target and not noise else ("inconclusive" if noise else "refuted")
    if comparator == "lt":
        return "confirmed" if delta < -target and not noise else ("inconclusive" if noise else "refuted")
    if comparator == "le":
        return "confirmed" if delta <= -target and not noise else ("inconclusive" if noise else "refuted")
    return "inconclusive"
