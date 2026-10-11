"""Strict .loadline.yaml parser (tech_doc.md §16.3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from loadline.constants import SCHEMA_VERSION

ALLOWED_KEYS = frozenset(
    {
        "schema_version",
        "compose_file",
        "dockerfile",
        "compose_profile",
        "app_service",
        "container_port",
        "health_path",
        "command",
        "env",
        "exclude_operations",
        "slo.p95_ms",
        "slo.err_rate",
    }
)


class LoadlineHints(BaseModel):
    schema_version: str = Field(default="1")
    compose_file: str | None = None
    dockerfile: str | None = None
    compose_profile: str | None = None
    app_service: str | None = None
    container_port: int | None = None
    health_path: str | None = None
    command: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    exclude_operations: list[str] = Field(default_factory=list)
    slo_p95_ms: int | None = Field(default=None, alias="slo.p95_ms")
    slo_err_rate: float | None = Field(default=None, alias="slo.err_rate")

    model_config = {"populate_by_name": True}

    @field_validator("schema_version")
    @classmethod
    def _schema(cls, v: str) -> str:
        if v != "1":
            raise ValueError(f"schema_version must be 1 for {SCHEMA_VERSION}")
        return v

    @field_validator("health_path")
    @classmethod
    def _health(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith("/"):
            raise ValueError("health_path must start with /")
        return v


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


def load_hints(path: Path) -> tuple[LoadlineHints | None, str | None]:
    if not path.is_file():
        return None, None
    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        return None, "hints file must be a mapping"
    unknown = set(raw) - ALLOWED_KEYS
    if unknown:
        return None, f"unknown keys: {sorted(unknown)}"
    try:
        return LoadlineHints.model_validate(raw), None
    except ValidationError as exc:
        return None, str(exc)
