"""Experiment admission (tech_doc.md §11.5, implementation.md S6)."""

from __future__ import annotations

from dataclasses import dataclass, field

EXPERIMENT_KINDS = (
    "rate_step",
    "rate_ladder",
    "refine",
    "confirm",
    "isolate",
    "mix_ablation",
    "param_scale",
    "resource_perturb",
    "dependency_perturb",
    "warm_cold",
)

LOAD_KINDS = frozenset(EXPERIMENT_KINDS)


@dataclass
class ExperimentContext:
    operations_count: int = 1
    rate_rps: float = 2.0
    rate_cap: float = 100.0
    budget_remaining: float = 1.0
    refine_requested: bool = False
    confirm_requested: bool = False
    refinements_done: int = 0
    smoke_passed: bool = True
    duplicate_signature: bool = False
    allow_writes: bool = False


@dataclass
class AdmitResult:
    admitted: bool
    reason: str | None = None
    alternatives: list[str] = field(default_factory=list)


def legal_alternatives(_ctx: ExperimentContext) -> list[str]:
    return list(EXPERIMENT_KINDS)


def admit(kind: str, ctx: ExperimentContext) -> AdmitResult:
    if kind not in LOAD_KINDS:
        return AdmitResult(False, f"unknown experiment kind: {kind}", list(LOAD_KINDS))

    if not ctx.smoke_passed:
        return AdmitResult(False, "operations failed smoke", legal_alternatives(ctx))

    return AdmitResult(True)
