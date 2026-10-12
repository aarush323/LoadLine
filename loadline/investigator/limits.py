"""Caps for investigator run_k6 (agent-chosen rates, not the deterministic baseline ladder)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from loadline.constants import (
    FAST_MEASURE_S,
    INVESTIGATOR_MAX_K6_WAVES,
    INVESTIGATOR_MAX_K6_WAVES_FAST,
    INVESTIGATOR_MAX_OFFERED_RPS,
    INVESTIGATOR_MAX_OFFERED_RPS_FAST,
)


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


@dataclass(frozen=True)
class InvestigatorK6Limits:
    max_waves: int
    max_offered_rps: float
    max_duration_s: int


def investigator_k6_limits(fast: bool) -> InvestigatorK6Limits:
    max_waves = _env_int("LOADLINE_INVESTIGATOR_MAX_K6_WAVES")
    max_rps = _env_float("LOADLINE_INVESTIGATOR_MAX_RATE")
    if fast:
        return InvestigatorK6Limits(
            max_waves=max_waves if max_waves is not None else INVESTIGATOR_MAX_K6_WAVES_FAST,
            max_offered_rps=max_rps if max_rps is not None else INVESTIGATOR_MAX_OFFERED_RPS_FAST,
            max_duration_s=FAST_MEASURE_S,
        )
    return InvestigatorK6Limits(
        max_waves=max_waves if max_waves is not None else INVESTIGATOR_MAX_K6_WAVES,
        max_offered_rps=max_rps if max_rps is not None else INVESTIGATOR_MAX_OFFERED_RPS,
        max_duration_s=120,
    )
