"""Post-run terminal dashboard (presentation only, read-only).

Renders the same evidence the CLI and report.md already describe —
ledger.jsonl, report.json and experiments/*.json — as a compact terminal
summary. Never computes verdicts, never touches pipeline state, never
raises: any unreadable artifact degrades to "Not measured".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loadline.ui.render import emit, is_tty, use_color
from loadline.ui.spark import fmt_int, fmt_ms, vu_bar

RULE = "─" * 51
_MAX_WAVES = 6
_MAX_TRAIL = 4
_MAX_OPS = 5


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _ledger_events(run_dir: Path) -> list[dict[str, Any]]:
    try:
        lines = (run_dir / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict):
            out.append(ev)
    return out


def _endpoint_paths(run_dir: Path) -> dict[str, tuple[str, str]]:
    """op id -> (METHOD, path) from persisted experiment inputs."""
    mapping: dict[str, tuple[str, str]] = {}
    exp_dir = run_dir / "experiments"
    if not exp_dir.is_dir():
        return mapping
    try:
        children = sorted(exp_dir.glob("*.json"))
    except OSError:
        return mapping
    for child in children:
        rec = _read_json(child)
        if not rec:
            continue
        raw_input = rec.get("input")
        eps = raw_input.get("endpoints") if isinstance(raw_input, dict) else None
        if not isinstance(eps, list):
            continue
        for ep in eps:
            if not isinstance(ep, dict):
                continue
            op_id = str(ep.get("id") or ep.get("path") or "").strip()
            if not op_id or op_id in mapping:
                continue
            mapping[op_id] = (
                str(ep.get("method") or "GET").upper(),
                str(ep.get("path") or op_id),
            )
    return mapping


def _k6_waves(ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    waves = [e for e in ledger if e.get("kind") == "k6_run" and isinstance(e.get("result"), dict)]
    waves.sort(key=lambda e: float((e.get("result") or {}).get("offered_rps") or 0.0))
    return waves


def _short(text: Any, limit: int = 72) -> str:
    return str(text or "").strip().replace("\n", " ")[:limit]


def _wave_ops(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    ops = result.get("operations")
    if not isinstance(ops, dict):
        return {}
    return {str(k): v for k, v in ops.items() if isinstance(v, dict)}


def dashboard_rows(
    run_dir: Path | None, run_id: str | None, *, full: bool = False
) -> list[tuple[str, str | None]]:
    """Build (text, style) rows; empty list when there is nothing to show.

    full=True lifts the display caps and appends limitations, for the
    explicit `dashboard --run` view. The auto post-run panel stays compact.
    """
    if run_dir is None:
        return []
    try:
        run_dir = Path(run_dir)
        if not run_dir.is_dir():
            return []
        report = _read_json(run_dir / "report.json")
        ledger = _ledger_events(run_dir)
        waves = _k6_waves(ledger)
        if report is None and not waves and not ledger:
            return []
        return _assemble(run_dir, run_id, report, ledger, waves, full=full)
    except Exception:
        return []


def _assemble(
    run_dir: Path,
    run_id: str | None,
    report: dict[str, Any] | None,
    ledger: list[dict[str, Any]],
    waves: list[dict[str, Any]],
    *,
    full: bool = False,
) -> list[tuple[str, str | None]]:
    rows: list[tuple[str, str | None]] = []
    max_waves = len(waves) if full else _MAX_WAVES
    max_ops = len(_wave_ops(waves[-1].get("result") or {})) if (full and waves) else _MAX_OPS
    max_trail = len(ledger) if full else _MAX_TRAIL
    rid = run_id or (str(report.get("run_id")) if report else None) or run_dir.name
    rows.append(("", None))
    rows.append((RULE, "dim"))
    rows.append((f"RESULT · run {rid}", "bold"))

    if report is not None:
        state = str(report.get("run_state") or "completed")
        if state == "investigation_incomplete":
            rows.append(
                (f"Investigation incomplete — {_short(report.get('incomplete_reason') or 'reason not recorded', 90)}", None)
            )
        else:
            cap = report.get("capacity") if isinstance(report.get("capacity"), dict) else {}
            if isinstance(cap, dict) and cap.get("capacity_rps") is not None:
                rows.append(
                    (
                        f"Measured capacity {cap['capacity_rps']} req/s "
                        f"({cap.get('capacity_evidence', 'evidence')}) [MEASURED]",
                        None,
                    )
                )
            elif waves:
                rows.append(("Completed — capacity not established from measured evidence.", None))
            else:
                rows.append(("Not measured — no k6 waves recorded in this run.", None))
    elif waves:
        rows.append(("Report not written yet — showing measured k6 waves only.", None))
    else:
        rows.append(("Not measured — no report or k6 waves in this run.", None))

    if waves:
        peak = max(float((w.get("result") or {}).get("offered_rps") or 0.0) for w in waves)
        dropped = sum(int((w.get("result") or {}).get("dropped_iterations") or 0) for w in waves)
        n_ops = len(_wave_ops(waves[-1].get("result") or {}))
        rows.append(
            (
                f"peak {peak:g}rps │ {len(waves)} waves │ dropped {dropped} │ {n_ops} ops  [MEASURED]",
                "coral" if dropped > 0 else None,
            )
        )
        rows.append(("PRESSURE · OFFERED → P95 · VUS", "dim"))
        paths = _endpoint_paths(run_dir)
        shown = waves[:max_waves]
        for w in shown:
            result = w.get("result") or {}
            ops = _wave_ops(result)
            offered = result.get("offered_rps")
            offered_s = f"{offered:g}rps" if offered is not None else "?rps"
            if ops:
                ranked = sorted(ops.items(), key=lambda kv: float(kv[1].get("p95_ms") or 0.0), reverse=True)
                top_id, top = ranked[0]
                p95_s = f"{top_id} p95 {fmt_ms(top.get('p95_ms'))}"
                if len(ranked) > 1:
                    p95_s += f" (+{len(ranked) - 1} ops)"
            else:
                p95_s = "ops not tagged"
            vus_max, vu_ceiling = result.get("vus_max"), result.get("vu_ceiling")
            if vus_max is not None and vu_ceiling:
                vu_s = f"VUs {vu_bar(vus_max, vu_ceiling)} {fmt_int(vus_max)}/{fmt_int(vu_ceiling)}"
            else:
                vu_s = "VUs Not measured"
            drop_n = int(result.get("dropped_iterations") or 0)
            drop_s = f"dropped {drop_n}" if drop_n else "dropped 0"
            exp = w.get("experiment_id") or "exp ?"
            rows.append(
                (f"· {offered_s} → {p95_s} · {vu_s} · {drop_s} · {exp}", "coral" if drop_n > 0 else None)
            )
        if len(waves) > max_waves:
            rows.append((f"· +{len(waves) - max_waves} more waves (see ledger.jsonl)", "dim"))

        latest = waves[-1].get("result") or {}
        ops = _wave_ops(latest)
        if ops:
            rows.append(("OPERATIONS · LATEST WAVE", "dim"))
            paths = paths or _endpoint_paths(run_dir)
            for i, (op_id, row) in enumerate(
                sorted(ops.items(), key=lambda kv: float(kv[1].get("p95_ms") or 0.0), reverse=True)
            ):
                if i >= max_ops:
                    rows.append((f"· +{len(ops) - max_ops} more operations", "dim"))
                    break
                if op_id in paths:
                    method, path = paths[op_id]
                    label = f"{method} {path}"
                else:
                    label = op_id
                err = int(row.get("error_count") or 0)
                rows.append(
                    (
                        f"· {label} — p95 {fmt_ms(row.get('p95_ms'))} · err {err} "
                        f"· offered {row.get('offered_rps', '?')} / achieved "
                        f"{float(row.get('achieved_rps') or 0.0):.1f}rps",
                        "coral" if err > 0 else None,
                    )
                )
            rows.append(("Source map: not persisted in run artifacts — see report.md", "dim"))
    else:
        rows.append(("No k6 waves recorded — load was not measured on this run.", None))

    trail = _trail_rows(ledger, limit=None if full else _MAX_TRAIL)
    if trail:
        rows.append(("INVESTIGATION TRAIL", "dim"))
        rows.extend(trail)

    if full:
        rows.extend(_limitation_rows(run_dir, rid))

    marks: list[str] = []
    for name in ("report.md", "report.json", "ledger.jsonl"):
        marks.append(f"{name} {'✓' if (run_dir / name).is_file() else '·'}")
    rows.append((f"artifacts: {'  '.join(marks)}", "dim"))
    rows.append((RULE, "dim"))
    return rows


def _trail_rows(ledger: list[dict[str, Any]], limit: int | None = _MAX_TRAIL) -> list[tuple[str, str | None]]:
    picks: list[tuple[str, str | None]] = []
    for e in ledger:
        kind = str(e.get("kind") or "")
        if kind == "hypothesis":
            picks.append((f"· hypothesis: {_short(e.get('claim'))}", None))
        elif kind == "experiment_rejected":
            picks.append((f"· rejected: {_short(e.get('reason'))}", "coral"))
        elif kind == "experiment_finished":
            picks.append(
                (f"· finished: {_short(e.get('experiment_kind') or e.get('experiment_id'))}", None)
            )
        elif kind == "finding":
            picks.append((f"· finding: {_short(e.get('symptom') or e.get('mechanism'))}", None))
        elif kind == "investigation_incomplete":
            picks.append((f"· incomplete: {_short(e.get('reason'))}", "coral"))
        elif kind == "report_written":
            picks.append((f"· report: {_short(e.get('run_state') or 'written')}", None))
    return picks if limit is None else picks[-limit:]


def _limitation_rows(run_dir: Path, run_id: str) -> list[tuple[str, str | None]]:
    """Validity notes recomputed read-only from ledger/waves; never raises."""
    try:
        from loadline.core.report_render import build_report_model

        model = build_report_model(run_dir, run_id)
        if not model.limitations:
            return []
        rows: list[tuple[str, str | None]] = [("VALIDITY · LIMITATIONS", "dim")]
        rows.extend((f"· {line}", "dim") for line in model.limitations)
        return rows
    except Exception:
        return []


def build_dashboard_text(run_dir: Path | None, run_id: str | None, *, full: bool = False) -> str:
    return "\n".join(text for text, _style in dashboard_rows(run_dir, run_id, full=full))


def maybe_emit_dashboard(console: Any, run_dir: Path | None, run_id: str | None) -> bool:
    """Emit the dashboard to stderr on interactive runs; never raises."""
    try:
        if console is None or getattr(console, "json_mode", False) or getattr(console, "quiet", False):
            return False
        if not getattr(console, "enabled", lambda: False)():
            return False
        if not is_tty(sys.stderr):
            return False
        if run_dir is None:
            return False
        rows = dashboard_rows(Path(run_dir), run_id)
        if not rows:
            return False
        use_ansi = use_color(getattr(console, "no_color", False))
        for text, style in rows:
            emit(text, sys.stderr, use_ansi=use_ansi, style=style)
        return True
    except Exception:
        return False
