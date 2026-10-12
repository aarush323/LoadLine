"""One parser for .loadline.yaml (Phase 1). Old keys unchanged; new keys optional."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

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

EXTENDED_ALLOWED_KEYS = ALLOWED_KEYS | frozenset(
    {
        "compose",
        "prepare",
        "auth",
        "meta",
    }
)


class ComposeSection(BaseModel):
    files: list[str] = Field(default_factory=list)
    start_set: Literal["all", "closure"] = "all"

    model_config = {"extra": "forbid"}


class LoadlineHints(BaseModel):
    schema_version: str = Field(default="1")
    compose_file: str | None = None
    dockerfile: str | None = None
    compose_profile: str | None = None
    app_service: str | None = None
    container_port: int | None = None
    health_path: str | None = None
    command: str | None = None
    env: dict[str, Any] = Field(default_factory=dict)
    exclude_operations: list[str] = Field(default_factory=list)
    slo_p95_ms: int | None = Field(default=None, alias="slo.p95_ms")
    slo_err_rate: float | None = Field(default=None, alias="slo.err_rate")
    compose: ComposeSection = Field(default_factory=ComposeSection)
    prepare: list[Any] = Field(default_factory=list)
    auth: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True, "extra": "ignore"}

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


def load_hints(path: Path) -> tuple[LoadlineHints | None, str | None]:
    if not path.is_file():
        return None, None
    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        return None, "hints file must be a mapping"
    unknown = set(raw) - EXTENDED_ALLOWED_KEYS
    if unknown:
        return None, f"unknown keys: {sorted(unknown)}"
    try:
        return LoadlineHints.model_validate(raw), None
    except ValidationError as exc:
        return None, str(exc)
