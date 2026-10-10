"""Append-only run ledger (tech_doc.md Appendix B, §4.7)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable
from typing import Any, Iterator

S6_EVENT_KINDS = frozenset(
    {
        "experiment_admitted",
        "experiment_rejected",
        "experiment_finished",
        "prediction_scored",
        "prediction_rejected",
        "baseline_finished",
        "report_written",
        "investigation_incomplete",
    }
)


@dataclass
class Ledger:
    run_id: str
    path: Path
    seq: int = 0
    _events: list[dict[str, Any]] = field(default_factory=list)
    on_event: Callable[[dict[str, Any]], None] | None = None

    @classmethod
    def open(cls, run_dir: Path, run_id: str) -> Ledger:
        path = run_dir / "ledger.jsonl"
        ledger = cls(run_id=run_id, path=path)
        if path.is_file():
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                event = json.loads(line)
                ledger._events.append(event)
                ledger.seq = max(ledger.seq, int(event.get("seq", 0)))
        return ledger

    def append(self, kind: str, *, evidence_ids: list[str], **payload: Any) -> dict[str, Any]:
        self.seq += 1
        event: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "seq": self.seq,
            "kind": kind,
            "evidence_ids": list(evidence_ids),
            **payload,
        }
        self._events.append(event)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")
        if self.on_event is not None:
            self.on_event(event)
        return event

    def events(self) -> Iterator[dict[str, Any]]:
        return iter(self._events)

    def events_of(self, kind: str) -> list[dict[str, Any]]:
        return [e for e in self._events if e.get("kind") == kind]
