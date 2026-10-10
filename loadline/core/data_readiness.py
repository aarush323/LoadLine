"""Post-boot data readiness (tech_doc.md §7.7)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReadOperation:
    id: str
    needs_harvested_ids: bool
    read_safe: bool = True


@dataclass(frozen=True)
class DatasetMeasurement:
    """size is row/count when measured; None means not measured."""

    size: int | None
    source: str


@dataclass(frozen=True)
class DataReadinessResult:
    measured: bool
    blocker_code: str | None = None
    blocker_summary: str | None = None
    excluded_operations: tuple[str, ...] = ()
    working_operations: tuple[str, ...] = ()


def evaluate_data_readiness(
    operations: list[ReadOperation],
    measurement: DatasetMeasurement,
) -> DataReadinessResult:
    reads = [op for op in operations if op.read_safe]
    if measurement.size is None:
        return DataReadinessResult(measured=False, working_operations=tuple(op.id for op in reads))

    if measurement.size > 0:
        return DataReadinessResult(measured=True, working_operations=tuple(op.id for op in reads))

    without_ids = [op for op in reads if not op.needs_harvested_ids]
    needs_ids = [op for op in reads if op.needs_harvested_ids]
    if without_ids:
        return DataReadinessResult(
            measured=True,
            excluded_operations=tuple(op.id for op in needs_ids),
            working_operations=tuple(op.id for op in without_ids),
        )
    if not reads:
        return DataReadinessResult(measured=True, working_operations=())
    return DataReadinessResult(
        measured=True,
        blocker_code="data_missing",
        blocker_summary="Dataset size is zero and every read operation requires harvested identifiers.",
        excluded_operations=tuple(op.id for op in needs_ids),
        working_operations=(),
    )
