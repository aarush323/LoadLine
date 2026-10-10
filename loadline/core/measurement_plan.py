"""Map experiment kind + params to k6 WorkloadPlan (tech_doc.md §9, §11)."""

from __future__ import annotations

from typing import Any

from loadline.constants import FAST_MEASURE_S, FAST_WARMUP_S, LADDER_START, MEASURE_S, WARMUP_S


def _shape_from_params(
    params: dict[str, Any],
    *,
    default_rate: float,
    default_warmup: int,
    default_duration: int,
) -> dict[str, int | float]:
    shape = dict(params.get("shape") or {})
    rate = params.get("rate", shape.get("rate", default_rate))
    warmup = params.get("warmup", shape.get("warmup", default_warmup))
    duration = params.get("duration", shape.get("duration", default_duration))
    return {
        "rate": int(rate),
        "warmup": int(warmup),
        "duration": int(duration),
    }


def _op_id(item: dict[str, Any]) -> str:
    op = item.get("op") or {}
    return str(op.get("id") or "")


def _filter_mix(mix: list[dict[str, Any]], keep_id: str) -> list[dict[str, Any]]:
    filtered = [item for item in mix if _op_id(item) == keep_id]
    if not filtered:
        return []
    return [{"weight": 100, "op": filtered[0]["op"]}]


def _ablate_mix(mix: list[dict[str, Any]], drop_id: str) -> list[dict[str, Any]]:
    remaining = [item for item in mix if _op_id(item) != drop_id]
    if not remaining:
        return []
    weight = max(1, 100 // len(remaining))
    return [{**item, "weight": weight} for item in remaining]


def build_measurement_plan(
    kind: str,
    params: dict[str, Any],
    mix: list[dict[str, Any]],
    *,
    fast: bool = False,
    default_rate: float | None = None,
) -> dict[str, Any] | None:
    """Return a k6 plan dict or None if the kind/params cannot produce a workload."""
    warmup_default = FAST_WARMUP_S if fast else WARMUP_S
    duration_default = FAST_MEASURE_S if fast else MEASURE_S
    rate_default = float(default_rate if default_rate is not None else LADDER_START)

    effective_mix = mix
    shape = _shape_from_params(
        params,
        default_rate=rate_default,
        default_warmup=warmup_default,
        default_duration=duration_default,
    )

    if kind == "isolate":
        op_id = str(params.get("operation_id") or params.get("op_id") or "")
        effective_mix = _filter_mix(mix, op_id) if op_id else []
    elif kind == "mix_ablation":
        drop_id = str(params.get("operation_id") or params.get("drop_operation_id") or "")
        effective_mix = _ablate_mix(mix, drop_id) if drop_id else mix
    elif kind == "warm_cold":
        cold_factor = float(params.get("cold_factor", 2.0))
        shape["warmup"] = int(shape["warmup"] * cold_factor)
    elif kind in ("rate_step", "rate_ladder", "refine", "confirm"):
        if "rate" in params:
            shape["rate"] = int(params["rate"])
        if kind == "refine" and "rate" not in params and params.get("refine_rate") is not None:
            shape["rate"] = int(params["refine_rate"])
        if kind == "confirm" and "rate" not in params and params.get("lo") is not None:
            shape["rate"] = int(params["lo"])
    elif kind in ("param_scale", "resource_perturb", "dependency_perturb"):
        pass
    else:
        return None

    if not effective_mix:
        return None
    return {"mix": effective_mix, "shape": shape}
