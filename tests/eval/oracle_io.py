"""Load sealed oracles (tests only — never import from loadline/)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ORACLES_DIR = Path(__file__).resolve().parents[1] / "oracles"


def load_sealed_oracle(name: str) -> dict[str, Any]:
    path = ORACLES_DIR / name
    if not path.is_file():
        raise FileNotFoundError(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"oracle {name} must be a mapping")
    return data


def list_sealed_oracles() -> list[Path]:
    return sorted(ORACLES_DIR.glob("*.sealed.yaml"))
