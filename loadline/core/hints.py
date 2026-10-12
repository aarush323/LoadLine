"""Strict .loadline.yaml parser (tech_doc.md §16.3). Phase 1: delegates to config schema."""

from __future__ import annotations

from pathlib import Path

from loadline.config.schema import ALLOWED_KEYS, EXTENDED_ALLOWED_KEYS, LoadlineHints, load_hints

__all__ = [
    "ALLOWED_KEYS",
    "DEFAULT_SLO_ERR_RATE",
    "DEFAULT_SLO_P95_MS",
    "EXTENDED_ALLOWED_KEYS",
    "LoadlineHints",
    "load_hints",
    "slo_from_hints",
]

DEFAULT_SLO_P95_MS = 2000.0
DEFAULT_SLO_ERR_RATE = 0.05


def slo_from_hints(repo: Path) -> tuple[float, float]:
    hints, _ = load_hints(repo / ".loadline.yaml")
    p95 = DEFAULT_SLO_P95_MS
    err = DEFAULT_SLO_ERR_RATE
    if hints is not None and hints.slo_p95_ms is not None:
        p95 = float(hints.slo_p95_ms)
    if hints is not None and hints.slo_err_rate is not None:
        err = float(hints.slo_err_rate)
    return p95, err
