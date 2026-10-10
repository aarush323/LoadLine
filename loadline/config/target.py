"""Frozen boot target (Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    service: str
    port: int
    health_path: str
    origin: str
