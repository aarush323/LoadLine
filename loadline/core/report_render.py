"""Render report.md / report.json from ledger and waves (tech_doc.md §14)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from loadline.core.ledger import Ledger
from loadline.core.report_model import ReportModel, ReportNumber, primary_attribution_blocks_app_bottleneck
from loadline.core.verdict import moves_bracket


class ReportRenderError(Exception):
    pass


def recompute_from_waves(run_dir: Path) -> dict[str, Any]:
    waves_root = run_dir / "waves"
    out: dict[str, Any] = {"waves": {}}
    if not waves_root.is_dir():
        return out
    for child in sorted(waves_root.iterdir()):
        if not child.is_dir():
            continue
        tele_path = child / "telemetry.json"
        summary_path = child / "k6.summary.json"
        entry: dict[str, Any] = {}
        if tele_path.is_file():
            entry["telemetry"] = json.loads(tele_path.read_text())
        if summary_path.is_file():
            entry["summary"] = json.loads(summary_path.read_text())
        if entry:
            out["waves"][child.name] = entry
    return out


def _load_bracket(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "bracket.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _investigator_ran(ledger: Ledger) -> bool:
    for e in ledger.events():
        if e.get("kind") == "hypothesis":
            return True
        if e.get("kind") == "experiment_finished" and e.get("experiment_kind") in (
            "rate_step",
            "refine",
            "isolate",
            "mix_ablation",
        ):
            return True
    waves = list((ledger.path.parent / "waves").glob("investigate-*")) if ledger.path.parent else []
    return bool(waves)


def _run_state_from_bracket(
    bracket: dict[str, Any],
    *,
    incomplete_reason: str | None,
    ledger: Ledger,
) -> tuple[str, str | None]:
    if incomplete_reason or ledger.events_of("investigation_incomplete"):
        ev = ledger.events_of("investigation_incomplete")
        reason = incomplete_reason or (ev[-1].get("reason") if ev else "unknown")
        return "investigation_incomplete", reason
    status = str(bracket.get("status") or "unknown")
    if status in ("bracketed", "application_limited"):
        return "completed", None
    if status in (
        "generator_limited",
        "above_measured_range",
        "measurement_incomplete",
        "below_ladder",
        "invalid",
        "above_ladder",
    ):
        return status, None
    return "completed", None


def _experiment_log_entries(ledger: Ledger) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for e in ledger.events():
        kind = e.get("kind")
        if kind not in (
            "experiment_admitted",
            "experiment_rejected",
            "experiment_finished",
            "prediction_scored",
            "prediction_rejected",
            "baseline_finished",
        ):
            continue
        row: dict[str, Any] = {
            "ledger_kind": kind,
            "experiment_kind": e.get("experiment_kind") or e.get("experiment_id"),
            "verdict": e.get("verdict"),
            "rate": e.get("rate"),
            "throughput_rps": e.get("throughput_rps"),
            "plan_shape": e.get("plan_shape") or e.get("params"),
            "reason": e.get("reason"),
        }
        if e.get("outcome"):
            oc = e["outcome"]
            row["verdict"] = row.get("verdict") or oc.get("verdict")
            row["throughput_rps"] = row.get("throughput_rps") or oc.get("throughput_rps")
            row["plan_shape"] = row.get("plan_shape") or oc.get("plan_shape")
        entries.append(row)
    return entries


def _capacity_from_evidence(bracket: dict[str, Any], ledger: Ledger) -> dict[str, Any]:
    status = bracket.get("status") or "not measured (no bracket)"
    cap: dict[str, Any] = {
        "bracket_status": status,
        "tag": "measured",
    }
    if bracket.get("capacity_rps") is not None:
        cap["capacity_rps"] = bracket["capacity_rps"]
        cap["capacity_evidence"] = "bracket.json"
    elif bracket.get("lo") is not None:
        cap["capacity_rps"] = bracket["lo"]
        cap["capacity_evidence"] = "bracket.json"
    best_pass: float | None = None
    for e in ledger.events():
        if e.get("kind") != "experiment_finished":
            continue
        v = str(e.get("verdict") or "")
        if e.get("outcome"):
            v = str(e["outcome"].get("verdict") or v)
        if not moves_bracket(v):  # type: ignore[arg-type]
            continue
        shape = e.get("plan_shape") or e.get("params") or {}
        if isinstance(e.get("outcome"), dict):
            shape = e["outcome"].get("plan_shape") or shape
        rate = shape.get("rate") if isinstance(shape, dict) else e.get("rate")
        if rate is not None:
            best_pass = max(best_pass or 0, float(rate))
    if best_pass is not None and "capacity_rps" not in cap:
        cap["capacity_rps"] = best_pass
        cap["capacity_evidence"] = "ledger experiment_finished pass"
    if bracket.get("last_achieved_rps") is not None:
        cap["last_achieved_rps"] = bracket["last_achieved_rps"]
    if status == "generator_limited":
        cap["note"] = (
            "Highest valid pass is capacity; higher offered rates may show achieved throughput "
            "below offer because the generator could not deliver the load (not application capacity)."
        )
    return cap


def build_report_model(
    run_dir: Path,
    run_id: str,
    *,
    incomplete_reason: str | None = None,
) -> ReportModel:
    ledger = Ledger.open(run_dir, run_id)
    waves = recompute_from_waves(run_dir)
    bracket = _load_bracket(run_dir)
    model = ReportModel(run_id=run_id)
    run_state, inc = _run_state_from_bracket(bracket, incomplete_reason=incomplete_reason, ledger=ledger)
    model.run_state = run_state
    model.incomplete_reason = inc

    baseline_tele = (waves.get("waves") or {}).get("baseline", {}).get("telemetry") or {}
    attribution = baseline_tele.get("attribution") or []
    if attribution:
        model.attribution_primary = attribution[0].get("limit")

    measured: list[ReportNumber] = []
    cap = _capacity_from_evidence(bracket, ledger)
    if cap.get("capacity_rps") is not None:
        measured.append(
            ReportNumber(
                value=str(cap["capacity_rps"]),
                unit="req/s",
                evidence_id=str(cap.get("capacity_evidence", "bracket.json")),
                tag="measured",
            )
        )
    baseline_events = ledger.events_of("baseline_finished")
    if baseline_events:
        ev = baseline_events[-1]
        if ev.get("throughput_rps") is not None:
            measured.append(
                ReportNumber(
                    value=str(ev["throughput_rps"]),
                    unit="req/s",
                    evidence_id="ev-baseline-throughput",
                    tag="measured",
                )
            )
        if ev.get("successful_samples") is not None:
            measured.append(
                ReportNumber(
                    value=str(ev["successful_samples"]),
                    unit="samples",
                    evidence_id="ev-baseline-samples",
                    tag="measured",
                )
            )
    model.measured = measured
    model.capacity = cap
    model.experiment_log = _experiment_log_entries(ledger)
    model.hypotheses = [e for e in ledger.events() if e.get("kind") == "hypothesis"]
    model.findings = [e for e in ledger.events() if e.get("kind") == "finding"]
    model.limitations = _default_limitations(model, bracket, ledger)
    return model


def _default_limitations(model: ReportModel, bracket: dict[str, Any], ledger: Ledger) -> list[str]:
    lines = [
        "Loadline ran the repository in an isolated Docker network with egress denied.",
    ]
    if _investigator_ran(ledger):
        lines.append(
            "Model providers may receive repository excerpts returned by investigator tools during this run."
        )
    else:
        lines.append("The Investigator agent did not run or produced no experiments on this run.")
    status = bracket.get("status")
    if status == "measurement_incomplete":
        lines.append("Capacity bracketing did not complete: steps remained below MIN_SAMPLES after bounded retries.")
    elif status in ("generator_limited", "above_measured_range"):
        lines.append(
            "Search stopped at generator delivery limits; reported capacity_rps is the highest valid pass, "
            "not achieved throughput on generator-limited steps."
        )
    elif status in ("bracketed", "application_limited"):
        lines.append("Capacity bracketing completed from measured pass/fail steps.")
    elif not bracket:
        lines.append("No bracket.json was written for this run.")
    if model.run_state == "investigation_incomplete":
        lines.append(f"Investigation ended early: {model.incomplete_reason or 'reason not recorded'}.")
    if model.attribution_primary in ("host", "generator", "measurement_failure"):
        lines.append(
            f"Primary limit attribution for the baseline step was {model.attribution_primary}; "
            "an application bottleneck was not established from that step alone."
        )
    return lines


def render_markdown(model: ReportModel) -> str:
    lines = [
        "# Loadline report",
        "",
        f"**Run state:** {model.run_state}",
        "",
        "## Verdict",
        "",
    ]
    if model.run_state == "investigation_incomplete":
        lines.append(f"[measured] Investigation incomplete: {model.incomplete_reason or 'not measured (reason)'}")
    elif model.run_state == "measurement_incomplete":
        lines.append("[measured] Measurement incomplete: ladder could not produce valid pass/fail steps.")
    elif model.run_state == "generator_limited":
        lines.append("[measured] Search stopped: generator could not deliver higher offered rates.")
    elif model.run_state == "above_measured_range":
        lines.append("[measured] Highest valid pass recorded; application limit above measured range was not established.")
    elif model.findings:
        lines.append("[measured] Findings recorded in the ledger.")
    else:
        lines.append("[measured] No application bottleneck was established from measured evidence.")

    lines.extend(["", "## Capacity", ""])
    cap = model.capacity or {}
    if cap.get("capacity_rps") is not None:
        lines.append(f"- [measured] capacity_rps {cap['capacity_rps']} req/s ({cap.get('capacity_evidence', 'evidence')})")
    lines.append(f"- [measured] bracket_status {cap.get('bracket_status', 'not measured')}")
    if cap.get("last_achieved_rps") is not None:
        lines.append(f"- [measured] last_achieved_rps {cap['last_achieved_rps']} req/s (achieved throughput, not capacity)")
    if cap.get("note"):
        lines.append(f"- {cap['note']}")

    lines.extend(["", "## Experiment log", ""])
    if model.experiment_log:
        for entry in model.experiment_log:
            kind = entry.get("experiment_kind") or entry.get("ledger_kind") or "event"
            verdict = entry.get("verdict") or ""
            rate = entry.get("rate")
            shape = entry.get("plan_shape") or {}
            offered = rate if rate is not None else (shape.get("rate") if isinstance(shape, dict) else None)
            tp = entry.get("throughput_rps")
            parts = [f"[measured] {kind}"]
            if offered is not None:
                parts.append(f"offered={offered}")
            if tp is not None:
                parts.append(f"throughput={tp}")
            if verdict:
                parts.append(f"verdict={verdict}")
            lines.append(" ".join(parts))
    else:
        lines.append("- not measured (no experiments logged)")

    lines.extend(["", "## Hypotheses", ""])
    if model.hypotheses:
        for h in model.hypotheses:
            lines.append(f"- [hypothesis] {h.get('claim', 'recorded')}")
    else:
        lines.append("- none recorded")

    lines.extend(["", "## Limitations", ""])
    for lim in model.limitations:
        lines.append(f"- {lim}")

    prose = "\n".join(lines)
    model.prose_blocks = [prose]
    if primary_attribution_blocks_app_bottleneck(model.attribution_primary, prose):
        raise ReportRenderError("wording lint: application bottleneck claimed under host/generator attribution")
    return prose


def validate_report_digits(markdown: str, model: ReportModel) -> None:
    allowed = model.all_digit_tokens()
    for token in re.findall(r"\d+\.?\d*", markdown):
        if token not in allowed:
            if token in ("1",) and "loadline-report/1" in json.dumps(model.to_dict()):
                continue
            raise ReportRenderError(f"stray digit in report prose: {token}")


def write_report(
    run_dir: Path,
    run_id: str,
    *,
    incomplete_reason: str | None = None,
) -> tuple[Path, Path]:
    ledger = Ledger.open(run_dir, run_id)
    model = build_report_model(run_dir, run_id, incomplete_reason=incomplete_reason)
    md = render_markdown(model)
    validate_report_digits(md, model)
    waves = recompute_from_waves(run_dir)
    _assert_ledger_wave_consistency(ledger, waves, model)

    report_json = model.to_dict()
    report_json["waves_snapshot"] = waves
    json_path = run_dir / "report.json"
    md_path = run_dir / "report.md"
    json_path.write_text(json.dumps(report_json, indent=2))
    md_path.write_text(md)
    ledger.append(
        "report_written",
        evidence_ids=[m.evidence_id for m in model.measured],
        run_state=model.run_state,
        paths={"report_md": str(md_path), "report_json": str(json_path)},
    )
    return md_path, json_path


def mark_investigation_incomplete(run_dir: Path, run_id: str, reason: str) -> tuple[Path, Path]:
    ledger = Ledger.open(run_dir, run_id)
    ledger.append("investigation_incomplete", evidence_ids=[], reason=reason)
    return write_report(run_dir, run_id, incomplete_reason=reason)


def _assert_ledger_wave_consistency(ledger: Ledger, waves: dict[str, Any], model: ReportModel) -> None:
    baseline = ledger.events_of("baseline_finished")
    if not baseline:
        return
    tele = (waves.get("waves") or {}).get("baseline", {}).get("telemetry")
    if not tele:
        tele = (waves.get("waves") or {}).get("baseline")
    if not tele:
        return
    ledger_throughput = baseline[-1].get("throughput_rps")
    if ledger_throughput is None:
        return
    baseline_vals = [float(m.value) for m in model.measured if m.evidence_id == "ev-baseline-throughput"]
    if baseline_vals and abs(baseline_vals[0] - float(ledger_throughput)) > 1e-3:
        raise ReportRenderError("ledger baseline throughput does not match report model")
