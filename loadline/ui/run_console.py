"""Terminal progress for loadline run (stderr)."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from loadline.ui.events import EventSink, RunEvent
from loadline.ui.phases import PHASE_LABELS, Phase
from loadline.ui.render import emit, use_color


class BootProgress(Protocol):
    def boot_note(self, message: str) -> None: ...

    def health_tick(self, elapsed_s: float, budget_s: float) -> None: ...

    def compose_tick(self, elapsed_s: float) -> None: ...


@dataclass
class RunConsole:
    """Human-facing run progress on stderr."""

    json_mode: bool = False
    quiet: bool = False
    verbose: bool = False
    no_color: bool = False
    run_dir: Path | None = None
    _sink: EventSink = field(init=False)
    _active_phase: Phase | None = field(default=None, init=False)
    _phase_start: float = field(default=0.0, init=False)
    _last_health_tick: float = field(default=0.0, init=False)
    _last_compose_tick: float = field(default=0.0, init=False)
    _last_ledger_line: float = field(default=0.0, init=False)
    _timeline: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._sink = EventSink(self.run_dir)

    @classmethod
    def disabled(cls) -> RunConsole:
        return cls(json_mode=True, quiet=True)

    def enabled(self) -> bool:
        return not self.json_mode and not self.quiet

    def set_run_dir(self, run_dir: Path | None) -> None:
        self.run_dir = run_dir
        self._sink = EventSink(run_dir)

    def run_header(self, *, run_id: str | None, repo: Path) -> None:
        if not self.enabled():
            return
        rid = run_id or "pending"
        emit(f"loadline run  run_id={rid}  repo={repo}", sys.stderr, use_ansi=use_color(self.no_color))
        if self.run_dir:
            emit(f"artifacts: {self.run_dir}", sys.stderr, use_ansi=use_color(self.no_color))
        self._log("info", f"run started run_id={rid}")

    def phase_start(self, phase: Phase) -> None:
        if not self.enabled():
            return
        self._active_phase = phase
        self._phase_start = time.monotonic()
        label = PHASE_LABELS[phase]
        emit(f"... {label}", sys.stderr, use_ansi=use_color(self.no_color), style="bold")
        self._log("phase", f"start {phase.value}")

    def phase_done(self, phase: Phase, detail: str | None = None) -> None:
        if not self.enabled():
            return
        label = PHASE_LABELS[phase]
        suffix = f" ({detail})" if detail else ""
        emit(f"ok {label}{suffix}", sys.stderr, use_ansi=use_color(self.no_color), style="green")
        self._timeline.append({"phase": phase.value, "status": "ok", "detail": detail or ""})
        self._log("phase", f"done {phase.value} {detail or ''}")
        self._active_phase = None

    def phase_fail(self, phase: Phase, detail: str) -> None:
        if self.json_mode:
            return
        if self.quiet:
            emit(f"fail {PHASE_LABELS[phase]}: {detail[:200]}", sys.stderr, use_ansi=False)
            return
        label = PHASE_LABELS[phase]
        emit(f"fail {label}", sys.stderr, use_ansi=use_color(self.no_color), style="red bold")
        for line in detail.splitlines():
            emit(f"  {line}", sys.stderr, use_ansi=use_color(self.no_color))
        emit("  next: see run_dir artifacts or use --json for structured blocker", sys.stderr, use_ansi=False)
        self._timeline.append({"phase": phase.value, "status": "fail"})
        self._log("error", detail[:500])

    def note(self, message: str, *, verbose_only: bool = False) -> None:
        if not self.enabled():
            return
        if verbose_only and not self.verbose:
            return
        emit(f"  {message}", sys.stderr, use_ansi=use_color(self.no_color))
        self._log("info", message)

    def warn(self, message: str) -> None:
        if self.json_mode:
            return
        if self.quiet:
            return
        emit(f"warn: {message}", sys.stderr, use_ansi=use_color(self.no_color), style="yellow")
        self._log("warn", message)

    def trace(self, message: str) -> None:
        if not self.enabled():
            return
        emit(f"trace: {message}", sys.stderr, use_ansi=use_color(self.no_color))
        self._log("info", message)

    def boot_progress(self) -> _BootProgressAdapter:
        return _BootProgressAdapter(self)

    def investigate_event(self, source: str, summary: str, *, style: str | None = None) -> None:
        if not self.enabled() or self._active_phase != Phase.INVESTIGATE:
            return
        prefix = f"  [investigate] {summary}"
        emit(prefix, sys.stderr, use_ansi=use_color(self.no_color), style=style)
        self._log("info", f"{source}: {summary}")

    def ledger_event(self, event: dict[str, Any]) -> None:
        if not self.enabled() or self._active_phase != Phase.INVESTIGATE:
            return
        kind = str(event.get("kind") or "")
        if kind not in (
            "hypothesis",
            "experiment_admitted",
            "experiment_finished",
            "finding",
            "experiment_rejected",
            "k6_run",
        ):
            return
        now = time.monotonic()
        if not self.verbose and now - self._last_ledger_line < 2.0:
            return
        self._last_ledger_line = now
        summary = _ledger_one_liner(kind, event)
        emit(f"  [investigate] {summary}", sys.stderr, use_ansi=use_color(self.no_color))
        self._log("info", summary)

    def print_blocker(self, blocker: dict[str, Any] | None, run_dir: Path | None) -> None:
        if self.json_mode or not blocker:
            return
        summary = str(blocker.get("summary") or blocker.get("code") or "blocked")
        tty = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
        if self.quiet and tty and "\n" in summary:
            for line in summary.splitlines():
                emit(line, sys.stderr, use_ansi=False)
            if run_dir:
                emit(f"  run_dir: {run_dir}", sys.stderr, use_ansi=False)
            return
        if self.quiet:
            emit(summary[:300], sys.stderr, use_ansi=False)
            return
        self.phase_fail(Phase.BOOT, summary)
        if run_dir:
            emit(f"  run_dir: {run_dir}", sys.stderr, use_ansi=False)

    def timeline(self) -> list[dict[str, str]]:
        return list(self._timeline)

    def _log(self, level: str, message: str) -> None:
        phase = self._active_phase.value if self._active_phase else None
        self._sink.write(RunEvent(level=level, message=message, phase=phase))


@dataclass
class _BootProgressAdapter(BootProgress):
    console: RunConsole

    def boot_note(self, message: str) -> None:
        self.console.note(message, verbose_only=False)

    def health_tick(self, elapsed_s: float, budget_s: float) -> None:
        if not self.console.enabled():
            return
        now = time.monotonic()
        if now - self.console._last_health_tick < 10.0 and elapsed_s > 0:
            return
        self.console._last_health_tick = now
        self.console.note(f"health: {int(elapsed_s)}s / {int(budget_s)}s")

    def compose_tick(self, elapsed_s: float) -> None:
        if not self.console.enabled():
            return
        now = time.monotonic()
        if now - self.console._last_compose_tick < 15.0 and elapsed_s > 0:
            return
        self.console._last_compose_tick = now
        self.console.note(f"boot: still building... ({int(elapsed_s)}s)")


def _ledger_one_liner(kind: str, event: dict[str, Any]) -> str:
    if kind == "hypothesis":
        return f"hypothesis: {str(event.get('claim', 'recorded'))[:120]}"
    if kind == "experiment_finished":
        return f"experiment_finished: {event.get('experiment_kind', 'run')}"
    if kind == "experiment_admitted":
        return f"experiment_admitted: {event.get('experiment_kind', 'run')}"
    if kind == "experiment_rejected":
        return f"experiment_rejected: {event.get('reason', '')[:80]}"
    if kind == "finding":
        return f"finding: {str(event.get('symptom', event.get('mechanism', 'recorded')))[:120]}"
    if kind == "k6_run":
        exp = event.get("experiment_id") or "?"
        wave = event.get("wave") or "?"
        result = event.get("result") or {}
        rate = result.get("offered_rps")
        dropped = result.get("dropped_iterations", 0)
        p95_bits: list[str] = []
        ops = result.get("operations") or {}
        if isinstance(ops, dict):
            for op_id, row in list(ops.items())[:2]:
                if isinstance(row, dict) and row.get("p95_ms") is not None:
                    p95_bits.append(f"p95_{op_id}={int(round(float(row['p95_ms'])))}ms")
        tail = " ".join(p95_bits)
        if dropped:
            tail = f"{tail} dropped={dropped}".strip()
        rate_s = f"rate={rate}" if rate is not None else ""
        return f"← k6 {exp} {wave} {rate_s} {tail}".strip()
    return kind
