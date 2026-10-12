"""Read-only index of past runs (presentation only, never writes)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class RunSummary:
    run_id: str
    run_dir: Path
    mtime: float
    repo_name: str
    repo_root: str
    state: str
    peak_rps: float | None
    waves: int
    dropped: int
    verification_verdict: str | None = None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _repo_from_profile(run_dir: Path) -> tuple[str, str]:
    prof = _read_json(run_dir / "profile.json")
    root = str((prof or {}).get("root") or "").strip()
    if not root:
        return "unknown", ""
    return Path(root).name or root, root


def _state_waves_peak(run_dir: Path) -> tuple[str, int, float | None, int]:
    """Read state / wave stats from the ledger only (cheap line scan)."""
    state = ""
    waves = 0
    peak: float | None = None
    dropped = 0
    try:
        lines = (run_dir / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        kind = ev.get("kind")
        if kind == "k6_run":
            waves += 1
            result = ev.get("result") if isinstance(ev.get("result"), dict) else {}
            try:
                offered = float(result.get("offered_rps"))
                peak = max(peak or 0.0, offered)
            except (TypeError, ValueError):
                pass
            try:
                dropped += int(result.get("dropped_iterations") or 0)
            except (TypeError, ValueError):
                pass
        elif kind == "report_written" and not state:
            state = str(ev.get("run_state") or "")
        elif kind == "investigation_incomplete":
            state = "investigation_incomplete"
    if not state:
        report = _read_json(run_dir / "report.json")
        if isinstance(report, dict):
            state = str(report.get("run_state") or "")
    return state or "unknown", waves, peak, dropped


def _verification_verdict(run_dir: Path) -> str | None:
    data = _read_json(run_dir / "verification.json")
    if not data:
        return None
    verdict = data.get("verdict")
    return str(verdict) if verdict else None


def _blocker_state(run_dir: Path) -> str | None:
    data = _read_json(run_dir / "attempts.json")
    if not data:
        return None
    blocker = data.get("blocker") if isinstance(data.get("blocker"), dict) else None
    if not blocker:
        return "blocked"
    return str(blocker.get("code") or "blocked")


def summarize_run(run_dir: Path) -> RunSummary | None:
    """Return None when the directory holds no recognizable run evidence."""
    try:
        if not run_dir.is_dir():
            return None
        has_ledger = (run_dir / "ledger.jsonl").is_file()
        has_report = (run_dir / "report.json").is_file()
        has_attempts = (run_dir / "attempts.json").is_file()
        if not has_ledger and not has_report and not has_attempts:
            return None
        try:
            mtime = max(
                (run_dir / name).stat().st_mtime
                for name in (
                    "ledger.jsonl",
                    "report.json",
                    "report.md",
                    "verification.json",
                    "attempts.json",
                )
                if (run_dir / name).is_file()
            )
        except OSError:
            try:
                mtime = run_dir.stat().st_mtime
            except OSError:
                mtime = 0.0
        repo_name, repo_root = _repo_from_profile(run_dir)
        state, waves, peak, dropped = _state_waves_peak(run_dir)
        if state in ("", "unknown") and has_attempts and not has_ledger:
            state = _blocker_state(run_dir) or "blocked"
        return RunSummary(
            run_id=run_dir.name,
            run_dir=run_dir,
            mtime=mtime,
            repo_name=repo_name,
            repo_root=repo_root,
            state=state,
            peak_rps=peak,
            waves=waves,
            dropped=dropped,
            verification_verdict=_verification_verdict(run_dir),
        )
    except Exception:
        return None


_POST_BOOT_STATES = {
    "completed",
    "investigation_incomplete",
    "measurement_incomplete",
    "generator_limited",
    "above_measured_range",
}
_NOT_BOOTED_STATES = {
    "boot_failed",
    "no_entrypoint",
    "needs_input",
    "policy_refused",
    "blocked",
    "egress_not_enforced",
}


def run_booted(summary: RunSummary) -> bool:
    """True when the app came up; failed-boot blocker states stay hidden on the web index."""
    if summary.waves > 0:
        return True
    if summary.state in _POST_BOOT_STATES:
        return True
    if summary.state in _NOT_BOOTED_STATES:
        return False
    return False


def scan_runs(
    runs_root: Path, *, repo_filter: str | None = None, booted_only: bool = False
) -> list[RunSummary]:
    """Newest-first summaries; unreadable entries are skipped, never fatal."""
    try:
        children = sorted(
            (p for p in runs_root.iterdir() if p.is_dir()),
            key=lambda p: p.name,
        )
    except OSError:
        return []
    out: list[RunSummary] = []
    for child in children:
        summary = summarize_run(child)
        if summary is None:
            continue
        if repo_filter and repo_filter.lower() not in summary.repo_root.lower():
            continue
        if booted_only and not run_booted(summary):
            continue
        out.append(summary)
    out.sort(key=lambda s: s.mtime, reverse=True)
    _disambiguate_repos(out)
    return out


def _disambiguate_repos(summaries: list[RunSummary]) -> None:
    """Expand repo_name to parent/name where basenames collide across repos."""
    seen: dict[str, int] = {}
    for s in summaries:
        seen[s.repo_name] = seen.get(s.repo_name, 0) + 1
    for s in summaries:
        if s.repo_name != "unknown" and seen.get(s.repo_name, 0) > 1 and s.repo_root:
            parts = Path(s.repo_root).parts
            s.repo_name = "/".join(parts[-2:]) if len(parts) >= 2 else s.repo_root


def match_runs(summaries: list[RunSummary], prefix: str) -> list[RunSummary]:
    prefix = prefix.strip()
    return [s for s in summaries if s.run_id == prefix or s.run_id.startswith(prefix)]


def age_string(mtime: float) -> str:
    """Relative age for the picker; clock-safe fallback on weird values."""
    try:
        from time import time as _now

        delta = max(0.0, _now() - float(mtime))
    except (TypeError, ValueError):
        return "?"
    if delta < 90:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    return f"{int(delta // 86400)}d ago"
