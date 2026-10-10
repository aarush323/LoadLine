"""Run event log for stderr and optional events.jsonl."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

EventLevel = Literal["info", "warn", "error", "phase"]


@dataclass(frozen=True)
class RunEvent:
    level: EventLevel
    message: str
    phase: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "t": datetime.now(timezone.utc).isoformat(),
            "level": self.level,
            "phase": self.phase,
            "message": self.message,
        }


class EventSink:
    def __init__(self, run_dir: Path | None) -> None:
        self._path = run_dir / "events.jsonl" if run_dir else None

    def write(self, event: RunEvent) -> None:
        if self._path is None:
            return
        if os.environ.get("LOADLINE_LOG", "").lower() not in ("debug", "1", "true"):
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.to_json()) + "\n")
