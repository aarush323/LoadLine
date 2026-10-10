"""Investigator runtime dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loadline.core.ledger import Ledger
from loadline.entire_runtime.graph import GraphClient


@dataclass
class ReadRange:
    path: str
    start_line: int
    end_line: int


@dataclass
class InvestigationDeps:
    repo_root: Path
    run_dir: Path
    run_id: str
    ledger: Ledger
    graph: GraphClient | None
    graph_degraded: bool = False
    dirty_worktree: bool = False
    read_ranges: list[ReadRange] = field(default_factory=list)
    boot: dict[str, Any] = field(default_factory=dict)
    allowed_hosts: frozenset[str] = frozenset()
    network: str = ""
    k6_wave_index: int = 0
    auth_profiles: dict[str, dict[str, str]] = field(default_factory=dict)
    console: Any = None
