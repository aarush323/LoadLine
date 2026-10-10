"""S8 deterministic acceptance checks (tests only)."""

from __future__ import annotations

from typing import Any, Iterable

from loadline.core.report_model import primary_attribution_blocks_app_bottleneck


def _ledger_events(ledger_or_events: Any) -> list[dict[str, Any]]:
    if hasattr(ledger_or_events, "events"):
        return list(ledger_or_events.events())
    return list(ledger_or_events)


def has_confirmed_prediction(events: Iterable[dict[str, Any]]) -> bool:
    for event in events:
        if event.get("kind") != "prediction_scored":
            continue
        if event.get("outcome") == "confirmed":
            return True
    return False


def finding_cites_decoy_comment(finding: dict[str, Any], decoy_substrings: list[str]) -> bool:
    blob = " ".join(
        str(finding.get(key, ""))
        for key in ("mechanism", "symptom", "component", "observed_facts", "remediation")
    )
    if isinstance(finding.get("observed_facts"), list):
        blob += " " + " ".join(str(x) for x in finding["observed_facts"])
    lower = blob.lower()
    return any(sub.lower() in lower for sub in decoy_substrings)


def misleading_comment_finding_allowed(
    finding: dict[str, Any],
    ledger_or_events: Any,
    *,
    decoy_substrings: list[str],
) -> bool:
    events = _ledger_events(ledger_or_events)
    if not finding_cites_decoy_comment(finding, decoy_substrings):
        return True
    return has_confirmed_prediction(events)


def generator_bound_finding_allowed(primary_attribution: str | None, finding: dict[str, Any]) -> bool:
    if primary_attribution != "generator":
        return True
    prose = " ".join(
        str(finding.get(key, ""))
        for key in ("mechanism", "symptom", "remediation", "component")
    )
    return not primary_attribution_blocks_app_bottleneck("generator", prose)


def competing_hypotheses_allow_findings(
    findings: list[dict[str, Any]],
    ledger_or_events: Any,
    *,
    competing_mechanisms: list[str],
) -> bool:
    if has_confirmed_prediction(_ledger_events(ledger_or_events)):
        return True
    mechs = {m.lower() for m in competing_mechanisms}
    for finding in findings:
        mech = str(finding.get("mechanism", "")).lower()
        if any(cm in mech for cm in mechs):
            return False
    return True


def git_history_claim_allowed(
    finding: dict[str, Any],
    ledger_or_events: Any,
    *,
    forbidden_substrings: list[str],
) -> bool:
    events = _ledger_events(ledger_or_events)
    blob = " ".join(
        str(finding.get(key, ""))
        for key in ("mechanism", "symptom", "observed_facts", "remediation")
    )
    if isinstance(finding.get("observed_facts"), list):
        blob += " " + " ".join(str(x) for x in finding["observed_facts"])
    lower = blob.lower()
    if not any(sub.lower() in lower for sub in forbidden_substrings):
        return True
    return has_confirmed_prediction(events)
